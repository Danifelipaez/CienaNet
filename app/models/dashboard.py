"""Modelos ORM exclusivos del dashboard interno (no WhatsApp)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func, text
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
    pregunta: Mapped[str] = mapped_column(Text)
    respuesta: Mapped[list] = mapped_column(JSONB)
    sugerencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    contexto: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
