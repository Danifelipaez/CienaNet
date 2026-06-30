"""Orquestación del snapshot ambiental y persistencia en DB (V-05)."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import (
    DailySemaphore,
    SatelliteData,
    WeatherSnapshot,
)
from app.services.ingestion.alerts_ext import get_cyclone_alerts
from app.services.ingestion.satellite import get_satellite_data
from app.services.ingestion.weather import get_weather_forecast
from app.services.ipp import rank_zones
from app.services.semaphore import evaluate
from app.services.sensor_service import aggregate_sensor_readings, get_latest_readings

logger = logging.getLogger(__name__)


async def get_latest_snapshot(db: AsyncSession) -> dict:
    """Obtiene datos de todas las fuentes y retorna el snapshot actual.

    Estrategia DB-first para satélite: evita llamadas lentas a NASA ERDDAP
    en cada cold-start de Vercel cuando ya hay datos del día en la DB.
    """
    sat_date = date.today() - timedelta(days=2)
    db_satellite = (
        await db.execute(
            select(SatelliteData).where(
                SatelliteData.date == sat_date,
                SatelliteData.source == "nasa_mur",
            ).limit(1)
        )
    ).scalar_one_or_none()

    if db_satellite:
        satellite_data = {
            "sst_celsius": db_satellite.sst_celsius,
            "chlorophyll_mgm3": db_satellite.chlorophyll_mgm3,
            "date": db_satellite.date.isoformat(),
        }
        weather_data, alerts = await asyncio.gather(
            get_weather_forecast(),
            get_cyclone_alerts(),
        )
    else:
        weather_data, satellite_data, alerts = await asyncio.gather(
            get_weather_forecast(),
            get_satellite_data(),
            get_cyclone_alerts(),
        )

    # DB: lecturas de sensores (sesión separada del gather externo)
    readings = await get_latest_readings(db)

    water = aggregate_sensor_readings(readings)
    semaphore = evaluate(weather_data, satellite_data, water)
    ipp = rank_zones(water, satellite_data)
    today = date.today()

    # Persistencia secuencial (una sola sesión async, no concurrent)
    await _save_weather(db, weather_data)
    await _save_satellite(db, satellite_data, today)
    await _upsert_semaphore(db, today, semaphore, ipp)

    return {
        "semaphore": {
            "color": semaphore.color,
            "reason": semaphore.reason,
            "safe": semaphore.safe,
        },
        "weather": weather_data,
        "satellite": satellite_data,
        "sensors": [
            {
                "zone": r.sensor.location if r.sensor else None,
                "ph": r.ph,
                "temperature_c": r.temperature_c,
                "conductivity_mscm": r.conductivity_mscm,
            }
            for r in readings
        ],
        "ipp_ranking": ipp,
        "cyclone_alerts": alerts,
        "updated_at": datetime.now(UTC).isoformat(),
    }


async def get_history(db: AsyncSession, days: int) -> dict:
    """Retorna series de tiempo de los últimos N días desde la DB."""
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

    return {
        "weather": [
            {
                "timestamp": r.timestamp.isoformat(),
                "temperature_c": r.temperature_c,
                "wind_speed_kmh": r.wind_speed_kmh,
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
    }


# ── helpers privados ──────────────────────────────────────────────────────────


async def _save_weather(db: AsyncSession, data: dict) -> None:
    if not any(v is not None for v in data.values()):
        return
    # Dedup: no insertar si ya hay un snapshot en los últimos 60 min
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    recent = (
        await db.execute(
            select(WeatherSnapshot).where(WeatherSnapshot.timestamp >= cutoff).limit(1)
        )
    ).scalar_one_or_none()
    if recent:
        return
    db.add(
        WeatherSnapshot(
            timestamp=datetime.now(UTC),
            temperature_c=data.get("temperature_c"),
            wind_speed_kmh=data.get("wind_speed_kmh"),
            wind_direction_deg=data.get("wind_direction_deg"),
            precipitation_mm=data.get("precipitation_mm"),
        )
    )
    await db.commit()


async def _save_satellite(db: AsyncSession, data: dict, today: date) -> None:
    sat_date_str = data.get("date") or today.isoformat()
    sat_date = date.fromisoformat(sat_date_str)

    existing = (
        await db.execute(
            select(SatelliteData).where(
                SatelliteData.date == sat_date,
                SatelliteData.source == "nasa_mur",
            )
        )
    ).scalar_one_or_none()

    if existing:
        return

    db.add(
        SatelliteData(
            source="nasa_mur",
            date=sat_date,
            sst_celsius=data.get("sst_celsius"),
            chlorophyll_mgm3=data.get("chlorophyll_mgm3"),
        )
    )
    await db.commit()


async def _upsert_semaphore(db: AsyncSession, today: date, semaphore, ipp: list) -> None:
    row = (
        await db.execute(select(DailySemaphore).where(DailySemaphore.date == today))
    ).scalar_one_or_none()

    if row:
        row.color = semaphore.color
        row.reason = semaphore.reason
        row.ipp_ranking = ipp
    else:
        db.add(
            DailySemaphore(
                date=today,
                color=semaphore.color,
                reason=semaphore.reason,
                ipp_ranking=ipp,
            )
        )
    await db.commit()
