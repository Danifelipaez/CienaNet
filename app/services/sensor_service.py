"""Lógica de ingesta y consulta de lecturas de sensores ESP32 (V-04)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.environmental import Sensor, SensorReading
from app.schemas.sensor import SensorReadingIn
from app.services.derived import salinity_psu, tds_mgl


async def process_reading(reading: SensorReadingIn, sensor: Sensor, db: AsyncSession) -> None:
    """Valida y persiste una lectura de sensor. Actualiza last_seen del sensor."""
    db.add(
        SensorReading(
            sensor_id=sensor.id,
            timestamp=reading.timestamp,
            ph=reading.ph,
            conductivity_mscm=reading.conductivity_mscm,
            temperature_c=reading.temperature_c,
            water_level_cm=reading.water_level_cm,
        )
    )
    sensor.last_seen = datetime.now(UTC)
    await db.commit()


async def get_latest_readings(db: AsyncSession) -> list[SensorReading]:
    """Retorna la lectura más reciente de cada sensor activo."""
    subq = (
        select(SensorReading.sensor_id, func.max(SensorReading.timestamp).label("max_ts"))
        .group_by(SensorReading.sensor_id)
        .subquery()
    )
    result = await db.execute(
        select(SensorReading)
        .options(selectinload(SensorReading.sensor))
        .join(
            subq,
            (SensorReading.sensor_id == subq.c.sensor_id)
            & (SensorReading.timestamp == subq.c.max_ts),
        )
    )
    return list(result.scalars().all())


def aggregate_sensor_readings(readings: list[SensorReading]) -> dict:
    """Promedia los valores de agua disponibles entre todos los sensores activos."""
    if not readings:
        return {}

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    agg = {
        "ph": _avg([r.ph for r in readings if r.ph is not None]),
        "temperature_c": _avg([r.temperature_c for r in readings if r.temperature_c is not None]),
        "conductivity_mscm": _avg([r.conductivity_mscm for r in readings if r.conductivity_mscm is not None]),
        "water_level_cm": _avg([r.water_level_cm for r in readings if r.water_level_cm is not None]),
    }
    # Derivadas §10 (confianza alta): salinidad PSS-78 y TDS desde EC + temperatura.
    # Alimentan el semáforo y el IPP, que antes usaban una salinidad por defecto.
    # ponytail: derivar del promedio, no promediar derivadas — nivel dashboard, ok.
    agg["salinity_psu"] = salinity_psu(agg["conductivity_mscm"], agg["temperature_c"])
    agg["tds_mgl"] = tds_mgl(agg["conductivity_mscm"], agg["temperature_c"])
    return agg
