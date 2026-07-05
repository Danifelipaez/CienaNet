"""Ingesta meteorológica desde Open-Meteo (V-01).

Cache en memoria de 60 minutos. Fallback al último resultado exitoso si la API falla.
Usa httpx (ya en requirements) en lugar de openmeteo-requests para evitar dependencia extra.
"""

import asyncio
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_TTL = 3600.0  # 60 min

# ponytail: cache de módulo, una entrada, suficiente para una sola ubicación
_cache: dict = {"data": None, "ts": 0.0}


async def get_weather_forecast() -> dict:
    """Retorna condiciones meteorológicas actuales para la Ciénaga Grande."""
    now = time.monotonic()
    if _cache["data"] and now - _cache["ts"] < _TTL:
        return _cache["data"]

    params = {
        "latitude": settings.cienaga_lat,
        "longitude": settings.cienaga_lon,
        "current": [
            "temperature_2m",
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
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "precipitation_mm": current.get("precipitation"),
            }
            _cache["data"] = result
            _cache["ts"] = now
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1 + attempt)  # 1s, luego 2s

    logger.warning("Open-Meteo no disponible tras reintentos: %s", last_exc)
    if _cache["data"]:
        return _cache["data"]
    return {
        "temperature_c": None,
        "wind_speed_kmh": None,
        "wind_direction_deg": None,
        "precipitation_mm": None,
    }
