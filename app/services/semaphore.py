"""Lógica del semáforo de condiciones (KNOWLEDGE_BASE §5)."""

from dataclasses import dataclass


@dataclass
class SemaphoreResult:
    color: str   # "green" | "yellow" | "red"
    emoji: str
    reason: str
    safe: bool


def evaluate(weather: dict, satellite: dict, water: dict) -> SemaphoreResult:
    # ponytail: oxígeno disuelto y turbidez no tienen sensor real todavía (ver
    # ipp.py) — sin dato real, los checks caían siempre en el mismo default y
    # nunca disparaban. Se quitan hasta que exista un sensor real.
    wind_kmh = weather.get("wind_speed_kmh") or 0
    gust_kmh = wind_kmh * 1.4  # ponytail: estimado, Open-Meteo no entrega ráfagas
    precip_mm = weather.get("precipitation_mm") or 0

    # ROJO — condiciones peligrosas
    if wind_kmh > 30 or gust_kmh > 45 or precip_mm > 10:
        return SemaphoreResult("red", "🔴", "Viento o lluvia peligrosa", False)

    # AMARILLO — precaución
    sst = satellite.get("sst_celsius", 28)
    salinity = water.get("salinity_psu", 15)
    if sst is not None and not (25 <= sst <= 32):
        return SemaphoreResult("yellow", "🟡", "Temperatura del agua fuera de rango", True)
    if salinity > 32:
        return SemaphoreResult("yellow", "🟡", "Condiciones de precaución", True)

    return SemaphoreResult("green", "🟢", "Condiciones favorables", True)
