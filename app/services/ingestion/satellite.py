"""Ingesta satelital ERDDAP — SST (NASA MUR) y clorofila (Copernicus S-3 OLCI vía NOAA CoastWatch).

SST: lag 2 días, resolución ~1.1 km (jplMURSST41) — ya es la más fina disponible, sin cambios.
Clorofila: Sentinel-3 OLCI, ~278 m diario, sector "FG" (cubre la CGSM). Migrado desde el
compuesto MODIS de 4 km/8 días: ese píxel mezclaba la laguna con el Caribe abierto y
subestimaba la clorofila real (hipereutrófica) de la ciénaga. Ver docs/RESOLUCION_FUENTES.md.
Fallback: baselines históricos de la Ciénaga Grande.
erddapy es síncrono → asyncio.to_thread para no bloquear el event loop (solo SST: el
servidor de NOAA CoastWatch para OLCI bloquea el User-Agent por defecto de erddapy/requests
con un 403, y erddapy no reenvía headers personalizados en griddap_initialize — la
clorofila se pide con httpx directo en su lugar, con User-Agent propio).
"""

import asyncio
import logging
from datetime import date, timedelta

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ERDDAP_SERVER = "https://coastwatch.pfeg.noaa.gov/erddap"  # NASA MUR SST
NOAA_CW_SERVER = "https://coastwatch.noaa.gov/erddap"      # Copernicus OLCI vía NOAA CoastWatch
LAT_MIN, LAT_MAX = 10.5, 11.2
LON_MIN, LON_MAX = -74.85, -73.9

_SST_BASELINE = 28.0   # °C promedio histórico Ciénaga Grande
_CHL_BASELINE = 4.5    # mg/m³ promedio histórico (bajo — el dato real de OLCI ronda 8-80)
_SST_MIN, _SST_MAX = 15.0, 40.0  # rango válido antes de aceptar (buenas prácticas del doc)
_CHL_WINDOW_DAYS = 7   # ventana para tolerar nubes: producto óptico, no todos los días tienen píxel válido
_CHL_STRIDE = 10       # ponytail: 1 de cada 10 píxeles (~2.8km) — basta para un promedio de área,
                       # evita descargar ~2M filas/semana a resolución nativa de 300m
_USER_AGENT = "CienaNetBot/1.0"  # NOAA CoastWatch bloquea el UA por defecto de clientes HTTP genéricos


def _fetch_sst(date_str: str) -> float:
    from erddapy import ERDDAP  # import tardío: erddapy tarda en importar

    e = ERDDAP(server=ERDDAP_SERVER, protocol="griddap")
    e.dataset_id = settings.erddap_sst_dataset
    e.griddap_initialize()
    e.constraints = {
        "time>=": f"{date_str}T09:00:00Z",
        "time<=": f"{date_str}T09:00:00Z",
        "latitude>=": LAT_MIN,
        "latitude<=": LAT_MAX,
        "longitude>=": LON_MIN,
        "longitude<=": LON_MAX,
    }
    e.variables = ["analysed_sst"]
    ds = e.to_xarray()
    sst = round(float(ds["analysed_sst"].mean()) - 273.15, 2)  # Kelvin → Celsius
    return sst if _SST_MIN <= sst <= _SST_MAX else _SST_BASELINE


async def _fetch_chlorophyll(start_str: str) -> float:
    # "(last)" en vez de una fecha explícita: el feed NRT va ~2 días atrasado y un
    # stop futuro explícito da 404 ("Stop is greater than the axis maximum"); (last)
    # se autoajusta al dato más reciente disponible, sea cual sea el lag ese día.
    query = (
        f"chlor_a[({start_str}T00:00:00Z):(last)]"
        f"[(0.0)]"
        f"[({LAT_MIN}):{_CHL_STRIDE}:({LAT_MAX})]"
        f"[({LON_MIN}):{_CHL_STRIDE}:({LON_MAX})]"
    )
    url = f"{NOAA_CW_SERVER}/griddap/{settings.erddap_chl_dataset}.json?{query}"
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": _USER_AGENT}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    cols = data["table"]["columnNames"]
    idx = cols.index("chlor_a")
    valid = [row[idx] for row in data["table"]["rows"] if row[idx] is not None]
    if not valid:
        return _CHL_BASELINE
    chl = sum(valid) / len(valid)
    return round(chl, 3) if 0 < chl < 100 else _CHL_BASELINE


async def get_sst() -> float:
    date_str = (date.today() - timedelta(days=2)).isoformat()
    try:
        return await asyncio.to_thread(_fetch_sst, date_str)
    except Exception as exc:
        logger.warning("NASA ERDDAP SST no disponible (%s): usando baseline %s°C", exc, _SST_BASELINE)
        return _SST_BASELINE


async def get_chlorophyll() -> float:
    start_str = (date.today() - timedelta(days=_CHL_WINDOW_DAYS)).isoformat()
    try:
        return await _fetch_chlorophyll(start_str)
    except Exception as exc:
        logger.warning("Copernicus OLCI clorofila no disponible (%s): usando baseline %s mg/m³", exc, _CHL_BASELINE)
        return _CHL_BASELINE


async def get_satellite_data() -> dict:
    sst, chl = await asyncio.gather(get_sst(), get_chlorophyll())
    sat_date = (date.today() - timedelta(days=2)).isoformat()
    return {
        "sst_celsius": sst,
        "chlorophyll_mgm3": chl,
        "date": sat_date,
    }
