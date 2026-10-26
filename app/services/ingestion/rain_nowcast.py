"""Nowcast de lluvia desde GOES-19 ABI-L2-RRQPEF (tasa de lluvia estimada por IR,
malla fija de 2 km, un scan cada 10 min) sobre la CGSM — docs/ALERTAS_LLUVIA.md.

Mismo patrón que lightning.py: bucket público `noaa-goes19` en S3, httpx puro
contra el listado REST, HDF5 abierto con `h5py` desde memoria. Cada archivo pesa
~1.6 MB; se lee solo la ventana de ~180 km alrededor de la CGSM.

Se calculan dos fracciones de píxeles, que rain_signals.py::lluvia_nowcast convierte
en estado (lloviendo / inminente / sin_lluvia / sin_dato):
- caja de la CGSM con RR >= 1 mm/h  -> "ya está lloviendo encima"
- anillo 20-60 km (sin la caja) con RR >= 5 mm/h -> "lluvia fuerte a <=60 min"

RRQPE es un proxy satelital sin calibrar contra pluviómetros: la tasa se usa
como categoría, nunca como lámina (satura en 100 mm/h).
"""

import asyncio
import io
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import h5py
import httpx
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_BUCKET_URL = "https://noaa-goes19.s3.amazonaws.com"
_TTL = 300.0  # 5 min: el producto cambia cada 10
_SIN_DATO_RAW = 65535  # uint16 de relleno; el resto es tasa * scale_factor

# --- Proyección GOES-R fixed grid (PUG vol. 3, 4.2.8), GOES-19 en -75°W ---
_H = 35786023.0 + 6378137.0  # radio orbital desde el centro de la Tierra
_RE, _RP = 6378137.0, 6356752.31414
_LON0 = np.deg2rad(-75.0)
# Origen y paso (rad) de la malla de 2 km del producto full disk (RRQPEF).
_X0, _XS = -0.151844, 5.6e-05
_Y0, _YS = 0.151844, -5.6e-05
_HALF_DEG = 1.6  # semiancho de la ventana (~180 km)


def _lonlat_a_xy(lon: float, lat: float) -> tuple[float, float]:
    lon_r, lat_r = np.deg2rad(lon), np.deg2rad(lat)
    e2 = 1 - (_RP**2) / (_RE**2)
    phic = np.arctan((_RP**2 / _RE**2) * np.tan(lat_r))
    rc = _RP / np.sqrt(1 - e2 * np.cos(phic) ** 2)
    sx = _H - rc * np.cos(phic) * np.cos(lon_r - _LON0)
    sy = -rc * np.cos(phic) * np.sin(lon_r - _LON0)
    sz = rc * np.sin(phic)
    return float(np.arcsin(-sy / np.sqrt(sx**2 + sy**2 + sz**2))), float(np.arctan(sz / sx))


