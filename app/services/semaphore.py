"""Lógica del semáforo de condiciones (KNOWLEDGE_BASE §5)."""

from dataclasses import dataclass


@dataclass
class SemaphoreResult:
    color: str   # "green" | "yellow" | "red"
    emoji: str
    reason: str
    safe: bool


def evaluate(weather: dict, satellite: dict, water: dict) -> SemaphoreResult:
    wind_kmh = weather.get("wind_speed_kmh") or 0
    gust_kmh = wind_kmh * 1.4  # ponytail: estimado, Open-Meteo no entrega ráfagas
    precip_mm = weather.get("precipitation_mm") or 0
    oxygen = water.get("dissolved_oxygen_mgl")

    # ROJO — condiciones peligrosas
    if wind_kmh > 30 or gust_kmh > 45 or precip_mm > 10:
        return SemaphoreResult("red", "🔴", "Viento o lluvia peligrosa", False)
    if oxygen is not None and oxygen < 3.0:
        return SemaphoreResult("red", "🔴", "Oxígeno disuelto crítico", False)

    # AMARILLO — precaución
    sst = satellite.get("sst_celsius", 28)
    salinity = water.get("salinity_psu", 15)
    turbidity = water.get("turbidity_ntu", 50)
    if sst is not None and not (25 <= sst <= 32):
        return SemaphoreResult("yellow", "🟡", "Temperatura del agua fuera de rango", True)
    if salinity > 32 or turbidity > 120:
        return SemaphoreResult("yellow", "🟡", "Condiciones de precaución", True)
    if oxygen is not None and 3.0 <= oxygen <= 4.5:
        return SemaphoreResult("yellow", "🟡", "Oxígeno bajo, precaución", True)

    return SemaphoreResult("green", "🟢", "Condiciones favorables", True)
