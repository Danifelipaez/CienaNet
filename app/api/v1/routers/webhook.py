"""Webhook de Meta WhatsApp Cloud API: verificación + recepción de mensajes.

Ver docs/WHATSAPP_API.md. Validación HMAC-SHA256 obligatoria (regla 1 de CLAUDE.md)
antes de procesar cualquier payload — nunca confiar en un POST sin firma válida.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import verify_hmac_meta
from app.services.message_router import handle_incoming_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> PlainTextResponse:
    """Meta llama esto una vez al configurar el webhook en el dashboard."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403)


@router.post("/whatsapp")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
) -> dict:
    """Recibe eventos de mensajes. Solo procesa mensajes de tipo texto por ahora.

    ponytail: botones/listas/audio quedan para cuando el bot los necesite —
    hoy el flujo entero (saludo/condición/alertas/reporte) es texto plano.
    """
    raw_body = await request.body()
    if not verify_hmac_meta(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Firma inválida")

    payload = await request.json()
    async with AsyncSessionLocal() as db:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {c["wa_id"]: c.get("profile", {}).get("name") for c in value.get("contacts", [])}
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        continue
                    wa_id = message["from"]
                    await _process_text_message(
                        wa_id, contacts.get(wa_id), message, db
                    )

    return {"status": "ok"}


async def _process_text_message(wa_id: str, nombre: str | None, message: dict, db: AsyncSession) -> None:
    try:
        await handle_incoming_text(
            wa_id=wa_id,
            nombre=nombre,
            text=message["text"]["body"],
            wa_message_id=message["id"],
            db=db,
        )
    except Exception as exc:
        logger.error("Error procesando mensaje entrante: %s", exc)
