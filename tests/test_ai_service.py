"""Tests del proveedor de IA (Gemini). Mockea httpx — sin red."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services import ai_service
from app.services.ai_service import GeminiProvider, _StubProvider, get_ai_provider


def _fake_client(*, json_body: dict | None = None, raises: Exception | None = None):
    """Devuelve un mock usable como `async with httpx.AsyncClient(...) as c`."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=raises)
    resp.json = MagicMock(return_value=json_body or {})

    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory, client


def _gemini_text(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_reply_text_devuelve_string():
    factory, _ = _fake_client(json_body=_gemini_text("Hola pescador"))
    with patch.object(ai_service.httpx, "AsyncClient", factory):
        out = asyncio.run(GeminiProvider().reply_text("sys", "hola"))
    assert out == "Hola pescador"


def test_reply_text_incluye_history():
    factory, client = _fake_client(json_body=_gemini_text("ok"))
    history = [{"role": "user", "parts": [{"text": "antes"}]}]
    with patch.object(ai_service.httpx, "AsyncClient", factory):
        asyncio.run(GeminiProvider().reply_text("sys", "ahora", history=history))
    sent = client.post.call_args.kwargs["json"]["contents"]
    # history + mensaje actual, en orden
    assert sent[0]["parts"][0]["text"] == "antes"
    assert sent[-1]["parts"][0]["text"] == "ahora"


def test_reply_text_none_en_fallo():
    factory, _ = _fake_client(raises=httpx.HTTPError("boom"))
    with patch.object(ai_service.httpx, "AsyncClient", factory):
        out = asyncio.run(GeminiProvider().reply_text("sys", "hola"))
    assert out is None


def test_answer_structured_devuelve_parrafos():
    body = _gemini_text(json.dumps({"parrafos": [{"tipo": "texto", "html": "dato"}], "sugerencia": "s"}))
    factory, _ = _fake_client(json_body=body)
    with patch.object(ai_service.httpx, "AsyncClient", factory):
        out = asyncio.run(GeminiProvider().answer_structured("sys", "pregunta"))
    assert out["parrafos"][0]["tipo"] == "texto"
    assert out["sugerencia"] == "s"


def test_answer_structured_limitacion_en_fallo():
    factory, _ = _fake_client(raises=httpx.HTTPError("boom"))
    with patch.object(ai_service.httpx, "AsyncClient", factory):
        out = asyncio.run(GeminiProvider().answer_structured("sys", "pregunta"))
    assert out["parrafos"][0]["tipo"] == "limitaciones"


def test_stub_no_revienta():
    assert asyncio.run(_StubProvider().reply_text("s", "u")) is None
    assert asyncio.run(_StubProvider().answer_structured("s", "u"))["parrafos"]


def test_provider_selection_por_api_key():
    ai_service._provider = None
    with patch.object(ai_service.settings, "ai_api_key", ""):
        assert isinstance(get_ai_provider(), _StubProvider)
    ai_service._provider = None
    with patch.object(ai_service.settings, "ai_api_key", "k"):
        assert isinstance(get_ai_provider(), GeminiProvider)
    ai_service._provider = None
