"""Tests de app/api/v1/routers/admin.py — registro/listado de sensores tras X-Admin-Key."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}  # ver tests/conftest.py


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_db():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()
    mock_session.refresh = AsyncMock()

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    yield mock_session
    app.dependency_overrides.clear()


def test_register_sensor_sin_admin_key_rechaza(client):
    resp = client.post("/api/v1/admin/sensors", json={"device_id": "esp32-01"})
    assert resp.status_code == 422  # falta el header requerido


def test_register_sensor_admin_key_invalida_rechaza(client):
    resp = client.post(
        "/api/v1/admin/sensors",
        json={"device_id": "esp32-01"},
        headers={"X-Admin-Key": "incorrecta"},
    )
    assert resp.status_code == 403


def test_register_sensor_ok_retorna_api_key_en_texto_plano(client, mock_db):
    resp = client.post(
        "/api/v1/admin/sensors",
        json={"device_id": "esp32-01", "location": "Tasajera"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["device_id"] == "esp32-01"
    assert body["raw_api_key"]  # se devuelve una sola vez, en texto plano
    mock_db.add.assert_called_once()


def test_register_sensor_duplicado_retorna_409(client, mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = MagicMock()  # ya existe
    resp = client.post(
        "/api/v1/admin/sensors", json={"device_id": "esp32-01"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 409


def test_list_sensors_sin_admin_key_rechaza(client):
    resp = client.get("/api/v1/admin/sensors")
    assert resp.status_code == 422


def test_list_sensors_no_expone_api_key_hash(client, mock_db):
    sensor = MagicMock(
        id="11111111-1111-1111-1111-111111111111", device_id="esp32-01", location=None, active=True
    )
    mock_db.execute.return_value.scalars.return_value.all.return_value = [sensor]
    resp = client.get("/api/v1/admin/sensors", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    body = resp.json()[0]
    assert "api_key_hash" not in body
    assert body["device_id"] == "esp32-01"
