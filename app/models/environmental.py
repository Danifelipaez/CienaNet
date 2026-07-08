"""Modelos ORM del dominio ambiental (KNOWLEDGE_BASE §7)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Sensor(Base):
    """Sensor IoT (ESP32) registrado y autenticado por API key."""

    __tablename__ = "sensors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    device_id: Mapped[str] = mapped_column(String(100), unique=True)
    api_key_hash: Mapped[str] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    readings: Mapped[list["SensorReading"]] = relationship(back_populates="sensor")


class SensorReading(Base):
    """Lectura puntual de un sensor IoT."""

    __tablename__ = "sensor_readings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    conductivity_mscm: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_level_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sensor: Mapped["Sensor"] = relationship(back_populates="readings")


class WeatherSnapshot(Base):
    """Snapshot meteorológico (Open-Meteo)."""

    __tablename__ = "weather_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(String(50), server_default=text("'open-meteo'"))
    estacion: Mapped[str] = mapped_column(String(50), server_default=text("'CGSM'"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SatelliteData(Base):
    """Dato satelital diario (NASA ERDDAP / Copernicus)."""

    __tablename__ = "satellite_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    sst_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    chlorophyll_mgm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExternalAlert(Base):
    """Alerta de una fuente externa (NOAA NHC, IDEAM)."""

    __tablename__ = "external_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    alert_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SedimentationZone(Base):
    """Zona de sedimentación (capa del mapa) — polígono + nivel de severidad.

    Datos sembrados a mano vía migración (igual que fishing_points): son
    datos, no esquema, se ajustan con un update directo o nueva migración.
    """

    __tablename__ = "sedimentation_zones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    nombre: Mapped[str] = mapped_column(String(100))
    polygon: Mapped[list] = mapped_column(JSONB)
    nivel: Mapped[str] = mapped_column(String(10))  # "bajo" | "medio" | "alto"
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdeamHidroReading(Base):
    """Lectura diaria agregada de una estación IDEAM en vivo (precipitación o nivel
    de río, ver `app/services/ingestion/ideam_hidro.py`). Persistida por el cron
    diario (`GET /data/latest`) como respaldo propio ante la API pública de IDEAM.
    """

    __tablename__ = "ideam_hidro_readings"
    __table_args__ = (
        UniqueConstraint("variable", "estacion", "date", name="uq_ideam_hidro_variable_estacion_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    variable: Mapped[str] = mapped_column(String(30))  # "precipitacion_mm" | "nivel_m"
    estacion: Mapped[str] = mapped_column(String(100))
    date: Mapped[date] = mapped_column(Date)
    valor: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DailySemaphore(Base):
    """Resultado del semáforo diario cacheado (con ranking IPP por zona)."""

    __tablename__ = "daily_semaphore"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    date: Mapped[date] = mapped_column(Date, unique=True)
    color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ipp_ranking: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
