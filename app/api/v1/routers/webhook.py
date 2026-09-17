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


@router.post("/evolution")
async def receive_webhook_evolution(request: Request, token: str = Query(default="")) -> dict:
    """Alternativa temporal a /whatsapp: recibe eventos de Evolution API
    (Baileys) mientras la verificación de negocio de Meta está pendiente (ver
    docs/WHATSAPP_API.md). Apuntar el webhook de la instancia de Evolution a
    esta URL con ?token=<settings.evolution_webhook_secret> — Evolution no
    firma sus webhooks como Meta, así que el token en la query es la única
    validación de origen.
    """
    if not settings.evolution_webhook_secret or token != settings.evolution_webhook_secret:
        raise HTTPException(status_code=403)

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored"}  # body no es JSON válido

    # Evolution es self-hosted y sin schema garantizado entre versiones/forks —
    # a diferencia de /whatsapp (Meta, formato estable), cualquier forma
    # inesperada del payload se ignora en vez de tumbar el webhook con un 500.
    try:
        if payload.get("event") != "messages.upsert":
            return {"status": "ignored"}

        data = payload.get("data", {})
        key = data.get("key", {})
        remote_jid = key.get("remoteJid", "")
        # ponytail: grupos (`@g.us`) y mensajes propios (eco de lo que el bot
        # mismo envió) quedan fuera de alcance del bot 1:1 con pescadores.
        if key.get("fromMe") or "@g.us" in remote_jid:
            return {"status": "ignored"}

        message = data.get("message") or {}
        text_body = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text")
        if not text_body:
            return {"status": "ignored"}  # no es texto plano (imagen, audio, sticker...)

        # JID completo (con dominio), no solo el número: WhatsApp expone algunos
        # contactos como `@lid` (identificador enlazado, privacidad) en vez del
        # número real (`@s.whatsapp.net`) — confirmado en pruebas reales de la
        # demo. Evolution acepta ambos como "number" al responder, pero solo si
        # se manda el JID completo; el número sin dominio de un LID no es válido.
        wa_id = remote_jid
    except (AttributeError, TypeError):
        logger.warning("Payload de Evolution con forma inesperada, ignorado")
        return {"status": "ignored"}
    async with AsyncSessionLocal() as db:
        await _process_text_message(
            wa_id, data.get("pushName"), {"id": key.get("id", ""), "text": {"body": text_body}}, db
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
