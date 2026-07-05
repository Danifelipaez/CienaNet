"""Proveedor de IA (Google AI Studio / Gemini) para NLU y generación de respuestas.

Dos formas de salida, una por consumidor:
- reply_text()        → str  para WhatsApp (texto plano)
- answer_structured() → dict {parrafos, sugerencia} para el dashboard (JSON mode)

El resto del código nunca importa el SDK/REST concreto: para cambiar de proveedor,
implementar AIProvider y ajustar get_ai_provider().

Regla de CLAUDE.md: nunca loggear contenido de mensajes de usuarios — los logs de
error de este módulo no incluyen el prompt ni la respuesta.
"""

import json
import logging
from typing import Protocol, runtime_checkable

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Schema que refleja app/schemas/dashboard.py (AIParrafo / AIDato) para el JSON mode.
_STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "parrafos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": ["texto", "datos", "limitaciones"]},
                    "titulo": {"type": "string", "nullable": True},
                    "html": {"type": "string", "nullable": True},
                    "items": {
                        "type": "array",
                        "nullable": True,
                        "items": {
                            "type": "object",
                            "properties": {
                                "v": {"type": "string"},
                                "d": {"type": "string"},
                                "fuente": {"type": "string"},
                            },
                            "required": ["v", "d", "fuente"],
                        },
                    },
                },
                "required": ["tipo"],
            },
        },
        "sugerencia": {"type": "string", "nullable": True},
    },
    "required": ["parrafos"],
}

_LIMITACION = {
    "parrafos": [
        {"tipo": "limitaciones", "titulo": None, "html": "La IA no está disponible en este momento.", "items": None}
    ],
    "sugerencia": None,
}


@runtime_checkable
class AIProvider(Protocol):
    async def reply_text(self, system: str, user: str, history: list[dict] | None = None) -> str | None:
        """Respuesta en texto plano para WhatsApp. None si el proveedor falla."""
        ...

    async def answer_structured(
        self, system: str, user: str, history: list[dict] | None = None
    ) -> dict:
        """Respuesta estructurada {parrafos, sugerencia} para el dashboard.

        `history`: turnos previos del hilo del usuario (roles user/model de Gemini),
        para que las preguntas de seguimiento tengan memoria de la conversación.
        """
        ...


class _StubProvider:
    """Sin proveedor configurado: no lanza errores, degrada suave."""

    async def reply_text(self, system: str, user: str, history: list[dict] | None = None) -> str | None:
        return None

    async def answer_structured(
        self, system: str, user: str, history: list[dict] | None = None
    ) -> dict:
        return _LIMITACION


class GeminiProvider:
    """Cliente REST de Google AI Studio (Generative Language API) vía httpx."""

    async def _generate(self, system: str, contents: list[dict], *, json_schema: dict | None = None) -> str | None:
        """POST a Gemini. Devuelve el texto del primer candidate, o None si algo falla."""
        url = _GENERATE_URL.format(model=settings.ai_model)
        # thinkingBudget=0 desactiva el "thinking" de Gemini 3: sin él la latencia salta
        # esporádicamente por encima del timeout (→ fallback) y cuesta más tokens. Este
        # caso de uso (Q&A ambiental) no necesita razonamiento extendido.
        generation_config: dict = {"thinkingConfig": {"thinkingBudget": 0}}
        if json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = json_schema
        payload: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": generation_config,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url, params={"key": settings.ai_api_key}, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            logger.error("Fallo al llamar a Gemini (%s): %s", settings.ai_model, exc)
            return None

    async def reply_text(self, system: str, user: str, history: list[dict] | None = None) -> str | None:
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": user}]})
        return await self._generate(system, contents)

    async def answer_structured(
        self, system: str, user: str, history: list[dict] | None = None
    ) -> dict:
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": user}]})
        raw = await self._generate(system, contents, json_schema=_STRUCTURED_SCHEMA)
        if not raw:
            return _LIMITACION
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Gemini devolvió JSON inválido: %s", exc)
            return _LIMITACION
        result.setdefault("parrafos", _LIMITACION["parrafos"])
        result.setdefault("sugerencia", None)
        return result


_provider: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    """Proveedor de IA activo (cacheado). GeminiProvider si hay API key, si no stub."""
    global _provider
    if _provider is None:
        _provider = GeminiProvider() if settings.ai_api_key else _StubProvider()
    return _provider
