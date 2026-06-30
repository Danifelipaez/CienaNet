"""Modelos ORM de la capa WhatsApp: usuarios, conversaciones, reportes y alertas."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    """Pescador identificado por su número de WhatsApp (wa_id)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    wa_id: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comunidad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alertas_activas: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    catch_reports: Mapped[list["CatchReport"]] = relationship(back_populates="user")


class Conversation(Base):
    """Mensaje individual entrante/saliente de WhatsApp.

    Nunca loggear `body` ni `wa_id` del usuario (regla de CLAUDE.md) — esto es
    persistencia legítima para historial conversacional, no logging.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    direction: Mapped[str] = mapped_column(String(10))  # "in" | "out"
    message_type: Mapped[str] = mapped_column(String(20), server_default=text("'text'"))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="conversations")


class CatchReport(Base):
    """Reporte de captura de un pescador, recibido vía WhatsApp.

    `fishing_point_id` no lleva ForeignKeyConstraint en la migración 002 porque
    `fishing_points` se crea recién en 003 — la constraint se agrega ahí.
    """

    __tablename__ = "catch_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    fishing_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fishing_points.id"), nullable=True
    )
    especie: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cantidad_indice: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="catch_reports")


class AlertLog(Base):
    """Registro de alertas enviadas a la comunidad por WhatsApp."""

    __tablename__ = "alert_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    color: Mapped[str] = mapped_column(String(10))
    zonas: Mapped[str | None] = mapped_column(Text, nullable=True)
    canal: Mapped[str] = mapped_column(String(20), server_default=text("'whatsapp'"))
    texto: Mapped[str] = mapped_column(Text)
    destinatarios_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
