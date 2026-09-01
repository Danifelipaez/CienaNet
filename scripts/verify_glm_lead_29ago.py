"""Backtest: ¿el mecanismo que usará `signals.py::tormenta_aproximandose()`
(centroide de rayos entre dos instantáneas de 10 min -> velocidad -> ETA) habría
dado >=60 min de anticipación real sobre el vendaval del 29-ago-2026 en el
Magdalena centro-sur?

Puerta de entrada del rediseño de dos niveles (docs/ALERTAS_VENDAVAL.md). NO es
parte de pytest — script de verificación manual (mismo espíritu que
scripts/verify_alert_lock.py). Necesita red real hacia *.s3.amazonaws.com
(bucket público `noaa-goes19`, sin auth) y `pip install h5py` (los archivos
GLM-L2-LCFA son HDF5 real, firma confirmada con `xxd`).

Un primer intento (comparar cuándo cruza actividad un lado este/oeste de una
caja fija contra Chibolo) daba solo 10-40 min y hacía parecer que el diseño no
sirve. Es la pregunta equivocada: Chibolo quedó bajo la tormenta casi en el
instante en que esta se volvió detectable en todo el corredor — ningún método
de monitoreo puede anticipar una tormenta que se forma encima de su propio
objetivo (límite físico, no una falla de este diseño). La pregunta correcta —
la que sí importa para proteger la CGSM, que es un objetivo lejano al que un
sistema tendría que ACERCARSE — es si el centroide de una tormenta con
trayectoria real y sostenida da un ETA útil con anticipación. Tenerife (pueblo
con ~30 viviendas y un colegio afectados, y con un colapso de capa límite
documentado hasta las 18h locales / 23h UTC) es el caso de prueba: el sistema
viene acercándose desde la frontera con Cesar desde temprano.

Método:
1. Descarga TODOS los archivos GLM-L2-LCFA del 29-ago sobre la caja del
   corredor (sin submuestreo — el volumen de un día es manejable, ~1800
   archivos, ~630 MB).
2. Calcula el centroide (ponderado por cantidad, no por energía) de los
   destellos de cada bucket de 10 min con >= MIN_FLASHES_CENTROIDE destellos.
3. Para cada par de buckets consecutivos, calcula la velocidad de acercamiento
   a Tenerife y, si se está acercando, el ETA lineal ingenuo.
4. Reporta el primer ciclo con ETA <= LEAD_MIN_REQUERIDO y cuánto antes de la
   ventana de daño documentada (18-23h UTC) ocurrió.

Uso:
    python scripts/verify_glm_lead_29ago.py
"""

import asyncio
import io
import math
import re
from datetime import datetime, timedelta, timezone

import h5py
import httpx
import numpy as np

BUCKET_URL = "https://noaa-goes19.s3.amazonaws.com"
DOY_2026_08_29 = 241  # 2026 no es bisiesto: 31+28+31+30+31+30+31+29 = 241

# Caja del corredor (misma que settings.corredor_lat/lon_min/max del rediseño).
LAT_MIN, LAT_MAX = 9.0, 11.3
LON_MIN, LON_MAX = -75.3, -73.3

# 14-23h UTC = 09:00-18:00 local (America/Bogota, UTC-5) — cubre desde antes del
# colapso de capa límite de Chibolo (13-15h local) hasta después del de Tenerife
# (~18h local), ver docs/ALERTAS_VENDAVAL.md.
HOURS_UTC = range(14, 24)

# Tenerife: pueblo con daño documentado (~30 viviendas + 1 colegio), coordenada
# aproximada de cabecera municipal (no geocodificada con precisión — alcanza
# para un backtest en km, no para production).
TENERIFE = (9.33, -74.85)
# Colapso de capa límite documentado para Tenerife: 18h LOCAL (America/Bogota,
# UTC-5) = 23:00 UTC — la huella del downburst tocando el pueblo (ver Parte 1
# de la investigación que originó este rediseño, docs/ALERTAS_VENDAVAL.md).
TENERIFE_IMPACTO_UTC = datetime(2026, 8, 29, 23, 0, tzinfo=timezone.utc)

MIN_FLASHES_CENTROIDE = 10  # menos que esto, el centroide es ruido
LEAD_MIN_REQUERIDO = 60


def _list_files(client: httpx.Client, hour_utc: int) -> list[str]:
    prefix = f"GLM-L2-LCFA/2026/{DOY_2026_08_29:03d}/{hour_utc:02d}/"
    keys: list[str] = []
    continuation = None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if continuation:
            params["continuation-token"] = continuation
        resp = client.get(BUCKET_URL, params=params, timeout=30)
        resp.raise_for_status()
        text = resp.text
        keys.extend(re.findall(r"<Key>([^<]+)</Key>", text))
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", text)
        if not m:
            break
        continuation = m.group(1)
    return keys


def _decode_unsigned_scaled(var: h5py.Dataset) -> np.ndarray:
    """Variables GOES-R empaquetadas: entero (a veces con signo invertido vía
    `_Unsigned`) + `scale_factor`/`add_offset` (convención CF que h5py, a
    diferencia de netCDF4/xarray, no aplica solo)."""
    raw = var[:]
    if var.attrs.get("_Unsigned") in (b"true", "true"):
        raw = raw.view(f"uint{raw.dtype.itemsize * 8}")
    scale = float(np.asarray(var.attrs.get("scale_factor", [1.0])).flat[0])
    offset = float(np.asarray(var.attrs.get("add_offset", [0.0])).flat[0])
    return raw.astype("float64") * scale + offset


