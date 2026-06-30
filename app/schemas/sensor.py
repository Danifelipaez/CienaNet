"""Pydantic schema para lecturas de sensores ESP32 (KNOWLEDGE_BASE §4.6)."""

from datetime import datetime

from pydantic import BaseModel, field_validator


class SensorReadingIn(BaseModel):
    sensor_id: str
    timestamp: datetime
    ph: float | None = None
    conductivity_mscm: float | None = None
    temperature_c: float | None = None
    water_level_cm: float | None = None

    @field_validator("ph")
    @classmethod
    def ph_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 14):
            raise ValueError("pH fuera de rango (0-14)")
        return v

    @field_validator("temperature_c")
    @classmethod
    def temp_range(cls, v: float | None) -> float | None:
        if v is not None and not (-5 <= v <= 45):
            raise ValueError("temperatura fuera de rango (-5 a 45 °C)")
        return v
