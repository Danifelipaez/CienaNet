"""Tests de POST /api/v1/webhook/evolution — el adaptador de Evolution API
(Baileys) usado mientras la verificación de negocio de Meta está pendiente.
Cubre el parser del payload de messages.upsert, que es la parte no trivial
(la validación HMAC de Meta ya tiene su propio flujo en /whatsapp)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

URL = "/api/v1/webhook/evolution"


@pytest.fixture
def client():
    return TestClient(app)


def _payload(text_field: dict, from_me: bool = False, remote_jid: str = "573001234567@s.whatsapp.net"):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": from_me, "id": "3EB0ABC"},
            "pushName": "Pescador",
            "message": text_field,
        },
    }


@pytest.fixture(autouse=True)
def evolution_secret(monkeypatch):
    monkeypatch.setattr(settings, "evolution_webhook_secret", "topsecret")


def _mock_session():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def test_token_invalido_rechaza(client):
    resp = client.post(f"{URL}?token=incorrecto", json=_payload({"conversation": "hola"}))
    assert resp.status_code == 403


def test_sin_secreto_configurado_rechaza(client, monkeypatch):
    monkeypatch.setattr(settings, "evolution_webhook_secret", "")
    resp = client.post(f"{URL}?token=", json=_payload({"conversation": "hola"}))
    assert resp.status_code == 403


def test_mensaje_de_texto_llama_handle_incoming_text(client):
    with patch("app.api.v1.routers.webhook.AsyncSessionLocal", return_value=_mock_session()), \
         patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(f"{URL}?token=topsecret", json=_payload({"conversation": "hola pescador"}))

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_handle.assert_awaited_once()
    kwargs = mock_handle.call_args.kwargs
    # JID completo (no solo el número): necesario para poder responderle de
    # vuelta a contactos `@lid` (ver comentario en webhook.py).
    assert kwargs["wa_id"] == "573001234567@s.whatsapp.net"
    assert kwargs["nombre"] == "Pescador"
    assert kwargs["text"] == "hola pescador"


def test_contacto_lid_usa_jid_completo_como_wa_id(client):
    with patch("app.api.v1.routers.webhook.AsyncSessionLocal", return_value=_mock_session()), \
         patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(
            f"{URL}?token=topsecret",
            json=_payload({"conversation": "hola"}, remote_jid="125958640140481@lid"),
        )

    assert resp.status_code == 200
    assert mock_handle.call_args.kwargs["wa_id"] == "125958640140481@lid"


def test_extended_text_message_tambien_se_extrae(client):
    with patch("app.api.v1.routers.webhook.AsyncSessionLocal", return_value=_mock_session()), \
         patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(
            f"{URL}?token=topsecret",
            json=_payload({"extendedTextMessage": {"text": "respondiendo a algo"}}),
        )

    assert resp.status_code == 200
    assert mock_handle.call_args.kwargs["text"] == "respondiendo a algo"


def test_eco_propio_se_ignora(client):
    with patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(
            f"{URL}?token=topsecret",
            json=_payload({"conversation": "hola"}, from_me=True),
        )

    assert resp.json() == {"status": "ignored"}
    mock_handle.assert_not_awaited()


def test_mensaje_de_grupo_se_ignora(client):
    with patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(
            f"{URL}?token=topsecret",
            json=_payload({"conversation": "hola"}, remote_jid="12036@g.us"),
        )

    assert resp.json() == {"status": "ignored"}
    mock_handle.assert_not_awaited()


def test_mensaje_sin_texto_se_ignora(client):
    with patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(f"{URL}?token=topsecret", json=_payload({"imageMessage": {}}))

    assert resp.json() == {"status": "ignored"}
    mock_handle.assert_not_awaited()


def test_evento_distinto_de_messages_upsert_se_ignora(client):
    with patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(f"{URL}?token=topsecret", json={"event": "connection.update", "data": {}})

    assert resp.json() == {"status": "ignored"}
    mock_handle.assert_not_awaited()


def test_data_con_forma_inesperada_no_truena(client):
    # Evolution es self-hosted sin schema garantizado entre versiones/forks —
    # un "data" en formato de lista (estilo v1 viejo) no debe tumbar el webhook.
    with patch("app.api.v1.routers.webhook.handle_incoming_text", new_callable=AsyncMock) as mock_handle:
        resp = client.post(
            f"{URL}?token=topsecret",
            json={"event": "messages.upsert", "data": [{"key": {}, "message": {}}]},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}
    mock_handle.assert_not_awaited()


def test_body_no_json_no_truena(client):
    resp = client.post(
        f"{URL}?token=topsecret",
        content=b"esto no es json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}
