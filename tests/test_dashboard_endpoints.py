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
    "water": {"ph": 7.8, "temperature_c": 28.0, "conductivity_mscm": 5.2, "water_level_cm": 45.0, "salinity_psu": 12.3, "tds_mgl": 3100.0},
    "sensors": [],
    "ipp_ranking": [{"zone": "Caño Clarín", "ipp": 82.5}],
    "cyclone_alerts": [],
    "updated_at": datetime.now(UTC).isoformat(),
}

MOCK_HISTORY = {
    "weather": [{"timestamp": "2026-06-29T10:00:00+00:00", "temperature_c": 28.0, "wind_speed_kmh": 12.0, "precipitation_mm": 0.0}],
    "captura": [{"date": "2026-06-29", "cantidad_indice": 55.0}],
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
    mock_result.all.return_value = []  # _load_thread usa execute(...).all() directo
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()  # AsyncSession.add() es síncrono, no una coroutine

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[__import__("app.core.database", fromlist=["get_db"]).get_db] = override_get_db
    yield mock_session
    app.dependency_overrides.clear()


# ── health ────────────────────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


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
    assert "captura" in data


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


# ── /dashboard/sedimentation ─────────────────────────────────────────────────


def test_sedimentation_retorna_200(client):
    with patch(
        "app.api.v1.routers.dashboard.get_sedimentation_zones", new_callable=AsyncMock
    ) as mock_zones:
        mock_zones.return_value = [
            {"id": "z1", "nombre": "Caño X", "polygon": [[10.0, -74.0]], "nivel": "alto", "observacion": None}
        ]
        data = client.get("/api/v1/dashboard/sedimentation").json()
    assert "zonas" in data
    assert data["zonas"][0]["nivel"] == "alto"


# ── /dashboard/ai/ask ─────────────────────────────────────────────────────────


def test_ai_ask_requiere_admin_key(client):
    resp = client.post("/api/v1/dashboard/ai/ask", json={"pregunta": "¿hola?"})
    assert resp.status_code == 422  # faltan headers requeridos (X-Admin-Key / X-User-Id)


def test_ai_ask_requiere_user_id(client):
    """Con admin key válida pero sin X-User-Id → 422 (identidad de usuario obligatoria)."""
    resp = client.post(
        "/api/v1/dashboard/ai/ask",
        json={"pregunta": "¿hola?"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert resp.status_code == 422


def test_ai_ask_rechaza_admin_key_invalida(client):
    resp = client.post(
        "/api/v1/dashboard/ai/ask",
        json={"pregunta": "¿hola?"},
        headers={"X-Admin-Key": "incorrecta", "X-User-Id": "u1"},
    )
    assert resp.status_code == 403


def test_ai_ask_stub_retorna_parrafos(client):
    # Fuerza el stub explícitamente: el .env real puede traer AI_API_KEY, y no
    # queremos que el test golpee la API de Gemini de verdad ni dependa del
    # _provider global (que otros tests resetean).
    from app.services.ai_service import _StubProvider

    with patch(
        "app.api.v1.routers.dashboard.get_latest_snapshot", new_callable=AsyncMock
    ) as mock_snap, patch(
        "app.api.v1.routers.dashboard.get_ai_provider", return_value=_StubProvider()
    ):
        mock_snap.return_value = MOCK_SNAPSHOT
        data = client.post(
            "/api/v1/dashboard/ai/ask",
            json={"pregunta": "¿cómo está la ciénaga?"},
            headers={"X-Admin-Key": "test-admin-key", "X-User-Id": "u1"},
        ).json()
    assert "parrafos" in data
    assert data["parrafos"][0]["tipo"] == "limitaciones"  # stub → limitación


# ── /dashboard/ai/history ────────────────────────────────────────────────────


def test_ai_history_sin_datos_retorna_lista_vacia(client):
    data = client.get(
        "/api/v1/dashboard/ai/history",
        headers={"X-Admin-Key": "test-admin-key", "X-User-Id": "u1"},
    ).json()
    assert data == {"historial": []}


def test_ai_history_requiere_admin_key(client):
    resp = client.get("/api/v1/dashboard/ai/history")
    assert resp.status_code == 422


# ── DELETE /dashboard/ai/history/{id} ────────────────────────────────────────


def test_ai_history_delete_ok(client):
    resp = client.delete(
        "/api/v1/dashboard/ai/history/11111111-1111-1111-1111-111111111111",
        headers={"X-Admin-Key": "test-admin-key", "X-User-Id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_ai_history_delete_id_invalido(client):
    resp = client.delete(
        "/api/v1/dashboard/ai/history/no-es-uuid",
        headers={"X-Admin-Key": "test-admin-key", "X-User-Id": "u1"},
    )
    assert resp.status_code == 422  # el path param uuid.UUID no valida


def test_ai_history_delete_requiere_admin_key(client):
    resp = client.delete(
        "/api/v1/dashboard/ai/history/11111111-1111-1111-1111-111111111111",
        headers={"X-User-Id": "u1"},
    )
    assert resp.status_code == 422


# ── memoria de hilo por usuario (helpers) ─────────────────────────────────────


def test_parrafos_to_text_aplana():
    from app.api.v1.routers.dashboard import _parrafos_to_text

    parrafos = [
        {"tipo": "texto", "html": "hola mundo"},
        {"tipo": "datos", "titulo": "Datos", "items": [{"v": "27°C", "d": "SST", "fuente": "MODIS"}]},
    ]
    out = _parrafos_to_text(parrafos, "¿siguiente?")
    assert "hola mundo" in out
    assert "27°C" in out and "MODIS" in out
    assert "Sugerencia: ¿siguiente?" in out


def test_load_thread_alterna_roles_en_orden_cronologico():
    """El hilo reenviado a Gemini alterna user/model y va de más antiguo a más nuevo."""
    from app.api.v1.routers import dashboard

    result = MagicMock()
    # execute(...).all() devuelve filas en orden desc (más reciente primero)
    result.all.return_value = [
        ("q2", [{"tipo": "texto", "html": "a2"}], None),
        ("q1", [{"tipo": "texto", "html": "a1"}], None),
    ]
    db = AsyncMock()
    db.execute.return_value = result

    import asyncio
    import uuid

    hist = asyncio.run(dashboard._load_thread("user-x", uuid.uuid4(), db))
    assert [h["role"] for h in hist] == ["user", "model", "user", "model"]
    assert hist[0]["parts"][0]["text"] == "q1"  # cronológico: q1 primero
    assert hist[-1]["parts"][0]["text"] == "a2"  # a2 al final


def test_ai_history_agrupa_turnos_por_conversacion():
    """Dos turnos del mismo hilo → una sola conversación con 2 turnos; el hilo con
    actividad más reciente va primero y el título es la primera pregunta del hilo."""
    import uuid
    from datetime import datetime, timezone

    from app.api.v1.routers import dashboard

    conv_a = uuid.uuid4()
    conv_b = uuid.uuid4()

    def row(cid, q, secs):
        r = MagicMock()
        r.id = uuid.uuid4()
        r.conversation_id = cid
        r.pregunta = q
        r.respuesta = [{"tipo": "texto", "html": "r"}]
        r.sugerencia = None
        r.created_at = datetime(2026, 7, 8, 12, 0, secs, tzinfo=timezone.utc)
        return r

    # Orden desc (más reciente primero), como lo devuelve la query.
    scalars = MagicMock()
    scalars.all.return_value = [
        row(conv_b, "b1", 30),  # hilo B, más reciente
        row(conv_a, "a2", 20),  # hilo A, turno 2
        row(conv_a, "a1", 10),  # hilo A, turno 1 (título)
    ]
    result = MagicMock()
    result.scalars.return_value = scalars
    db = AsyncMock()
    db.execute.return_value = result

    import asyncio

    out = asyncio.run(dashboard.ai_history(20, db, "user-x", None))
    hist = out["historial"]
    assert [c.id for c in hist] == [str(conv_b), str(conv_a)]  # B primero (más reciente)
    assert hist[1].titulo == "a1"  # título = primera pregunta cronológica
    assert [t.pregunta for t in hist[1].turnos] == ["a1", "a2"]  # cronológico dentro del hilo
