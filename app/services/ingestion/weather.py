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
        return cached["data"]  # dentro del TTL: ya trae origen="medido" de cuando se guardó

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
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
                "wind_gust_kmh": current.get("wind_gusts_10m"),
                "precipitation_mm": current.get("precipitation"),
                "origen": "medido",
            }
            _cache[key] = {"data": result, "ts": now}
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1 + attempt)  # 1s, luego 2s

    logger.warning("Open-Meteo no disponible tras reintentos (%s, %s): %s", lat, lon, last_exc)
    if cached:
        # El fetch fresco falló y este cache ya venció su TTL (si no, se habría
        # devuelto arriba) — sigue siendo el mejor dato disponible, pero hay que
        # nombrarlo distinto de "medido" para no ocultar que está rancio.
        return {**cached["data"], "origen": "cache"}
    return {
        "temperature_c": None,
        "humidity_pct": None,
        "wind_speed_kmh": None,
        "wind_direction_deg": None,
        "wind_gust_kmh": None,
        "precipitation_mm": None,
        "origen": "sin_dato",
    }


_forecast_cache: dict[tuple[float, float, int], dict] = {}


_CONVECTIVE_VARS = [
    "wind_gusts_10m",
    "cape",
    "lifted_index",
    "convective_inhibition",
    "dew_point_2m",
    "temperature_2m",
]


async def get_convective_forecast(
    lat: float | None = None, lon: float | None = None, hours: int | None = None
) -> dict:
    """Retorna el pronóstico horario de ráfaga + variables convectivas (CAPE,
    lifted index, CIN, punto de rocío) para las próximas `hours` horas — la base
    del outlook de vendaval (signals.py::vendaval_risk). A diferencia de
    get_weather_forecast() (solo condición actual), mira hacia adelante
    (docs/ALERTAS_VENDAVAL.md).

    Mismo patrón que get_weather_forecast: cache en memoria, reintentos con
    backoff corto, fallback a la última respuesta buena. `puntos` viene vacío
    (nunca inventado) si la fuente falla y no hay cache.
    """
    lat = settings.cienaga_lat if lat is None else lat
    lon = settings.cienaga_lon if lon is None else lon
    hours = settings.vendaval_forecast_hours if hours is None else hours
    key = (lat, lon, hours)
    now = time.monotonic()
    cached = _forecast_cache.get(key)
    if cached and now - cached["ts"] < _TTL:
        return cached["data"]

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": _CONVECTIVE_VARS,
        "forecast_days": min(16, max(1, -(-hours // 24) + 1)),  # ceil(hours/24) + 1 día de margen
        "timezone": "America/Bogota",
    }

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_OPEN_METEO_URL, params=params)
                resp.raise_for_status()
            hourly = resp.json()["hourly"]
            puntos = [
                {
                    "timestamp": ts,
                    "wind_gust_kmh": hourly["wind_gusts_10m"][i],
                    "cape": hourly["cape"][i],
                    "lifted_index": hourly["lifted_index"][i],
                    "convective_inhibition": hourly["convective_inhibition"][i],
                    "dew_point_2m": hourly["dew_point_2m"][i],
                    "temperature_2m": hourly["temperature_2m"][i],
                }
                for i, ts in enumerate(hourly["time"])
            ][:hours]
            result = {"puntos": puntos, "origen": "medido"}
            _forecast_cache[key] = {"data": result, "ts": now}
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1 + attempt)

    logger.warning("Pronóstico convectivo Open-Meteo no disponible (%s, %s): %s", lat, lon, last_exc)
    if cached:
        return {**cached["data"], "origen": "cache"}
    return {"puntos": [], "origen": "sin_dato"}
