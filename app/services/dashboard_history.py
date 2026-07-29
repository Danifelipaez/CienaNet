"""Series de tiempo históricas para GET /data/history."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import DailySemaphore, SatelliteData, Sensor, SensorReading, WeatherSnapshot
from app.models.messaging import CatchReport
from app.services.ingestion.ideam_hidro import get_nivel_historia, get_precipitacion_historia


async def get_history(db: AsyncSession, days: int) -> dict:
    """Retorna series de tiempo de los últimos N días desde la DB."""
    # Se lanza ya para que corra en paralelo con las queries de DB de abajo (I/O
    # de red independiente, no comparte la sesión async de SQLAlchemy).
    ideam_task = asyncio.gather(get_precipitacion_historia(days), get_nivel_historia(days))

    cutoff = datetime.now(UTC) - timedelta(days=days)
    cutoff_date = cutoff.date()

    weather_rows = (
        await db.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.timestamp >= cutoff)
            .order_by(WeatherSnapshot.timestamp)
        )
    ).scalars().all()

    semaphore_rows = (
        await db.execute(
            select(DailySemaphore)
            .where(DailySemaphore.date >= cutoff_date)
            .order_by(DailySemaphore.date)
        )
    ).scalars().all()

    satellite_rows = (
        await db.execute(
            select(SatelliteData)
            .where(SatelliteData.date >= cutoff_date)
            .order_by(SatelliteData.date)
        )
    ).scalars().all()

    catch_day = func.date(CatchReport.timestamp)
    catch_rows = (
        await db.execute(
            select(catch_day.label("date"), func.avg(CatchReport.cantidad_indice).label("avg"))
            .where(CatchReport.timestamp >= cutoff, CatchReport.cantidad_indice.isnot(None))
            .group_by(catch_day)
            .order_by(catch_day)
        )
    ).all()

    # Promedio por hora entre sensores activos — igual que aggregate_sensor_readings()
    # del snapshot, para no mezclar en la misma serie lecturas de boyas distintas.
    water_hour = func.date_trunc("hour", SensorReading.timestamp)
    water_rows = (
        await db.execute(
            select(
                water_hour.label("hour"),
                func.avg(SensorReading.ph).label("ph"),
                func.avg(SensorReading.temperature_c).label("temperature_c"),
                func.avg(SensorReading.conductivity_mscm).label("conductivity_mscm"),
            )
            .join(Sensor, SensorReading.sensor_id == Sensor.id)
            .where(SensorReading.timestamp >= cutoff, Sensor.active.is_(True))
            .group_by(water_hour)
            .order_by(water_hour)
        )
    ).all()

    ideam_precipitacion, ideam_nivel_rio = await ideam_task

    return {
        "ideam_precipitacion": ideam_precipitacion,
        "ideam_nivel_rio": ideam_nivel_rio,
        "water": [
            {
                "timestamp": r.hour.isoformat(),
                "ph": round(r.ph, 2) if r.ph is not None else None,
                "temperature_c": round(r.temperature_c, 2) if r.temperature_c is not None else None,
                "conductivity_mscm": round(r.conductivity_mscm, 2) if r.conductivity_mscm is not None else None,
            }
            for r in water_rows
        ],
        "weather": [
            {
                "timestamp": r.timestamp.isoformat(),
                "estacion": r.estacion,
                "temperature_c": r.temperature_c,
                "humidity_pct": r.humidity_pct,
                "wind_speed_kmh": r.wind_speed_kmh,
                "wind_gust_kmh": r.wind_gust_kmh,
                "precipitation_mm": r.precipitation_mm,
            }
            for r in weather_rows
        ],
        "semaphore": [
            {
                "date": r.date.isoformat(),
                "color": r.color,
                "reason": r.reason,
                "ipp_ranking": r.ipp_ranking,
            }
            for r in semaphore_rows
        ],
        "satellite": [
            {
                "date": r.date.isoformat(),
                "sst_celsius": r.sst_celsius,
                "chlorophyll_mgm3": r.chlorophyll_mgm3,
            }
            for r in satellite_rows
        ],
        "captura": [
            {"date": r.date.isoformat(), "cantidad_indice": round(r.avg, 2)}
            for r in catch_rows
        ],
    }