def _xy_a_lonlat(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.sin(x) ** 2 + np.cos(x) ** 2 * (np.cos(y) ** 2 + (_RE**2 / _RP**2) * np.sin(y) ** 2)
    b = -2 * _H * np.cos(x) * np.cos(y)
    c = _H**2 - _RE**2
    rs = (-b - np.sqrt(b**2 - 4 * a * c)) / (2 * a)
    sx, sy, sz = rs * np.cos(x) * np.cos(y), -rs * np.sin(x), rs * np.cos(x) * np.sin(y)
    lat = np.arctan((_RE**2 / _RP**2) * sz / np.sqrt((_H - sx) ** 2 + sy**2))
    lon = _LON0 - np.arctan(sy / (_H - sx))
    return np.rad2deg(lon), np.rad2deg(lat)


def _ventana() -> tuple[int, int, int, int]:
    """Índices (j0, j1, i0, i1) de la malla que cubren ±_HALF_DEG alrededor del centro del anillo."""
    esquinas = [
        _lonlat_a_xy(settings.lluvia_anillo_lon + dlon, settings.lluvia_anillo_lat + dlat)
        for dlat in (-_HALF_DEG, _HALF_DEG)
        for dlon in (-_HALF_DEG, _HALF_DEG)
    ]
    xs, ys = [e[0] for e in esquinas], [e[1] for e in esquinas]
    return (
        int((max(ys) - _Y0) / _YS) - 1,
        int((min(ys) - _Y0) / _YS) + 2,
        int((min(xs) - _X0) / _XS) - 1,
        int((max(xs) - _X0) / _XS) + 2,
    )


# Máscaras caja/anillo: se calculan UNA vez al importar (lat/lon de ~31k píxeles),
# no en cada scan.
_J0, _J1, _I0, _I1 = _ventana()
_LON, _LAT = _xy_a_lonlat(*np.meshgrid(_X0 + _XS * np.arange(_I0, _I1), _Y0 + _YS * np.arange(_J0, _J1)))
_MASK_CAJA = (
    (_LAT >= settings.lluvia_caja_lat_min)
    & (_LAT <= settings.lluvia_caja_lat_max)
    & (_LON >= settings.lluvia_caja_lon_min)
    & (_LON <= settings.lluvia_caja_lon_max)
)
# Distancia plana en km (error <1 % a ±100 km de la CGSM), igual que el backtest.
_DIST_KM = np.hypot(
    (_LON - settings.lluvia_anillo_lon) * 111.32 * np.cos(np.deg2rad(settings.lluvia_anillo_lat)),
    (_LAT - settings.lluvia_anillo_lat) * 110.57,
)
_MASK_ANILLO = (
    (_DIST_KM >= settings.lluvia_anillo_km_min) & (_DIST_KM < settings.lluvia_anillo_km_max) & ~_MASK_CAJA
)
_MASK_REGION = _MASK_CAJA | _MASK_ANILLO
VENTANA_SHAPE = _LAT.shape


def _frac(tasa: np.ndarray, mask: np.ndarray, umbral_mm_h: float) -> float | None:
    """Fracción de píxeles válidos de `mask` con tasa >= umbral (None si no hay válidos)."""
    v = tasa[mask]
    v = v[~np.isnan(v)]
    return float((v >= umbral_mm_h).mean()) if v.size else None


def features_from_raw(
    raw: np.ndarray, scale: float = 0.00152602, offset: float = 0.0, fill: int = _SIN_DATO_RAW
) -> dict:
    """Features de un scan a partir de la ventana cruda uint16 (`VENTANA_SHAPE`).

    `frac_nan` se mide sobre caja+anillo (lo que la regla usa), no sobre toda la
    ventana: el borde del disco no debería invalidar un scan sano. Es la misma
    función que usa scripts/gen_rrqpe_fixture.py, así el test de replay mide el
    código de producción y no una réplica.
    """
    tasa = np.where(raw == fill, np.nan, raw.astype("float32") * scale + offset)
    return {
        "frac_caja_1mm": _frac(tasa, _MASK_CAJA, 1.0),
        "frac_anillo_5mm": _frac(tasa, _MASK_ANILLO, 5.0),
        "frac_nan": float(np.isnan(tasa[_MASK_REGION]).mean()),
    }


def _scan_time(key: str) -> datetime:
    """Inicio del scan, del nombre `..._sYYYYDDDHHMMSSs_...`."""
    m = re.search(r"_s(\d{4})(\d{3})(\d{2})(\d{2})", key)
    if not m:
        raise ValueError("nombre de archivo RRQPE sin timestamp")
    anio, doy, hh, mm = (int(g) for g in m.groups())
    return datetime(anio, 1, 1, hh, mm, tzinfo=timezone.utc) + timedelta(days=doy - 1)


def _features_from_bytes(data: bytes) -> dict:
    with h5py.File(io.BytesIO(data), "r") as f:
        ds = f["RRQPE"]
        raw = ds[_J0:_J1, _I0:_I1]
        scale = float(ds.attrs["scale_factor"][0])
        offset = float(ds.attrs["add_offset"][0]) if "add_offset" in ds.attrs else 0.0
        fill = int(ds.attrs["_FillValue"][0]) if "_FillValue" in ds.attrs else _SIN_DATO_RAW
        # El RRQPE real ya viene uint16 (sin _Unsigned); esto cubre una variante
        # int16 + `_Unsigned` como la de lightning.py::_decode_flash_times.
        if raw.dtype.kind == "i" and ds.attrs.get("_Unsigned") in (b"true", "true"):
            raw = raw.view(f"u{raw.dtype.itemsize}")
            fill %= 1 << (raw.dtype.itemsize * 8)
    return features_from_raw(raw, scale, offset, fill)


async def _latest_key(client: httpx.AsyncClient) -> str | None:
    """Archivo más reciente: revisa la hora UTC actual y, si aún está vacía, la anterior."""
    now = datetime.now(timezone.utc)
    for dt in (now, now - timedelta(hours=1)):
        prefix = f"ABI-L2-RRQPEF/{dt.year}/{dt.timetuple().tm_yday:03d}/{dt.hour:02d}/"
        resp = await client.get(_BUCKET_URL, params={"list-type": "2", "prefix": prefix, "max-keys": "1000"})
        resp.raise_for_status()
        keys = re.findall(r"<Key>([^<]+\.nc)</Key>", resp.text)
        if keys:
            return max(keys)  # el nombre ordena igual que el tiempo
    return None


_cache: dict | None = None
_cache_ts = 0.0

_ultimo_lluvia: dict | None = None


def set_ultimo_lluvia(resultado: dict | None) -> None:
    """Guarda el último resultado de rain_signals.py::lluvia_nowcast (lo llama
    app/main.py::_nowcast_refresh cada 10 min) para que el dashboard lo lea sin
    descargar el scan en cada `GET /data/latest`.

    ponytail: en memoria de proceso, se pierde en reinicio; el próximo ciclo lo repone.
    """
    global _ultimo_lluvia
    _ultimo_lluvia = resultado


def get_ultimo_lluvia() -> dict | None:
    return _ultimo_lluvia


async def get_rain_features() -> dict | None:
    """Features del último scan RRQPE: `{scan (datetime UTC), frac_caja_1mm,
    frac_anillo_5mm, frac_nan}`, o None si no hay forma de obtenerlo.

    A diferencia de weather.py/lightning.py no devuelve el último resultado en
    caché cuando falla la red: un scan viejo no sirve para un nowcast de 30 min,
    y lluvia_nowcast ya lo marcaría `sin_dato` por antigüedad. Solo reusa dentro
    del TTL.
    """
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache and now - _cache_ts < _TTL:
        return _cache

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                key = await _latest_key(client)
                if key is None:
                    logger.warning("GOES-19 RRQPE: sin archivos en la hora actual ni la anterior")
                    return None
                resp = await client.get(f"{_BUCKET_URL}/{key}")
                resp.raise_for_status()
            result = {"scan": _scan_time(key), **_features_from_bytes(resp.content)}
            _cache, _cache_ts = result, now
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 1:
                await asyncio.sleep(1)
    logger.warning("GOES-19 RRQPE no disponible: %s", last_exc)
    return None
