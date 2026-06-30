"""Envía alertas proactivas por WhatsApp cuando cambia el color del semáforo.

Se llama después de cada refresco del snapshot ambiental (ver app/main.py).
Dedup: solo notifica si el color difiere del último alert_log — evita
reenviar la misma alerta cada hora mientras la condición no cambia.
"""

import logging

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.messaging import AlertLog, User
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
# ponytail: un solo template genérico. Debe crearse y aprobarse en Meta Business
# Manager con este nombre antes de que el envío funcione en producción.
_ALERT_TEMPLATE = "alerta_condicion"


async def maybe_send_alert(semaphore: dict, db: AsyncSession) -> None:
    """Si el color cambió desde la última alerta registrada, notifica a suscritos."""
    last = (
        await db.execute(select(AlertLog).order_by(desc(AlertLog.created_at)).limit(1))
    ).scalar_one_or_none()

    color = semaphore["color"]
    if last and last.color == color:
        return  # mismo estado que la última alerta, no repetir
    if color == "green" and (not last or last.color == "green"):
        return  # nada que avisar si ya estaba en verde

    recipients = (
        await db.execute(select(User).where(User.alertas_activas.is_(True)))
    ).scalars().all()

    texto = f"{_EMOJI.get(color, '')} {semaphore['reason']}"
    sent_count = 0
    for user in recipients:
        result = await whatsapp_service.send_template_message(
            user.wa_id, _ALERT_TEMPLATE, params=[semaphore["reason"]]
        )
        if result:
            sent_count += 1

    db.add(
        AlertLog(
            color=color,
            zonas="Todas",
            canal="whatsapp",
            texto=texto,
            destinatarios_count=sent_count,
        )
    )
    await db.commit()
    logger.info("Alerta %s enviada a %d destinatarios", color, sent_count)
