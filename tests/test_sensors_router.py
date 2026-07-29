"""Tests de app/api/v1/routers/sensors.py — POST /sensors/ingest tras X-Api-Key."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_current_sensor
from app.core.database import get_db
from app.main import app
from app.models.environmental import Sensor

VALID_READING = {
    "sensor_id": "esp32-01",
    # dinámico: con la validación de frescura de timestamp, un literal fijo
    # se vuelve una bomba de tiempo en cuanto el reloj real se aleje de esa
    # fecha (ver app/schemas/sensor.py::timestamp_within_freshness_window).
    "timestamp": datetime.now(UTC).isoformat(),
    "ph": 7.6,
    "temperature_c": 28.0,
}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_db():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # sin sensor -> API key inválida
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    yield mock_session
    app.dependency_overrides.clear()


def test_ingest_sin_api_key_rechaza(client):
    resp = client.post("/api/v1/sensors/ingest", json=VALID_READING)
    assert resp.status_code == 422  # falta el header requerido


def test_ingest_api_key_invalida_rechaza(client):
    resp = client.post(
        "/api/v1/sensors/ingest", json=VALID_READING, headers={"X-Api-Key": "no-existe"}
    )
    assert resp.status_code == 403


def test_ingest_lectura_fuera_de_rango_rechaza(client):
    sensor = Sensor(id=uuid.uuid4(), device_id="esp32-01", api_key_hash="x", active=True)
    app.dependency_overrides[get_current_sensor] = lambda: sensor
    resp = client.post(
        "/api/v1/sensors/ingest",
        json={**VALID_READING, "ph": 20.0},
        headers={"X-Api-Key": "valida"},
    )
    assert resp.status_code == 422  # validación Pydantic (rango 0-14), ver schemas/sensor.py


def test_ingest_ok_persiste_y_actualiza_last_seen(client, mock_db):
    sensor = Sensor(id=uuid.uuid4(), device_id="esp32-01", api_key_hash="x", active=True)
    app.dependency_overrides[get_current_sensor] = lambda: sensor
    resp = client.post(
        "/api/v1/sensors/ingest", json=VALID_READING, headers={"X-Api-Key": "valida"}
    )
    assert resp.status_code == 201
    assert resp.json() == {"status": "ok"}
    mock_db.add.assert_called_once()
    assert sensor.last_seen is not None


def test_ingest_timestamp_muy_viejo_rechaza(client):
    sensor = Sensor(id=uuid.uuid4(), device_id="esp32-01", api_key_hash="x", active=True)
    app.dependency_overrides[get_current_sensor] = lambda: sensor
    stale_ts = (datetime.now(UTC) - timedelta(hours=8)).isoformat()
    resp = client.post(
        "/api/v1/sensors/ingest",
        json={**VALID_READING, "timestamp": stale_ts},
        headers={"X-Api-Key": "valida"},
    )
    assert resp.status_code == 422


def test_ingest_timestamp_futuro_rechaza(client):
    sensor = Sensor(id=uuid.uuid4(), device_id="esp32-01", api_key_hash="x", active=True)
    app.dependency_overrides[get_current_sensor] = lambda: sensor
    future_ts = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    resp = client.post(
        "/api/v1/sensors/ingest",
        json={**VALID_READING, "timestamp": future_ts},
        headers={"X-Api-Key": "valida"},
    )
    assert resp.status_code == 422


def test_ingest_timestamp_reintento_legitimo_acepta(client, mock_db):
    # simula el buffer RTC del firmware reenviando una lectura de hace ~1h
    # (peor caso real: TX_INTERVAL 15min x RTC_BUFFER_SIZE 4)
    sensor = Sensor(id=uuid.uuid4(), device_id="esp32-01", api_key_hash="x", active=True)
    app.dependency_overrides[get_current_sensor] = lambda: sensor
    retry_ts = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    resp = client.post(
        "/api/v1/sensors/ingest",
        json={**VALID_READING, "timestamp": retry_ts},
        headers={"X-Api-Key": "valida"},
    )
    assert resp.status_code == 201


def test_ingest_sensor_id_no_coincide_rechaza(client):
    sensor = Sensor(id=uuid.uuid4(), device_id="esp32-01", api_key_hash="x", active=True)
    app.dependency_overrides[get_current_sensor] = lambda: sensor
    resp = client.post(
        "/api/v1/sensors/ingest",
        json={**VALID_READING, "sensor_id": "esp32-99"},
        headers={"X-Api-Key": "valida"},
    )
    assert resp.status_code == 422
