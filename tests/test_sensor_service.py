"""Tests de trust boundary de sensores: validación de rango y filtro de frescura."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.sensor import SensorReadingIn
from app.services.sensor_service import get_latest_readings


def _reading(**overrides):
    base = {
        "sensor_id": "s1",
        # dinámico: SensorReadingIn rechaza timestamps viejos (ver
        # timestamp_within_freshness_window en app/schemas/sensor.py)
        "timestamp": datetime.now(UTC).isoformat(),
        "ph": 7.5,
        "conductivity_mscm": 10.0,
        "temperature_c": 28.0,
        "water_level_cm": 50.0,
    }
    return {**base, **overrides}


def test_ec_fuera_de_rango_rechazada():
    with pytest.raises(ValidationError):
        SensorReadingIn(**_reading(conductivity_mscm=9999))


def test_nivel_negativo_rechazado():
    with pytest.raises(ValidationError):
        SensorReadingIn(**_reading(water_level_cm=-1))


def test_ec_y_nivel_en_rango_aceptados():
    reading = SensorReadingIn(**_reading())
    assert reading.conductivity_mscm == 10.0
    assert reading.water_level_cm == 50.0


def test_get_latest_readings_filtra_activos_y_frescos():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result

    asyncio.run(get_latest_readings(db))

    stmt = db.execute.call_args.args[0]
    sql = str(stmt)
    assert "sensors.active" in sql
    assert "sensor_readings.timestamp" in sql
