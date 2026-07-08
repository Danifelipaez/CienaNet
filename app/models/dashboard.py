"""Modelos ORM exclusivos del dashboard interno (no WhatsApp)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIConversation(Base):
    """Historial de preguntas/respuestas de la vista 'Pregunta a la IA' del dashboard.

    Independiente de `conversations` (WhatsApp) — uso interno admin, no pescadores.
    """

    __tablename__ = "ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Identidad blanda del cliente (UUID de localStorage, enviado como X-User-Id).
    # Aísla hilo e historial por usuario. Índice compuesto (user_id, created_at) en la migración 007.
    user_id: Mapped[str] = mapped_column(String(64), server_default=text("'legacy'"))
    # Clave de agrupación del hilo: todos los turnos de una misma conversación la
    # comparten. La mintea el cliente al abrir un chat nuevo. Índice (user_id,
    # conversation_id, created_at) en la migración 009.
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    pregunta: Mapped[str] = mapped_column(Text)
    respuesta: Mapped[list] = mapped_column(JSONB)
    sugerencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    contexto: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
