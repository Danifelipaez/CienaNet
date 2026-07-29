"""Pydantic schema para lecturas de sensores ESP32 (KNOWLEDGE_BASE §4.6)."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, field_validator

# Reusada por sensor_service.get_latest_readings() como cota de "lectura
# vieja" para el snapshot del dashboard -- un solo número, un solo lugar de
# verdad. TX_INTERVAL real de 15 min x RTC_BUFFER_SIZE=4 del firmware deja un
# peor caso de reintento legítimo de ~1h, muy por debajo de esta cota.
MAX_READING_AGE_HOURS = 6

# Tolerancia de drift de reloj del ESP32 (sincronizado por NTP solo si hay
# WiFi) -- da margen a un desfase benigno sin abrir la puerta a timestamps
# fabricados muy en el futuro (replay/manipulación en una red hostil tipo
# hotspot público).
MAX_FUTURE_SKEW_MINUTES = 5


class SensorReadingIn(BaseModel):
    sensor_id: str
    timestamp: datetime
    ph: float | None = None
    conductivity_mscm: float | None = None
    temperature_c: float | None = None
    water_level_cm: float | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_within_freshness_window(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            # el firmware siempre manda sufijo "Z" (formatIso8601 en el
            # .ino); un timestamp naive es ambiguo -- mejor rechazar que
            # asumir una zona horaria.
            raise ValueError("timestamp debe incluir offset UTC (ej. sufijo 'Z')")
        now = datetime.now(UTC)
        if v < now - timedelta(hours=MAX_READING_AGE_HOURS):
            raise ValueError(f"timestamp demasiado viejo (más de {MAX_READING_AGE_HOURS}h)")
        if v > now + timedelta(minutes=MAX_FUTURE_SKEW_MINUTES):
            raise ValueError("timestamp en el futuro")
        return v

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
