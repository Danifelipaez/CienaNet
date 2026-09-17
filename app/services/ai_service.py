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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import ai_tools

logger = logging.getLogger(__name__)

_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Tope de idas y vueltas del loop de function-calling — corta si el modelo no
# deja de pedir tools (ponytail: secuencial, un functionCall por turno; Gemini
# puede pedir varios en paralelo, pero el MVP solo procesa el primero).
_MAX_TOOL_ROUNDS = 4

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
    async def reply_text(
        self, system: str, user: str, history: list[dict] | None = None, *, db: AsyncSession | None = None
    ) -> str | None:
        """Respuesta en texto plano para WhatsApp. None si el proveedor falla.

        `db`: si se pasa, el proveedor puede invocar el catálogo de consultas
        generales de ai_tools.py (histórico, condición actual, etc.) en vez de
        limitarse al contexto ya incluido en `system`. Sin `db`, no hay tools.
        """
        ...

    async def answer_structured(
        self, system: str, user: str, history: list[dict] | None = None, *, db: AsyncSession | None = None
    ) -> dict:
        """Respuesta estructurada {parrafos, sugerencia} para el dashboard.

        `history`: turnos previos del hilo del usuario (roles user/model de Gemini),
        para que las preguntas de seguimiento tengan memoria de la conversación.
        `db`: igual que en reply_text — habilita tool-calling si se pasa.
        """
        ...


class _StubProvider:
    """Sin proveedor configurado: no lanza errores, degrada suave."""

    async def reply_text(
        self, system: str, user: str, history: list[dict] | None = None, *, db: AsyncSession | None = None
    ) -> str | None:
        return None

    async def answer_structured(
        self, system: str, user: str, history: list[dict] | None = None, *, db: AsyncSession | None = None
    ) -> dict:
        return _LIMITACION


class GeminiProvider:
    """Cliente REST de Google AI Studio (Generative Language API) vía httpx."""

    async def _post(self, payload: dict) -> dict | None:
        """POST a Gemini. Devuelve el JSON de la respuesta, o None si falla la red/HTTP."""
        url = _GENERATE_URL.format(model=settings.ai_model)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Header, no query param: además de evitar que la key quede en
                # texto plano en logs de error (URL completa en la excepción),
                # algunas keys de AI Studio devuelven 401 con ?key= y solo
                # aceptan el header (confirmado en vivo contra la API real).
                resp = await client.post(
                    url, headers={"x-goog-api-key": settings.ai_api_key}, json=payload
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.error("Fallo al llamar a Gemini (%s): %s", settings.ai_model, exc)
            return None

    async def _generate(
        self,
        system: str,
        contents: list[dict],
        *,
        json_schema: dict | None = None,
        db: AsyncSession | None = None,
    ) -> str | None:
        """Llama a Gemini y resuelve tool-calls localmente si el modelo los pide.

        Con `db`, declara el catálogo de ai_tools.py como functionDeclarations; si
        el modelo responde con un functionCall en vez de texto, ejecuta el handler
        correspondiente y reenvía el resultado como functionResponse, repitiendo
        hasta _MAX_TOOL_ROUNDS veces (corta y devuelve None si el modelo no para de
        pedir tools, en vez de loopear indefinido).
        """
        # ponytail: sin thinkingConfig — thinkingBudget=0 rompía TODAS las llamadas
        # (400 INVALID_ARGUMENT) desde que el alias "-latest" rodó a gemini-3.5-flash-lite,
        # que ya no acepta ese valor. Retomar la optimización de latencia/tokens solo si
        # se confirma manualmente qué valores de thinkingBudget acepta el modelo vigente.
        generation_config: dict = {}
        if json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = json_schema
        payload: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": generation_config,
        }
        if db is not None:
            payload["tools"] = [{"functionDeclarations": ai_tools.as_gemini_declarations()}]

        for _ in range(_MAX_TOOL_ROUNDS):
            data = await self._post(payload)
            if data is None:
                return None
            try:
                parts = data["candidates"][0]["content"]["parts"]
            except (KeyError, IndexError) as exc:
                logger.error("Respuesta de Gemini sin contenido (%s): %s", settings.ai_model, exc)
                return None

            # Se guarda el part completo (no solo functionCall): el modelo vigente
            # (gemini-3.5-flash-lite, "thinking") adjunta un thoughtSignature junto
            # al functionCall y exige recibirlo de vuelta tal cual al reenviar el
            # historial, o rechaza con 400 INVALID_ARGUMENT — confirmado en vivo.
            call_part = next((p for p in parts if "functionCall" in p), None)
            if call_part is None:
                return parts[0].get("text") if parts else None
            call = call_part["functionCall"]

            handler = ai_tools.get_handler(call["name"]) if db is not None else None
            result = await handler(db, call.get("args") or {}) if handler else {"error": "tool desconocida"}
            contents.append({"role": "model", "parts": [call_part]})
            # role "function" ya no es válido en el modelo vigente (gemini-3.5-flash-lite,
            # detrás del alias "-latest"): rechaza con 400 INVALID_ARGUMENT y pide "USER"
            # en su lugar — confirmado en vivo contra la API real.
            contents.append(
                {"role": "user", "parts": [{"functionResponse": {"name": call["name"], "response": result}}]}
            )
            payload["contents"] = contents

        logger.warning("Gemini no dejó de pedir tools tras %d turnos", _MAX_TOOL_ROUNDS)
        return None

    async def reply_text(
        self, system: str, user: str, history: list[dict] | None = None, *, db: AsyncSession | None = None
    ) -> str | None:
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": user}]})
        return await self._generate(system, contents, db=db)

    async def answer_structured(
        self, system: str, user: str, history: list[dict] | None = None, *, db: AsyncSession | None = None
    ) -> dict:
        contents = list(history or [])
        contents.append({"role": "user", "parts": [{"text": user}]})
        raw = await self._generate(system, contents, json_schema=_STRUCTURED_SCHEMA, db=db)
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