def _file_epoch(var: h5py.Dataset) -> datetime:
    units = var.attrs["units"]
    if isinstance(units, bytes):
        units = units.decode()
    base = units.removeprefix("seconds since ").strip()
    return datetime.strptime(base, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)


def _flashes_from_bytes(data: bytes) -> list[tuple[float, float, datetime]]:
    with h5py.File(io.BytesIO(data), "r") as f:
        lats = f["flash_lat"][:]
        lons = f["flash_lon"][:]
        var = f["flash_time_offset_of_first_event"]
        epoch = _file_epoch(var)
        secs = _decode_unsigned_scaled(var)
    out = []
    for lat, lon, s in zip(lats, lons, secs, strict=True):
        if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
            out.append((float(lat), float(lon), epoch + timedelta(seconds=float(s))))
    return out


async def _download_all(keys: list[str]) -> list[tuple[float, float, datetime]]:
    sem = asyncio.Semaphore(16)
    flashes: list[tuple[float, float, datetime]] = []

    async def _one(client: httpx.AsyncClient, key: str) -> None:
        async with sem:
            try:
                resp = await client.get(f"{BUCKET_URL}/{key}", timeout=30)
                resp.raise_for_status()
                flashes.extend(_flashes_from_bytes(resp.content))
            except Exception as exc:  # noqa: BLE001 — script de diagnóstico manual
                print(f"    [aviso] {key}: {exc}")

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(_one(client, k) for k in keys))
    return flashes


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def _centroids_by_bucket(
    flashes: list[tuple[float, float, datetime]],
) -> dict[datetime, tuple[float, float, int]]:
    buckets: dict[datetime, list[tuple[float, float]]] = {}
    for lat, lon, t in flashes:
        b = t.replace(minute=(t.minute // 10) * 10, second=0, microsecond=0)
        buckets.setdefault(b, []).append((lat, lon))
    return {
        b: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), len(pts))
        for b, pts in buckets.items()
        if len(pts) >= MIN_FLASHES_CENTROIDE
    }


def main() -> None:
    print(
        f"Escaneando GOES-19 GLM, 2026-08-29, {HOURS_UTC.start}-{HOURS_UTC.stop - 1}h "
        f"UTC, corredor lat[{LAT_MIN},{LAT_MAX}] lon[{LON_MIN},{LON_MAX}] (sin submuestreo)...\n"
    )

    with httpx.Client() as client:
        all_keys = []
        for h in HOURS_UTC:
            keys = _list_files(client, h)
            print(f"  {h:02d}h UTC: {len(keys)} archivos")
            all_keys.extend(keys)

    print(f"\nDescargando {len(all_keys)} archivos...")
    flashes = asyncio.run(_download_all(all_keys))
    print(f"Destellos en el corredor: {len(flashes)}")

    centroids = _centroids_by_bucket(flashes)
    times = sorted(centroids)
    if len(times) < 2:
        print("\nMuy pocos buckets con centroide confiable — no se puede medir ETA.")
        raise SystemExit(1)

    primer_bucket = times[0]
    print(f"\nPrimera actividad significativa en todo el corredor: {primer_bucket.isoformat()}")
    print(f"Colapso de capa límite documentado en Tenerife (impacto real): {TENERIFE_IMPACTO_UTC.isoformat()}")

    primer_eta_util = None
    for i in range(1, len(times)):
        t0, t1 = times[i - 1], times[i]
        if (t1 - t0).total_seconds() > 15 * 60:
            continue  # hueco de datos: no hay "instantánea anterior" válida para este ciclo
        lat0, lon0, _ = centroids[t0]
        lat1, lon1, n1 = centroids[t1]
        dt_min = (t1 - t0).total_seconds() / 60

        d_prev = _haversine_km((lat0, lon0), TENERIFE)
        d_now = _haversine_km((lat1, lon1), TENERIFE)
        closing_kmh = (d_prev - d_now) / (dt_min / 60)
        if closing_kmh <= 0:
            continue  # no se acerca en este ciclo — tormenta_aproximandose() tampoco opinaría

        eta_min = (d_now / closing_kmh) * 60
        if eta_min <= 90 and primer_eta_util is None:  # settings.nowcast_eta_max_min por defecto
            primer_eta_util = (t1, eta_min, d_now, n1)

    if primer_eta_util is None:
        print("\nFALLO: nunca hubo un ciclo con ETA<=90min acercándose a Tenerife.")
        raise SystemExit(1)

    t_alerta, eta_min, dist_km, n_destellos = primer_eta_util
    lead_min = (TENERIFE_IMPACTO_UTC - t_alerta).total_seconds() / 60

    print(
        f"\nPrimer ciclo con señal accionable (acercándose, ETA<=90min): {t_alerta.isoformat()} "
        f"(ETA={eta_min:.0f} min, distancia={dist_km:.0f} km, n={n_destellos} destellos)"
    )
    print(f"Lead sobre el colapso de capa límite documentado en Tenerife: {lead_min:.0f} minutos")

    if lead_min >= LEAD_MIN_REQUERIDO:
        print(f"\nOK: >={LEAD_MIN_REQUERIDO} min de anticipación real — el mecanismo de centroide+ETA sirve.")
        print(
            "Aviso: esto no cubre convección que se forma encima del propio objetivo (ver Chibolo en "
            "docs/ALERTAS_VENDAVAL.md) — límite físico de cualquier nowcast, no de esta implementación."
        )
    else:
        print(f"\nFALLO: {lead_min:.0f} min < {LEAD_MIN_REQUERIDO} — replantear.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
