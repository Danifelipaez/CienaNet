"""Ingesta meteorológica desde Open-Meteo (V-01).

Cache en memoria de 60 minutos por ubicación (lat, lon) — soporta más de un
punto (CGSM, Tasajera) sin pisarse el caché entre ellos. Fallback al último
resultado exitoso de esa ubicación si la API falla. Usa httpx (ya en
requirements) en lugar de openmeteo-requests para evitar dependencia extra.
"""

import asyncio
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_TTL = 3600.0  # 60 min

_cache: dict[tuple[float, float], dict] = {}


async def get_weather_forecast(lat: float | None = None, lon: float | None = None) -> dict:
    """Retorna condiciones meteorológicas actuales para una ubicación.

    Sin argumentos, usa el centroide de la Ciénaga Grande (comportamiento previo).
    """
    lat = settings.cienaga_lat if lat is None else lat
    lon = settings.cienaga_lon if lon is None else lon
    key = (lat, lon)
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached["ts"] < _TTL:
        return cached["data"]

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "precipitation",
        ],
        "timezone": "America/Bogota",
    }

    # Reintentos con backoff corto (2 extra): la API es estable, fallos suelen ser
    # transitorios (buenas prácticas del doc).
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_OPEN_METEO_URL, params=params)
                resp.raise_for_status()
            current = resp.json()["current"]
            result = {
                "temperature_c": current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "precipitation_mm": current.get("precipitation"),
            }
            _cache[key] = {"data": result, "ts": now}
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1 + attempt)  # 1s, luego 2s

    logger.warning("Open-Meteo no disponible tras reintentos (%s, %s): %s", lat, lon, last_exc)
    if cached:
        return cached["data"]
    return {
        "temperature_c": None,
        "humidity_pct": None,
        "wind_speed_kmh": None,
        "wind_direction_deg": None,
        "precipitation_mm": None,
    }
