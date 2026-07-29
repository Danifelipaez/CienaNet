"""Tests de app/services/whatsapp_service.py — el único camino por el que el bot
llega a los pescadores. Sin tests antes (ver auditoría de deuda técnica)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.services import whatsapp_service


def _mock_client(response=None, raise_exc=None):
    client = AsyncMock()
    if raise_exc:
        client.post = AsyncMock(side_effect=raise_exc)
    else:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = response if response is not None else {"messages": [{"id": "wamid.1"}]}
        client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_sin_credenciales_no_llama_a_meta(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_token", "")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "")
    with patch("app.services.whatsapp_service.httpx.AsyncClient") as mock_cls:
        result = asyncio.run(whatsapp_service.send_text_message("+570000000", "hola"))
    assert result is None
    mock_cls.assert_not_called()


def test_send_text_message_arma_payload_correcto(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123")
    client = _mock_client()
    with patch("app.services.whatsapp_service.httpx.AsyncClient", return_value=client):
        result = asyncio.run(whatsapp_service.send_text_message("+570000000", "hola pescador"))

    assert result == {"messages": [{"id": "wamid.1"}]}
    payload = client.post.call_args.kwargs["json"]
    assert payload["to"] == "+570000000"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "hola pescador"


def test_send_button_message_trunca_a_3_botones(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123")
    client = _mock_client()
    botones = [{"id": str(i), "title": f"op{i}"} for i in range(5)]
    with patch("app.services.whatsapp_service.httpx.AsyncClient", return_value=client):
        asyncio.run(whatsapp_service.send_button_message("+570000000", "elige", botones))

    payload = client.post.call_args.kwargs["json"]
    assert len(payload["interactive"]["action"]["buttons"]) == 3


def test_send_template_message_arma_componentes_solo_si_hay_params(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123")
    client = _mock_client()
    with patch("app.services.whatsapp_service.httpx.AsyncClient", return_value=client):
        asyncio.run(whatsapp_service.send_template_message("+570000000", "alerta_semaforo", ["rojo"]))

    payload = client.post.call_args.kwargs["json"]
    assert payload["template"]["name"] == "alerta_semaforo"
    assert payload["template"]["components"][0]["parameters"][0]["text"] == "rojo"


def test_send_template_message_sin_params_no_manda_componentes(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123")
    client = _mock_client()
    with patch("app.services.whatsapp_service.httpx.AsyncClient", return_value=client):
        asyncio.run(whatsapp_service.send_template_message("+570000000", "bienvenida"))

    payload = client.post.call_args.kwargs["json"]
    assert payload["template"]["components"] == []


def test_fallo_de_red_retorna_none_y_no_truena(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123")
    client = _mock_client(raise_exc=Exception("timeout"))
    with patch("app.services.whatsapp_service.httpx.AsyncClient", return_value=client):
        result = asyncio.run(whatsapp_service.send_text_message("+570000000", "hola"))
    assert result is None


def test_mask_solo_expone_los_ultimos_4_digitos():
    # Regla de CLAUDE.md: nunca loggear números de teléfono completos.
    assert whatsapp_service._mask("+573001234567") == "***4567"
    assert whatsapp_service._mask("12") == "***"
