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

Además de la media del box (compat con SatelliteSnapshot/el frontend), se calcula
una media por zona IPP — la respuesta griddap ya trae lat/lon por fila, esa
información espacial se descargaba y se tiraba en el promedio global.
"""

import asyncio
import logging
from datetime import date, timedelta

import httpx

from app.core.config import settings
from app.services.ipp import ZONES

logger = logging.getLogger(__name__)

ERDDAP_SERVER = "https://coastwatch.pfeg.noaa.gov/erddap"  # NASA MUR SST
NOAA_CW_SERVER = "https://coastwatch.noaa.gov/erddap"      # Copernicus OLCI vía NOAA CoastWatch

# Ajustado a los 3 vértices medidos en campo (docs/KNOWLEDGE_BASE.md §12). El box
# anterior (10.5-11.2, -74.85/-73.9) los "cubría" pero con tanto margen que el
# promedio mezclaba mar Caribe abierto al norte y tierra al este con el agua de
# la laguna. Corte de continuidad: valores antes/después de este cambio no son
# comparables (agua de laguna vs. promedio laguna+mar+tierra) — misma aceptación
# que la recalibración del IPP (ver app/services/ipp.py).
LAT_MIN, LAT_MAX = 10.54, 11.01
LON_MIN, LON_MAX = -74.69, -74.32

_SST_BASELINE = 28.0   # °C promedio histórico Ciénaga Grande
_CHL_BASELINE = 4.5    # mg/m³ promedio histórico (bajo — el dato real de OLCI ronda 8-80)
_SST_MIN, _SST_MAX = 15.0, 40.0  # rango válido antes de aceptar (buenas prácticas del doc)
_CHL_WINDOW_DAYS = 7   # ventana para tolerar nubes: producto óptico, no todos los días tienen píxel válido
_CHL_STRIDE = 5        # ~1.4 km (era 10/~2.8km). Con el box apretado el conteo de píxeles
                       # cae ~4x; stride 5 mantiene decenas de píxeles por zona tras el
                       # enmascarado de nubes — neto: menos filas descargadas que antes.
_ZONE_RADIUS_DEG = 0.045  # ~5 km — 2-3 celdas del grid diezmado alrededor del centroide de zona
_USER_AGENT = "CienaNetBot/1.0"  # NOAA CoastWatch bloquea el UA por defecto de clientes HTTP genéricos


def _mean_near(rows: list, cols: list[str], lat: float, lon: float, radius_deg: float) -> float | None:
    """Media de los píxeles válidos dentro de un radio alrededor de (lat, lon).
    None si no hay ninguno. Radio, no vecino más cercano: en un producto óptico
    con huecos de nube el píxel más cercano puede ser nulo o un outlier —
    promediar un vecindario es más robusto y cuesta lo mismo."""
    lat_idx, lon_idx, chl_idx = cols.index("latitude"), cols.index("longitude"), cols.index("chlor_a")
    valores = [
        row[chl_idx]
        for row in rows
        if row[chl_idx] is not None
        and abs(row[lat_idx] - lat) <= radius_deg
        and abs(row[lon_idx] - lon) <= radius_deg
    ]
    return sum(valores) / len(valores) if valores else None


def _fetch_sst(date_str: str) -> dict:
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

    box_sst = round(float(ds["analysed_sst"].mean()) - 273.15, 2)  # Kelvin → Celsius
    if _SST_MIN <= box_sst <= _SST_MAX:
        box_value, box_origen = box_sst, "medido"
    else:
        box_value, box_origen = _SST_BASELINE, "baseline"

    por_zona = {}
    for zona in ZONES:
        try:
            punto = ds["analysed_sst"].sel(latitude=zona["lat"], longitude=zona["lng"], method="nearest")
            v = round(float(punto.mean()) - 273.15, 2)
        except Exception:
            continue  # sin dato para esa zona (NaN, píxel enmascarado) — cae al box en _zone_satellite
        if _SST_MIN <= v <= _SST_MAX:
            por_zona[zona["name"]] = v

    return {"box": box_value, "origen": box_origen, "por_zona": por_zona}


async def _fetch_chlorophyll(start_str: str) -> dict:
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
    rows = data["table"]["rows"]
    chl_idx = cols.index("chlor_a")
    valid = [row[chl_idx] for row in rows if row[chl_idx] is not None]
    if not valid:
        return {"box": _CHL_BASELINE, "origen": "baseline", "por_zona": {}}

    box_chl = sum(valid) / len(valid)
    if 0 < box_chl < 100:
        box_value, box_origen = round(box_chl, 3), "medido"
    else:
        box_value, box_origen = _CHL_BASELINE, "baseline"

    por_zona = {}
    for zona in ZONES:
        v = _mean_near(rows, cols, zona["lat"], zona["lng"], _ZONE_RADIUS_DEG)
        if v is not None and 0 < v < 100:
            por_zona[zona["name"]] = round(v, 3)

    return {"box": box_value, "origen": box_origen, "por_zona": por_zona}


async def get_sst() -> dict:
    """Retorna {"box", "origen", "por_zona"} — origen es "medido" o "baseline"
    (API caída o valor fuera de rango). El baseline nunca se persiste como si
    fuera medición real, ver dashboard_persistence._save_satellite."""
    date_str = (date.today() - timedelta(days=2)).isoformat()
    try:
        return await asyncio.to_thread(_fetch_sst, date_str)
    except Exception as exc:
        logger.warning("NASA ERDDAP SST no disponible (%s): usando baseline %s°C", exc, _SST_BASELINE)
        return {"box": _SST_BASELINE, "origen": "baseline", "por_zona": {}}


async def get_chlorophyll() -> dict:
    """Retorna {"box", "origen", "por_zona"} — ver get_sst()."""
    start_str = (date.today() - timedelta(days=_CHL_WINDOW_DAYS)).isoformat()
    try:
        return await _fetch_chlorophyll(start_str)
    except Exception as exc:
        logger.warning("Copernicus OLCI clorofila no disponible (%s): usando baseline %s mg/m³", exc, _CHL_BASELINE)
        return {"box": _CHL_BASELINE, "origen": "baseline", "por_zona": {}}


async def get_satellite_data() -> dict:
    sst_result, chl_result = await asyncio.gather(get_sst(), get_chlorophyll())
    sat_date = (date.today() - timedelta(days=2)).isoformat()

    por_zona: dict[str, dict] = {}
    for zona in ZONES:
        nombre = zona["name"]
        entry = {}
        if nombre in sst_result["por_zona"]:
            entry["sst_celsius"] = sst_result["por_zona"][nombre]
        if nombre in chl_result["por_zona"]:
            entry["chlorophyll_mgm3"] = chl_result["por_zona"][nombre]
        if entry:
            por_zona[nombre] = entry

    return {
        # Escalares = media del box: SatelliteSnapshot y el frontend no se rompen.
        "sst_celsius": sst_result["box"],
        "chlorophyll_mgm3": chl_result["box"],
        "date": sat_date,
        "origen": {"sst_celsius": sst_result["origen"], "chlorophyll_mgm3": chl_result["origen"]},
        "por_zona": por_zona,
    }
