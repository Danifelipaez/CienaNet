"""Ingesta de rayos desde GOES-19 GLM — nowcast de tormentas acercándose a la
CGSM por el corredor Cesar → Magdalena centro (docs/ALERTAS_VENDAVAL.md,
scripts/verify_glm_lead_29ago.py: 270 min de lead real medidos contra el
vendaval del 29-ago-2026).

Bucket público `noaa-goes19` en S3, sin auth — httpx puro contra el listado
REST de S3, sin boto3. Los archivos GLM-L2-LCFA son HDF5 real (firma
confirmada con `xxd`), los abre `h5py` directo sin depender de `netCDF4`.

TTL de cache más corto que weather.py (300s vs 3600s): el dato cambia cada
10 min, no cada hora.
"""

import asyncio
import io
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import h5py
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BUCKET_URL = "https://noaa-goes19.s3.amazonaws.com"
_TTL = 300.0  # 5 min

_cache: dict | None = None
_cache_ts = 0.0

_ultimo_nowcast: dict | None = None


def set_ultimo_nowcast(resultado: dict | None) -> None:
    """Guarda el resultado más reciente de signals.py::tormenta_aproximandose
    (lo llama app/main.py::_nowcast_refresh cada 10 min) para que el dashboard
    lo lea sin recalcularlo en cada `GET /data/latest` — la instantánea
    anterior que esa función necesita vive en el propio bucle de
    _nowcast_refresh, no acá.

    ponytail: en memoria de proceso, se pierde en reinicio; el próximo ciclo
    (10 min) lo repone.
    """
    global _ultimo_nowcast
    _ultimo_nowcast = resultado


def get_ultimo_nowcast() -> dict | None:
    return _ultimo_nowcast


async def _list_keys(client: httpx.AsyncClient, dt: datetime) -> list[str]:
    prefix = f"GLM-L2-LCFA/{dt.year}/{dt.timetuple().tm_yday:03d}/{dt.hour:02d}/"
    resp = await client.get(_BUCKET_URL, params={"list-type": "2", "prefix": prefix, "max-keys": "1000"})
    resp.raise_for_status()
    return re.findall(r"<Key>([^<]+)</Key>", resp.text)


async def _recent_keys(client: httpx.AsyncClient, n: int) -> list[str]:
    """Últimos `n` archivos por orden cronológico (el nombre del archivo
    ordena igual que el tiempo). Si la hora UTC actual apenas empieza y no
    tiene `n` archivos todavía, completa con la cola de la hora anterior."""
    now = datetime.now(timezone.utc)
    keys = await _list_keys(client, now)
    if len(keys) < n:
        keys = (await _list_keys(client, now - timedelta(hours=1))) + keys
    return sorted(keys)[-n:]


def _file_epoch(var: h5py.Dataset) -> datetime:
    units = var.attrs["units"]
    if isinstance(units, bytes):
        units = units.decode()
    base = units.removeprefix("seconds since ").strip()
    return datetime.strptime(base, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)


def _decode_flash_times(var: h5py.Dataset, epoch: datetime) -> list[datetime]:
    """GOES-R empaqueta el tiempo como entero (a veces con signo invertido vía
    el atributo `_Unsigned`) + `scale_factor`/`add_offset` (convención CF que
    h5py, a diferencia de netCDF4/xarray, no aplica solo)."""
    raw = var[:].tolist()
    if var.attrs.get("_Unsigned") in (b"true", "true"):
        bits = var.dtype.itemsize * 8
        raw = [v + (1 << bits) if v < 0 else v for v in raw]
    scale = float(var.attrs["scale_factor"][0])
    offset = float(var.attrs["add_offset"][0])
    return [epoch + timedelta(seconds=v * scale + offset) for v in raw]


def _flashes_from_bytes(data: bytes) -> list[dict]:
    with h5py.File(io.BytesIO(data), "r") as f:
        lats = f["flash_lat"][:].tolist()
        lons = f["flash_lon"][:].tolist()
        var = f["flash_time_offset_of_first_event"]
        times = _decode_flash_times(var, _file_epoch(var))
    return [
        {"lat": lat, "lon": lon, "timestamp": t.isoformat()}
        for lat, lon, t in zip(lats, lons, times, strict=True)
        if settings.corredor_lat_min <= lat <= settings.corredor_lat_max
        and settings.corredor_lon_min <= lon <= settings.corredor_lon_max
    ]


async def get_lightning_flashes() -> dict:
    """Retorna los destellos recientes (`settings.glm_files_per_ciclo`
    archivos, ~1 min de datos) sobre el corredor de aproximación a la CGSM.

    Mismo patrón que weather.py: reintentos con backoff, fallback al último
    resultado bueno, `origen: "sin_dato"` si todo falla — nunca inventa.
    """
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache and now - _cache_ts < _TTL:
        return _cache

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                keys = await _recent_keys(client, settings.glm_files_per_ciclo)
                responses = await asyncio.gather(*(client.get(f"{_BUCKET_URL}/{k}") for k in keys))
            flashes = []
            for resp in responses:
                resp.raise_for_status()
                flashes.extend(_flashes_from_bytes(resp.content))
            result = {"flashes": flashes, "origen": "medido"}
            _cache, _cache_ts = result, now
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1 + attempt)

    logger.warning("GOES-19 GLM no disponible tras reintentos: %s", last_exc)
    if _cache:
        return {**_cache, "origen": "cache"}
    return {"flashes": [], "origen": "sin_dato"}
