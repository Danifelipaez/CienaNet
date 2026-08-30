"""Orquestación del snapshot ambiental (camino de escritura, V-05).

Los guardados en DB viven en dashboard_persistence.py, la serie histórica en
dashboard_history.py y el contexto de IA en ai_context.py — este módulo pasaba
el límite de 300 líneas de docs/GUARDRAILS.md mezclando las cuatro cosas.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import SatelliteData
from app.core.config import settings
from app.services.dashboard_persistence import (
    _save_ideam_hidro,
    _save_satellite,
    _save_weather,
    _upsert_semaphore,
)
from app.services.ingestion.alerts_ext import get_cyclone_alerts
from app.services.ingestion.ideam_hidro import get_nivel_historia, get_precipitacion_historia
from app.services.ingestion.satellite import get_satellite_data
from app.services.ingestion.weather import get_weather_forecast, get_wind_gust_forecast
from app.services.ipp import rank_zones
from app.services.semaphore import evaluate
from app.services.sensor_service import aggregate_sensor_readings, get_latest_readings
from app.services.signals import anoxia_risk, pulso_agua_dulce, vendaval_risk
from app.services.trends import get_trends

logger = logging.getLogger(__name__)

# Ventana de respaldo IDEAM: el cron corre 1 vez/día (Vercel) — unos días de
# solape cubren el rezago propio de la fuente (~2 días) sin recorrer meses.
_IDEAM_BACKFILL_DAYS = 7


async def get_latest_snapshot(db: AsyncSession) -> dict:
    """Obtiene datos de todas las fuentes y retorna el snapshot actual.

    Estrategia DB-first para satélite: evita llamadas lentas a NASA ERDDAP
    en cada cold-start de Vercel cuando ya hay datos del día en la DB.
    """
    # Se lanza ya para que corra en paralelo con el resto (I/O de red
    # independiente, no comparte la sesión async de SQLAlchemy).
    ideam_task = asyncio.gather(
        get_precipitacion_historia(_IDEAM_BACKFILL_DAYS),
        get_nivel_historia(_IDEAM_BACKFILL_DAYS),
    )

    sat_date = date.today() - timedelta(days=2)
    db_satellite = (
        await db.execute(
            select(SatelliteData).where(
                SatelliteData.date == sat_date,
                SatelliteData.source == "nasa_mur",
            ).limit(1)
        )
    ).scalar_one_or_none()

    tasajera_task = get_weather_forecast(settings.tasajera_lat, settings.tasajera_lon)

    if db_satellite:
        # Si ya está en DB fue guardado por _save_satellite, que nunca persiste un
        # baseline como si fuera medición (ver más abajo) — NULL en la columna sí
        # significa "no hubo dato", nunca "medido".
        satellite_data = {
            "sst_celsius": db_satellite.sst_celsius,
            "chlorophyll_mgm3": db_satellite.chlorophyll_mgm3,
            "date": db_satellite.date.isoformat(),
            "por_zona": db_satellite.por_zona or {},
            "origen": {
                "sst_celsius": "medido" if db_satellite.sst_celsius is not None else "sin_dato",
                "chlorophyll_mgm3": "medido" if db_satellite.chlorophyll_mgm3 is not None else "sin_dato",
            },
        }
        weather_data, tasajera_weather, alerts, wind_forecast = await asyncio.gather(
            get_weather_forecast(),
            tasajera_task,
            get_cyclone_alerts(),
            get_wind_gust_forecast(),
        )
    else:
        weather_data, tasajera_weather, satellite_data, alerts, wind_forecast = await asyncio.gather(
            get_weather_forecast(),
            tasajera_task,
            get_satellite_data(),
            get_cyclone_alerts(),
            get_wind_gust_forecast(),
        )

    # "origen" viaja dentro de cada dict de ingesta (medido/cache/baseline/sin_dato)
    # hasta acá. Se extrae a un bloque aparte para el snapshot; en particular debe
    # salir de weather_data/tasajera_weather ANTES de _save_weather, cuyo check de
    # "¿hay algún valor no-None?" contaría el string de origen como dato real.
    weather_origen = weather_data.pop("origen", "sin_dato")
    tasajera_origen = tasajera_weather.pop("origen", "sin_dato")
    satellite_origen = satellite_data.get("origen") or {}

    # DB: lecturas de sensores (sesión separada del gather externo)
    readings = await get_latest_readings(db)

    water = aggregate_sensor_readings(readings)
    semaphore = evaluate(weather_data, satellite_data, water)
    ipp = rank_zones(water, satellite_data)
    today = date.today()

    ideam_precipitacion, ideam_nivel_rio = await ideam_task

    # Persistencia secuencial (una sola sesión async, no concurrent). Cada guardado
    # va envuelto: get_latest_snapshot() es el camino de ESCRITURA — lo llaman el
    # cron/scheduler horario y GET /data/latest — un fallo de un guardado (p.ej.
    # migración pendiente en esta DB) no debe tumbar el resto de guardados de este
    # mismo snapshot. El bot de WhatsApp NO llama esta función: lee lo ya persistido
    # vía snapshot_service.read_persisted() (cero red, cero escrituras por mensaje).
    try:
        await _save_weather(db, weather_data, "CGSM")
        await _save_weather(db, tasajera_weather, "Tasajera")
    except Exception as exc:
        logger.warning("No se pudo guardar snapshot de clima en DB: %s", exc)
        await db.rollback()
    try:
        await _save_satellite(db, satellite_data, today)
    except Exception as exc:
        logger.warning("No se pudo guardar dato satelital en DB: %s", exc)
        await db.rollback()
    try:
        await _upsert_semaphore(db, today, semaphore, ipp)
    except Exception as exc:
        logger.warning("No se pudo guardar semáforo diario en DB: %s", exc)
        await db.rollback()
    try:
        await _save_ideam_hidro(db, ideam_precipitacion, ideam_nivel_rio)
    except Exception as exc:
        logger.warning("No se pudo guardar respaldo IDEAM en DB: %s", exc)
        await db.rollback()

    # Después de persistir, para que refleje lo que este mismo ciclo acaba de
    # guardar. Cero llamadas de red — agrega sobre lo que ya está en DB.
    tendencias = await get_trends(db)

    # Señales compuestas (ver app/services/signals.py). anoxia/pulso_agua_dulce son
    # ESTIMACIONES (combinan varias fuentes con umbrales no validados) — solo
    # dashboard por ahora: el riesgo de un falso positivo (día de pesca perdido,
    # credibilidad quemada) es asimétrico frente al de un falso negativo. El bot
    # tiene el mecanismo listo (condicion_message._ANOXIA_EN_BOT) pero apagado.
    # vendaval es distinto: umbral directo sobre un número real de Open-Meteo, sin
    # combinar fuentes — por eso sí dispara WhatsApp (maybe_send_wind_alert, ver
    # app/main.py y docs/ALERTAS_VENDAVAL.md).
    senales = {
        "anoxia": anoxia_risk(satellite_data, weather_data, water),
        "pulso_agua_dulce": pulso_agua_dulce(
            tendencias.get("lluvia_72h_mm"), water.get("salinity_psu")
        ),
        "vendaval": vendaval_risk(wind_forecast, settings.vendaval_gust_threshold_kmh),
    }

    return {
        "semaphore": {
            "color": semaphore.color,
            "reason": semaphore.reason,
            "safe": semaphore.safe,
        },
        "weather": weather_data,
        "tasajera_weather": tasajera_weather,
        "ideam_precipitacion": ideam_precipitacion,
        "ideam_nivel_rio": ideam_nivel_rio,
        "satellite": satellite_data,
        "water": water,
        "sensors": [
            {
                "zone": r.sensor.location if r.sensor else None,
                "ph": r.ph,
                "temperature_c": r.temperature_c,
                "conductivity_mscm": r.conductivity_mscm,
                "water_level_cm": r.water_level_cm,
            }
            for r in readings
        ],
        "ipp_ranking": ipp,
        "cyclone_alerts": alerts,
        "tendencias": tendencias,
        "senales": senales,
        "origen": {
            "weather": weather_origen,
            "tasajera_weather": tasajera_origen,
            "satellite": satellite_origen,
            "water": "medido" if water else "sin_dato",
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }
