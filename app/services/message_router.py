"""Enruta mensajes entrantes de WhatsApp: clasifica intención y responde.

Intenciones cubiertas (keyword matching — ponytail: suficiente para el MVP,
subir a NLU/IA real si el volumen de mensajes no reconocidos crece):
saludo, consulta de condición, suscripción/baja de alertas, reporte de
captura. Todo lo demás cae al AIProvider (stub hasta que se conecte uno real).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.messaging import CatchReport, Conversation, User
from app.services import whatsapp_service
from app.services.ai_service import get_ai_provider
from app.services.dashboard_service import camaron_moonrise_hint, get_latest_snapshot

logger = logging.getLogger(__name__)

_ESPECIES = {"camarón": "camarón", "camaron": "camarón", "lisa": "lisa", "mojarra": "mojarra", "róbalo": "róbalo", "robalo": "róbalo"}

_SALUDO = (
    "¡Hola! Soy CienRayas 🐟. Puedo contarte cómo está el agua hoy, "
    "suscribirte a alertas, o recibir tu reporte de pesca.\n\n"
    "Escribe *condición*, *alertas* o cuéntame qué pescaste."
)
_NO_ENTENDI = (
    "No entendí tu mensaje. Escribe *condición* para saber cómo está el agua, "
    "o *alertas* para suscribirte."
)
_SEMAFORO_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


async def _get_or_create_user(wa_id: str, nombre: str | None, db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.wa_id == wa_id))).scalar_one_or_none()
    if user:
        user.last_message_at = datetime.now(UTC)
        if nombre and not user.nombre:
            user.nombre = nombre
    else:
        user = User(wa_id=wa_id, nombre=nombre, last_message_at=datetime.now(UTC))
        db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _log_message(
    user_id, direction: str, body: str, db: AsyncSession, wa_message_id: str | None = None
) -> None:
    db.add(Conversation(user_id=user_id, direction=direction, body=body, wa_message_id=wa_message_id))
    await db.commit()


async def _condicion_actual(db: AsyncSession) -> str:
    snapshot = await get_latest_snapshot(db)
    sem = snapshot["semaphore"]
    emoji = _SEMAFORO_EMOJI.get(sem["color"], "")
    return f"{emoji} Condición actual: {sem['reason']}."


async def _recent_history(user_id, db: AsyncSession) -> list[dict]:
    """Últimos mensajes de la conversación como contexto para Gemini (orden cronológico).

    Mapea direction 'in'→'user', 'out'→'model' (roles de la API de Gemini).
    Excluye el mensaje actual, que el caller ya agrega aparte.
    """
    rows = (
        await db.execute(
            select(Conversation.direction, Conversation.body)
            .where(Conversation.user_id == user_id, Conversation.body.isnot(None))
            .order_by(desc(Conversation.created_at))
            .limit(settings.ai_history_turns + 1)
        )
    ).all()
    history = [
        {"role": "user" if d == "in" else "model", "parts": [{"text": b}]}
        for d, b in reversed(rows)
    ]
    return history[:-1]  # quita el mensaje actual (el más reciente)


def _detect_especie(text_lower: str) -> str | None:
    for keyword, label in _ESPECIES.items():
        if keyword in text_lower:
            return label
    return None


_PREGUNTA_MARKERS = ("?", "dónde", "donde", "cuándo", "cuando", "estará", "estarán", "estaran", "hay camar")


def _es_pregunta(text_lower: str) -> bool:
    """Distingue una pregunta ('¿dónde hay camarón?') de un reporte de captura
    ('hoy pesqué camarón') — ambos matchean _detect_especie por igual."""
    return any(m in text_lower for m in _PREGUNTA_MARKERS)


async def handle_incoming_text(
    wa_id: str, nombre: str | None, text: str, wa_message_id: str, db: AsyncSession
) -> None:
    """Procesa un mensaje de texto entrante y envía la respuesta correspondiente."""
    user = await _get_or_create_user(wa_id, nombre, db)
    await _log_message(user.id, "in", text, db, wa_message_id)

    text_lower = text.strip().lower()

    if text_lower in {"hola", "buenas", "hi", "start"}:
        reply = _SALUDO
    elif "condici" in text_lower or "agua" in text_lower:
        reply = await _condicion_actual(db)
    elif "alerta" in text_lower and ("no" in text_lower or "desactiv" in text_lower or "baja" in text_lower):
        user.alertas_activas = False
        await db.commit()
        reply = "Listo, ya no recibirás alertas automáticas."
    elif "alerta" in text_lower:
        user.alertas_activas = True
        await db.commit()
        reply = "Listo, quedaste suscrito a alertas. Escribe *alertas no* para darte de baja."
    elif (especie := _detect_especie(text_lower)) is not None and not _es_pregunta(text_lower):
        db.add(CatchReport(user_id=user.id, especie=especie, timestamp=datetime.now(UTC)))
        await db.commit()
        reply = f"Gracias por reportar tu pesca de {especie} 🎣. Esto ayuda a toda la comunidad."
    else:
        # ponytail: llamada a Gemini inline (Vercel serverless no tiene background
        # tasks confiables). Mover a cola solo si la latencia molesta.
        system = (
            "Eres el asistente de CienRayas para pescadores artesanales de la "
            "Ciénaga Grande de Santa Marta. Responde breve y claro, en español."
        )
        if "camar" in text_lower:
            system += f"\n{camaron_moonrise_hint()}"
        ai_reply = await get_ai_provider().reply_text(
            system=system,
            user=text,
            history=await _recent_history(user.id, db),
        )
        reply = ai_reply or _NO_ENTENDI

    sent = await whatsapp_service.send_text_message(wa_id, reply)
    sent_id = (sent or {}).get("messages", [{}])[0].get("id") if sent else None
    await _log_message(user.id, "out", reply, db, wa_message_id=sent_id)
