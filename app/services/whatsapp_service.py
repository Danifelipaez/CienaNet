"""Cliente de envío de mensajes vía Meta WhatsApp Cloud API (docs/WHATSAPP_API.md).

Regla de CLAUDE.md: nunca loggear contenido de mensajes ni números completos —
los logs de error de este módulo solo incluyen los últimos 4 dígitos del destinatario.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"


def _mask(to: str) -> str:
    return f"***{to[-4:]}" if len(to) >= 4 else "***"


async def _post(payload: dict, to: str) -> dict | None:
    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        logger.warning("WhatsApp no configurado (faltan whatsapp_token / whatsapp_phone_number_id)")
        return None

    url = _GRAPH_URL.format(phone_number_id=settings.whatsapp_phone_number_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("Fallo al enviar mensaje WhatsApp a %s: %s", _mask(to), exc)
        return None


async def send_text_message(to: str, message: str) -> dict | None:
    """Envía un mensaje de texto simple. Solo funciona dentro de la ventana de 24h."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    return await _post(payload, to)


async def send_button_message(to: str, body: str, buttons: list[dict]) -> dict | None:
    """Envía un mensaje con hasta 3 botones de respuesta rápida.

    `buttons`: [{"id": "...", "title": "..."}, ...]
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                    for btn in buttons[:3]
                ]
            },
        },
    }
    return await _post(payload, to)


async def send_template_message(to: str, template_name: str, params: list[str] | None = None) -> dict | None:
    """Envía un template pre-aprobado (única forma de iniciar contacto fuera de la ventana de 24h)."""
    components = []
    if params:
        components.append(
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
        )
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "es"},
            "components": components,
        },
    }
    return await _post(payload, to)
