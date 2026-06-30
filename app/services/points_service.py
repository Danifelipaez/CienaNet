"""Puntos de pesca con condición/IPP actual, para la vista Mapa del dashboard.

Lee el último estado ya persistido por `_hourly_refresh` (no vuelve a llamar
APIs externas en cada request — mismo patrón que GET /data/zones).
"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import DailySemaphore, SatelliteData, WeatherSnapshot
from app.models.fishing_points import FishingPoint
from app.services.ipp import rank_points
from app.services.sensor_service import aggregate_sensor_readings, get_latest_readings


async def get_points(db: AsyncSession) -> list[dict]:
    weather_row = (
        await db.execute(select(WeatherSnapshot).order_by(desc(WeatherSnapshot.timestamp)).limit(1))
    ).scalar_one_or_none()
    satellite_row = (
        await db.execute(select(SatelliteData).order_by(desc(SatelliteData.date)).limit(1))
    ).scalar_one_or_none()
    semaphore_row = (
        await db.execute(select(DailySemaphore).order_by(desc(DailySemaphore.date)).limit(1))
    ).scalar_one_or_none()
    points = (await db.execute(select(FishingPoint).order_by(FishingPoint.nombre))).scalars().all()

    weather = {
        "wind_speed_kmh": weather_row.wind_speed_kmh if weather_row else None,
    }
    satellite = {
        "sst_celsius": satellite_row.sst_celsius if satellite_row else None,
        "chlorophyll_mgm3": satellite_row.chlorophyll_mgm3 if satellite_row else None,
    }
    semaphore_color = semaphore_row.color if semaphore_row else "green"

    readings = await get_latest_readings(db)
    water = aggregate_sensor_readings(readings)

    return rank_points(water, satellite, weather, semaphore_color, points)
