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

    @field_validator("conductivity_mscm")
    @classmethod
    def ec_range(cls, v: float | None) -> float | None:
        # 0-80 mS/cm: agua de mar ronda 53 mS/cm a 25°C, margen para la
        # hipersalinidad de la CGSM. Atrapa la sonda desconectada (pega en 0
        # o en un riel tipo 1000+), no control de calidad fino.
        if v is not None and not (0 <= v <= 80):
            raise ValueError("conductividad fuera de rango (0-80 mS/cm)")
        return v

    @field_validator("water_level_cm")
    @classmethod
    def level_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 500):
            raise ValueError("nivel de agua fuera de rango (0-500 cm)")
        return v
