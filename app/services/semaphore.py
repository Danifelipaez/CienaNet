"""Lógica del semáforo de condiciones (KNOWLEDGE_BASE §5)."""

from dataclasses import dataclass, field


@dataclass
class SemaphoreResult:
    color: str   # "green" | "yellow" | "red"
    emoji: str
    reason: str
    safe: bool
    datos_faltantes: list[str] = field(default_factory=list)


_WIND_MAX = 30.0  # km/h sostenido — VALIDAR CON PESCADORES (canoa de madera, no meteorología general)
_GUST_MAX = 45.0  # km/h en ráfaga
_PRECIP_MAX = 10.0  # mm


def evaluate(weather: dict, satellite: dict, water: dict) -> SemaphoreResult:
    # ponytail: oxígeno disuelto y turbidez no tienen sensor real todavía (ver
    # ipp.py) — sin dato real, los checks caían siempre en el mismo default y
    # nunca disparaban. Se quitan hasta que exista un sensor real.
    wind_kmh = weather.get("wind_speed_kmh")
    gust_kmh = weather.get("wind_gust_kmh")  # Open-Meteo sí la entrega (wind_gusts_10m)
    precip_mm = weather.get("precipitation_mm")

    # Desconocido ≠ seguro: si no hay ni viento ni lluvia, el check de rojo de
    # abajo nunca corrió — no hay base para afirmar que es seguro salir. Antes
    # esto caía en verde por default (num() rellenaba con un valor inventado).
    if wind_kmh is None and precip_mm is None:
        return SemaphoreResult(
            "yellow",
            "🟡",
            "Sin datos de viento ni lluvia — no puedo confirmar si es seguro salir",
            False,
            datos_faltantes=["viento", "lluvia"],
        )

    # ROJO — condiciones peligrosas. Cada check solo corre si hay dato: sin
    # ráfaga (fila vieja, o la API no la devolvió) no se inventa una.
    if (
        (wind_kmh is not None and wind_kmh > _WIND_MAX)
        or (gust_kmh is not None and gust_kmh > _GUST_MAX)
        or (precip_mm is not None and precip_mm > _PRECIP_MAX)
    ):
        return SemaphoreResult("red", "🔴", "Viento o lluvia peligrosa", False)

    # AMARILLO — precaución. Sin dato real, el check simplemente no corre (antes
    # num() rellenaba sst=28/salinity=15, indistinguible de una medición).
    sst = satellite.get("sst_celsius")
    salinity = water.get("salinity_psu")
    if sst is not None and not (25 <= sst <= 32):
        return SemaphoreResult("yellow", "🟡", "Temperatura del agua fuera de rango", True)
    if salinity is not None and salinity > 32:
        return SemaphoreResult("yellow", "🟡", "Condiciones de precaución", True)

    return SemaphoreResult("green", "🟢", "Condiciones favorables", True)
