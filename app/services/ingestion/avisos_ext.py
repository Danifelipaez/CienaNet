"""Fuentes de los avisos del tiempo (docs/AVISOS_CLIMA.md).

- Open-Meteo Forecast con 3 modelos globales independientes (ECMWF IFS, GFS, ICON):
  lluvia, viento y ráfaga horarios — cada modelo es un "voto" del consenso.
- Open-Meteo Marine con 3 modelos de oleaje (ECMWF WAM, GFS-Wave, MFWAM) en el mar
  frente a la Boca de la Barra.
- NOAA NHC CurrentStorms.json: ciclones activos estructurados (sin regex de texto).
- NOAA CPC: estado del sistema de alerta ENSO (El Niño / La Niña).
- Xweather /forecasts: SOLO desempate cuando 1 de 3 modelos ve el evento (ver
  avisos.py) — cuota mensual compartida con las teselas de radar del frontend.

Mismo patrón que weather.py: cache en memoria, 3 intentos con backoff corto, cache de
falla de 5 min y `origen` medido/cache/sin_dato. Un pronóstico más viejo que
`max_edad` no se usa ni como respaldo: se reporta "sin_dato" en vez de opinar con él.
"""

import asyncio
import html
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
_NHC_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
_ENSO_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
_XWEATHER_URL = "https://data.api.xweather.com/forecasts/{lat},{lon}"

MODELOS = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")
MODELOS_OLA = ("ecmwf_wam025", "ncep_gfswave025", "meteofrance_wave")

_FALLO_TTL = 300.0
# ponytail: cache de módulo, un solo punto (CGSM) por fuente
_cache: dict[str, dict] = {}


async def _con_cache(
    clave: str, ttl: float, max_edad: float, fetch: Callable[[], Awaitable[Any]], intentos: int = 3
) -> tuple[Any, str]:
    """(dato, origen). Dentro de `ttl` no toca la red; tras fallar los `intentos`
    devuelve el último dato bueno como "cache" si tiene menos de `max_edad` s."""
    now = time.monotonic()
    c = _cache.get(clave) or {}
    if c.get("data") is not None and now - c["ts"] < ttl:
        return c["data"], "medido"
    if c.get("fallo_ts") is not None and now - c["fallo_ts"] < _FALLO_TTL:
        return _respaldo(c, now, max_edad)

    error = ""
    for intento in range(intentos):
        try:
            data = await fetch()
            _cache[clave] = {"data": data, "ts": now, "fallo_ts": None}
            return data, "medido"
        except Exception as exc:
            # Solo el tipo y el status: el mensaje de httpx repite la URL, y la de
            # Xweather lleva la clave en la query.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            error = f"{type(exc).__name__}{f' HTTP {status}' if status else ''}"
            if intento < intentos - 1:
                await asyncio.sleep(1 + intento)
    logger.warning("Fuente de avisos '%s' no disponible tras %d intento(s): %s", clave, intentos, error)
    c["fallo_ts"] = now
    _cache[clave] = c
    return _respaldo(c, now, max_edad)


def _respaldo(c: dict, now: float, max_edad: float) -> tuple[Any, str]:
    if c.get("data") is not None and now - c["ts"] < max_edad:
        return c["data"], "cache"
    return None, "sin_dato"


