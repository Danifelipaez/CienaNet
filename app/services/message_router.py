"""Enruta mensajes entrantes de WhatsApp: clasifica intención y responde.

Intenciones cubiertas (keyword matching — ponytail: suficiente para el MVP,
subir a NLU/IA real si el volumen de mensajes no reconocidos crece):
saludo, consulta de condición, suscripción/baja de alertas, reporte de
captura. Todo lo demás cae al AIProvider (stub hasta que se conecte uno real).
"""

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.messaging import CatchReport, Conversation, User
from app.services import whatsapp_service
from app.services.ai_context import build_ai_context, camaron_moonrise_hint
from app.services.ai_service import get_ai_provider
from app.services.condicion_message import _mensaje_condicion
from app.services.points_service import get_points
from app.services.snapshot_service import read_persisted

logger = logging.getLogger(__name__)

_ESPECIES = {"camarón": "camarón", "camaron": "camarón", "lisa": "lisa", "mojarra": "mojarra", "róbalo": "róbalo", "robalo": "róbalo"}

_SALUDO = (
    "¡Hola! Soy CienRayas 🐟. Puedo contarte cómo está el agua hoy, dónde pescar, "
    "suscribirte a alertas, o recibir tu reporte de pesca.\n\n"
    "Escribe *condición*, *dónde pesco*, *alertas* o cuéntame qué pescaste."
)
_NO_ENTENDI = (
    "No entendí tu mensaje. Escribe *condición* para saber cómo está el agua, "
    "*dónde pesco* para ver las mejores zonas, o *alertas* para suscribirte."
)


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
    estado = await read_persisted(db)
    return _mensaje_condicion(estado)


_DONDE_MARKERS = (
    "dónde pesc", "donde pesc", "dónde hay", "donde hay", "a dónde", "a donde",
    "qué zona", "que zona", "mejor zona", "dónde tiro", "donde tiro",
)
_SIN_ZONAS = "Todavía no tengo suficientes datos para recomendarte una zona. Escribe *condición* para ver cómo está el agua."


def _es_donde_pesco(text_lower: str) -> bool:
    return any(m in text_lower for m in _DONDE_MARKERS)


async def _donde_pesco(db: AsyncSession, text_lower: str) -> str:
    """Top 3 puntos de pesca por IPP. Nombres de punto ('Boquerón', 'La Ahuyama'),
    no de zona ('Suroccidente') — es el vocabulario que los pescadores ya usan.
    Sin fishing_points sembrados, cae a las 6 zonas del ranking IPP."""
    puntos = await get_points(db)
    if puntos:
        nombres = [p["nombre"] for p in puntos[:3]]
    else:
        estado = await read_persisted(db)
        nombres = [z["zone"] for z in (estado.get("ipp_ranking") or [])[:3]]

    if not nombres:
        return _SIN_ZONAS

    reply = f"Las mejores zonas hoy son: {', '.join(nombres)}."
    if "camar" in text_lower:
        reply += f" {camaron_moonrise_hint()}"
    return reply


_CANTIDAD_RE = re.compile(r"\b(\d{1,4})\b")  # ponytail: primer número del mensaje;
# no distingue unidad (libras/kg/unidades) ni descarta números que no son cantidad
# ("pesqué en el caño 3"). Sube a botones con rangos si el ruido molesta — además
# normalizaría la unidad, que hoy nadie declara.


def _cantidad_reportada(text: str) -> float | None:
    match = _CANTIDAD_RE.search(text)
    return float(match.group(1)) if match else None


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
    elif _es_donde_pesco(text_lower):
        reply = await _donde_pesco(db, text_lower)
    elif (especie := _detect_especie(text_lower)) is not None and not _es_pregunta(text_lower):
        cantidad = _cantidad_reportada(text)
        db.add(
            CatchReport(
                user_id=user.id, especie=especie, cantidad_indice=cantidad, timestamp=datetime.now(UTC)
            )
        )
        await db.commit()
        reply = f"Gracias por reportar tu pesca de {especie} 🎣. Esto ayuda a toda la comunidad."
    else:
        # ponytail: llamada a Gemini inline (Vercel serverless no tiene background
        # tasks confiables). Mover a cola solo si la latencia molesta.
        estado = await read_persisted(db)
        system = (
            "Eres el asistente de CienRayas para pescadores artesanales de la "
            "Ciénaga Grande de Santa Marta. Responde en español simple, máximo 4 "
            "oraciones, sin jerga técnica, y termina siempre con una recomendación "
            "de acción concreta. Usa solo estos datos, no inventes valores: "
            f"{build_ai_context(estado)}"
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
