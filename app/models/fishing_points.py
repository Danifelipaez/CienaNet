"""Puntos de pesca: conocimiento territorial comunitario (no derivado de sensores).

Cargados/editados vía /admin (igual que sensors) — lat/lng nunca se exponen como
GPS exacto en respuestas públicas, ver vista Mapa del diseño CienRayas.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FishingPoint(Base):
    """Punto de pesca con rango de salinidad esperado (para calcular IPP) y especies."""

    __tablename__ = "fishing_points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    nombre: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    sal_min: Mapped[float] = mapped_column(Float)
    sal_max: Mapped[float] = mapped_column(Float)
    especies: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