async def _get(url: str, params: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp


async def get_pronostico_modelos() -> tuple[dict | None, str]:
    """{modelo: {"times": [...UTC naive...], "lluvia", "viento", "rafaga", "dir"}} de
    las próximas 72 h. Un modelo que Open-Meteo no devuelva simplemente no aparece
    (no vota); si no vuelve ninguno, es una falla."""

    async def fetch() -> dict:
        resp = await _get(
            _FORECAST_URL,
            {
                "latitude": settings.cienaga_lat,
                "longitude": settings.cienaga_lon,
                "hourly": "precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m",
                "models": ",".join(MODELOS),
                "forecast_days": 3,
                "timezone": "GMT",
            },
        )
        h = resp.json()["hourly"]
        out = {
            m: {
                "times": h["time"],
                "lluvia": h[f"precipitation_{m}"],
                "viento": h[f"wind_speed_10m_{m}"],
                "rafaga": h[f"wind_gusts_10m_{m}"],
                "dir": h[f"wind_direction_10m_{m}"],
            }
            for m in MODELOS
            if f"precipitation_{m}" in h and any(v is not None for v in h[f"precipitation_{m}"])
        }
        if not out:
            raise ValueError("Open-Meteo no devolvió ningún modelo")
        return out

    return await _con_cache("modelos", 3600.0, 6 * 3600.0, fetch)


async def get_oleaje_modelos() -> tuple[dict | None, str]:
    """{modelo: {"times", "ola"}} — altura significativa de ola (m), 72 h, en el mar
    frente a la Boca de la Barra (settings.mar_lat/lon)."""

    async def fetch() -> dict:
        resp = await _get(
            _MARINE_URL,
            {
                "latitude": settings.mar_lat,
                "longitude": settings.mar_lon,
                "hourly": "wave_height",
                "models": ",".join(MODELOS_OLA),
                "forecast_days": 3,
                "timezone": "GMT",
            },
        )
        h = resp.json()["hourly"]
        out = {
            m: {"times": h["time"], "ola": h[f"wave_height_{m}"]}
            for m in MODELOS_OLA
            if any(v is not None for v in h.get(f"wave_height_{m}") or [])
        }
        if not out:
            raise ValueError("Open-Meteo Marine no devolvió ningún modelo de oleaje")
        return out

    return await _con_cache("oleaje", 3600.0, 6 * 3600.0, fetch)


async def get_ciclones_activos() -> tuple[list[dict] | None, str]:
    """Ciclones activos del NHC (Atlántico y Pacífico este; el filtro por distancia
    a la CGSM lo hace avisos.py). Lista vacía = el NHC confirma que no hay ninguno."""

    async def fetch() -> list[dict]:
        storms = (await _get(_NHC_STORMS_URL)).json()["activeStorms"]
        return [
            {
                "id": s["id"],
                "nombre": s.get("name") or s["id"],
                "clasificacion": s.get("classification") or "",
                "intensidad_kt": s.get("intensity"),
                "lat": float(s["latitudeNumeric"]),
                "lon": float(s["longitudeNumeric"]),
            }
            for s in storms
            if s.get("latitudeNumeric") is not None and s.get("longitudeNumeric") is not None
        ]

    return await _con_cache("ciclones", 900.0, 3 * 3600.0, fetch)


_TAG_RE = re.compile(r"<[^>]+>")
_ENSO_RE = re.compile(r"ENSO Alert System Status:\s*(.+?)\s*Synopsis:\s*(.+?)(?<=\.)\s", re.S)


def parse_enso(raw_html: str) -> dict:
    """Estado del sistema de alerta ENSO del CPC (`El Niño Advisory`, `La Niña Watch`,
    `Not Active`, ...) + primera oración de la sinopsis."""
    texto = " ".join(html.unescape(_TAG_RE.sub(" ", raw_html)).split())
    m = _ENSO_RE.search(texto + " ")
    if not m:
        raise ValueError("discusión ENSO sin 'ENSO Alert System Status' — ¿cambió el formato?")
    estado = m.group(1).strip()
    bajo = estado.lower()
    fase = "el_nino" if "el niño" in bajo else "la_nina" if "la niña" in bajo else "neutral"
    # Watch = se espera que llegue; Advisory = ya está; "Final ... Advisory" = terminando.
    vigente = "advisory" in bajo and "final" not in bajo
    return {"estado": estado, "fase": fase, "vigente": vigente, "sinopsis": m.group(2).strip()[:300]}


async def get_estado_enso() -> tuple[dict | None, str]:
    async def fetch() -> dict:
        return parse_enso((await _get(_ENSO_URL)).text)

    # Sale una vez al mes (segundo jueves); 12 h de cache, 40 días de respaldo.
    return await _con_cache("enso", 12 * 3600.0, 40 * 86400.0, fetch)


# Cuota del periodo leída de los headers de la última respuesta (x-ratelimit-*-period).
# La cuenta es compartida con las teselas de radar del frontend: por debajo de
# `xweather_reserva_tokens` el backend deja de consultar para no dejar el mapa sin radar.
xweather_cuota: dict = {"restante": None, "limite": None, "reinicia": None}


def xweather_configurado() -> bool:
    restante = xweather_cuota["restante"]
    con_cuota = restante is None or restante >= settings.xweather_reserva_tokens
    return bool(settings.xweather_client_id and settings.xweather_client_secret) and con_cuota


async def get_xweather_pronostico() -> tuple[dict | None, str]:
    """Pronóstico horario de Xweather con la misma forma que un modelo de
    get_pronostico_modelos. 1 llamada = 1 acceso de la cuota; cache de 3 h, así que
    como mucho 8 accesos/día aunque el desempate se pida en cada refresco."""
    if not xweather_configurado():
        return None, "sin_dato"

    async def fetch() -> dict:
        resp = await _get(
            _XWEATHER_URL.format(lat=settings.cienaga_lat, lon=settings.cienaga_lon),
            {
                "filter": "1hr",
                "limit": 48,
                "fields": "periods.dateTimeISO,periods.precipMM,periods.windSpeedKPH,"
                "periods.windGustKPH,periods.windDirDEG",
                "client_id": settings.xweather_client_id,
                "client_secret": settings.xweather_client_secret,
            },
        )
        h = resp.headers
        if h.get("x-ratelimit-remaining-period", "").isdigit():
            xweather_cuota.update(
                restante=int(h["x-ratelimit-remaining-period"]),
                limite=int(h["x-ratelimit-limit-period"]) if h.get("x-ratelimit-limit-period", "").isdigit() else None,
                reinicia=h.get("x-ratelimit-reset-period"),
            )
        body = resp.json()
        if not body.get("success"):
            raise ValueError(f"Xweather respondió error: {(body.get('error') or {}).get('code')}")
        periodos = body["response"][0]["periods"]
        return {
            "times": [_fin_de_hora_utc(p["dateTimeISO"]) for p in periodos],
            "lluvia": [p.get("precipMM") for p in periodos],
            "viento": [p.get("windSpeedKPH") for p in periodos],
            "rafaga": [p.get("windGustKPH") for p in periodos],
            "dir": [p.get("windDirDEG") for p in periodos],
        }

    # 1 intento: un reintento contra Xweather también cobra token.
    return await _con_cache("xweather", 3 * 3600.0, 6 * 3600.0, fetch, intentos=1)


def _fin_de_hora_utc(iso: str) -> str:
    """Xweather etiqueta el periodo por su INICIO, Open-Meteo por su FIN: se corre 1 h
    para que la lluvia de la hora caiga en la misma etiqueta. '2026-10-31T19:00:00-05:00'
    -> '2026-11-01T01:00' (UTC naive, convención de Open-Meteo con timezone=GMT)."""
    dt = datetime.fromisoformat(iso).astimezone(timezone.utc) + timedelta(hours=1)
    return dt.strftime("%Y-%m-%dT%H:%M")
