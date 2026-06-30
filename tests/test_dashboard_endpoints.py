"""Smoke tests de los endpoints del dashboard.

Mockea DB y APIs externas — verifica estructura de respuesta, no datos reales.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ── datos de prueba ───────────────────────────────────────────────────────────

MOCK_SNAPSHOT = {
    "semaphore": {"color": "green", "reason": "Condiciones favorables", "safe": True},
    "weather": {"temperature_c": 28.0, "wind_speed_kmh": 12.0, "wind_direction_deg": 90.0, "precipitation_mm": 0.0},
    "satellite": {"sst_celsius": 27.4, "chlorophyll_mgm3": 3.8, "date": "2026-06-27"},
    "sensors": [],
    "ipp_ranking": [{"zone": "Caño Clarín", "ipp": 82.5}],
    "cyclone_alerts": [],
    "updated_at": datetime.now(UTC).isoformat(),
}

MOCK_HISTORY = {
    "weather": [{"timestamp": "2026-06-29T10:00:00+00:00", "temperature_c": 28.0, "wind_speed_kmh": 12.0, "precipitation_mm": 0.0}],
    "semaphore": [{"date": "2026-06-29", "color": "green", "reason": "Condiciones favorables", "ipp_ranking": []}],
    "satellite": [{"date": "2026-06-27", "sst_celsius": 27.4, "chlorophyll_mgm3": 3.8}],
}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_db():
    """Reemplaza get_db con una sesión mock para todos los tests de este módulo."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[__import__("app.core.database", fromlist=["get_db"]).get_db] = override_get_db
    yield mock_session
    app.dependency_overrides.clear()


# ── health ────────────────────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── /data/latest ──────────────────────────────────────────────────────────────


def test_latest_retorna_200(client):
    with patch("app.api.v1.routers.data.get_latest_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = MOCK_SNAPSHOT
        resp = client.get("/api/v1/data/latest")
    assert resp.status_code == 200


def test_latest_tiene_campos_requeridos(client):
    with patch("app.api.v1.routers.data.get_latest_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = MOCK_SNAPSHOT
        data = client.get("/api/v1/data/latest").json()
    assert "semaphore" in data
    assert "weather" in data
    assert "satellite" in data
    assert "ipp_ranking" in data
    assert "updated_at" in data


def test_latest_semaphore_tiene_color(client):
    with patch("app.api.v1.routers.data.get_latest_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = MOCK_SNAPSHOT
        data = client.get("/api/v1/data/latest").json()
    assert data["semaphore"]["color"] in ("green", "yellow", "red")


# ── /data/history ─────────────────────────────────────────────────────────────


def test_history_retorna_200(client):
    with patch("app.api.v1.routers.data.get_history", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = MOCK_HISTORY
        resp = client.get("/api/v1/data/history?days=7")
    assert resp.status_code == 200


def test_history_tiene_claves(client):
    with patch("app.api.v1.routers.data.get_history", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = MOCK_HISTORY
        data = client.get("/api/v1/data/history").json()
    assert "weather" in data
    assert "semaphore" in data
    assert "satellite" in data


def test_history_days_invalido(client):
    resp = client.get("/api/v1/data/history?days=0")
    assert resp.status_code == 422  # validación Pydantic


# ── /data/zones ───────────────────────────────────────────────────────────────


def test_zones_retorna_200(client):
    resp = client.get("/api/v1/data/zones")
    assert resp.status_code == 200


def test_zones_sin_datos_retorna_lista_vacia(client):
    data = client.get("/api/v1/data/zones").json()
    assert "ipp_ranking" in data
    assert data["ipp_ranking"] == []


# ── /data/alerts ──────────────────────────────────────────────────────────────


def test_alerts_retorna_200(client):
    with patch("app.api.v1.routers.data.get_cyclone_alerts", new_callable=AsyncMock) as mock_alerts:
        mock_alerts.return_value = []
        resp = client.get("/api/v1/data/alerts")
    assert resp.status_code == 200


def test_alerts_tiene_claves(client):
    with patch("app.api.v1.routers.data.get_cyclone_alerts", new_callable=AsyncMock) as mock_alerts:
        mock_alerts.return_value = []
        data = client.get("/api/v1/data/alerts").json()
    assert "cyclones" in data
    assert "external" in data
