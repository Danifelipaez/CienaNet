"""Ingesta satelital NASA ERDDAP — SST y clorofila (V-02).

SST: lag 2 días (procesamiento NASA MUR).
Clorofila: lag 4 días (compuesto 8 días MODIS-Aqua).
Fallback: baselines históricos de la Ciénaga Grande.
erddapy es síncrono → asyncio.to_thread para no bloquear el event loop.
"""

import asyncio
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

ERDDAP_SERVER = "https://coastwatch.pfeg.noaa.gov/erddap"
LAT_MIN, LAT_MAX = 10.5, 11.2
LON_MIN, LON_MAX = -74.85, -73.9

_SST_BASELINE = 28.0   # °C promedio histórico Ciénaga Grande
_CHL_BASELINE = 4.5    # mg/m³ promedio histórico


def _fetch_sst(date_str: str) -> float:
    from erddapy import ERDDAP  # import tardío: erddapy tarda en importar

    e = ERDDAP(server=ERDDAP_SERVER, protocol="griddap")
    e.dataset_id = "jplMURSST41"
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
    return round(float(ds["analysed_sst"].mean()) - 273.15, 2)  # Kelvin → Celsius


def _fetch_chlorophyll(date_str: str) -> float:
    from erddapy import ERDDAP

    e = ERDDAP(server=ERDDAP_SERVER, protocol="griddap")
    e.dataset_id = "erdMH1chla8day"
    e.griddap_initialize()
    e.constraints = {
        "time>=": f"{date_str}T00:00:00Z",
        "time<=": f"{date_str}T00:00:00Z",
        "latitude>=": LAT_MIN,
        "latitude<=": LAT_MAX,
        "longitude>=": LON_MIN,
        "longitude<=": LON_MAX,
    }
    e.variables = ["chlorophyll"]
    ds = e.to_xarray()
    chl = float(ds["chlorophyll"].mean())
    return round(chl, 3) if 0 < chl < 100 else _CHL_BASELINE


async def get_sst() -> float:
    date_str = (date.today() - timedelta(days=2)).isoformat()
    try:
        return await asyncio.to_thread(_fetch_sst, date_str)
    except Exception as exc:
        logger.warning("NASA ERDDAP SST no disponible (%s): usando baseline %s°C", exc, _SST_BASELINE)
        return _SST_BASELINE


async def get_chlorophyll() -> float:
    date_str = (date.today() - timedelta(days=4)).isoformat()
    try:
        return await asyncio.to_thread(_fetch_chlorophyll, date_str)
    except Exception as exc:
        logger.warning("NASA ERDDAP clorofila no disponible (%s): usando baseline %s mg/m³", exc, _CHL_BASELINE)
        return _CHL_BASELINE


async def get_satellite_data() -> dict:
    sst, chl = await asyncio.gather(get_sst(), get_chlorophyll())
    sat_date = (date.today() - timedelta(days=2)).isoformat()
    return {
        "sst_celsius": sst,
        "chlorophyll_mgm3": chl,
        "date": sat_date,
    }
