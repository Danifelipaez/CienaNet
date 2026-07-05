"""Índice de Potencial Pesquero por zona (KNOWLEDGE_BASE §6)."""

from app.models.fishing_points import FishingPoint

# ponytail: oxígeno disuelto y turbidez no tienen sensor real (no hay columnas en
# SensorReading) — antes entraban con un default fijo (constante para las 6 zonas,
# sin aportar señal) y con peso 0.35 entre los dos. Se quitan hasta que exista un
# sensor real; el peso restante se redistribuye proporcionalmente entre las 4 señales
# que sí varían con el dato observado.
WEIGHTS = {
    "sst": 0.31,
    "salinity": 0.31,
    "chlorophyll": 0.23,
    "ph": 0.15,
}

ZONES = [
    {"name": "Boca de la Barra",     "sal_min": 20, "sal_max": 36},
    {"name": "Nueva Venecia",         "sal_min":  8, "sal_max": 22},
    {"name": "Buenavista",           "sal_min":  5, "sal_max": 18},
    {"name": "Caño Clarín",          "sal_min":  2, "sal_max": 12},
    {"name": "Tasajera/Puebloviejo", "sal_min":  3, "sal_max": 15},
    {"name": "Suroccidente",         "sal_min":  0, "sal_max":  8},
]


def _score_sst(v: float) -> float:
    return 100 if 26 <= v <= 30 else (60 if 24 <= v <= 32 else 20)


def _score_salinity(v: float, zone_min: float, zone_max: float) -> float:
    return 100 if zone_min <= v <= zone_max else 0


def _score_chlorophyll(v: float) -> float:
    return min(100, v * 10)  # >10 mg/m³ = saturación


def _score_ph(v: float) -> float:
    return 100 if 7.0 <= v <= 8.5 else 30


def calculate_ipp(water: dict, satellite: dict, zone: dict) -> float:
    scores = {
        "sst":         _score_sst(satellite.get("sst_celsius", 28)),
        "salinity":    _score_salinity(water.get("salinity_psu", 15), zone["sal_min"], zone["sal_max"]),
        "chlorophyll": _score_chlorophyll(satellite.get("chlorophyll_mgm3", 4.5)),
        "ph":          _score_ph(water.get("ph", 7.5)),
    }
    return round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS), 1)


def rank_zones(water: dict, satellite: dict) -> list[dict]:
    results = [
        {"zone": z["name"], "ipp": calculate_ipp(water, satellite, z)}
        for z in ZONES
    ]
    return sorted(results, key=lambda x: x["ipp"], reverse=True)


def point_condition(ipp: float, semaphore_color: str) -> str:
    """Condición semáforo de un punto de pesca puntual (vista Mapa).

    No hay red de sensores por punto — solo varía la salinidad esperada
    (calculate_ipp). Si el semáforo general ya es rojo (viento/lluvia
    peligrosa), aplica a toda la ciénaga por igual; si no, cada punto se
    colorea según qué tan bien encaja su rango de salinidad con las
    condiciones actuales.
    """
    if semaphore_color == "red":
        return "rojo"
    if ipp >= 70:
        return "verde"
    if ipp >= 40:
        return "amarillo"
    return "rojo"


def rank_points(
    water: dict, satellite: dict, weather: dict, semaphore_color: str, points: list[FishingPoint]
) -> list[dict]:
    """Igual que rank_zones pero sobre fishing_points reales (FishingPoint ORM)."""
    results = [
        {
            "id": str(p.id),
            "nombre": p.nombre,
            "lat": p.lat,
            "lng": p.lng,
            "especies": p.especies or [],
            "observacion": p.observacion,
            "temp": satellite.get("sst_celsius"),
            "clorofila": satellite.get("chlorophyll_mgm3"),
            "viento": weather.get("wind_speed_kmh"),
            "salinidad": water.get("salinity_psu"),
            "tds": water.get("tds_mgl"),
            "ipp": (ipp := calculate_ipp(water, satellite, {"sal_min": p.sal_min, "sal_max": p.sal_max})),
            "condicion": point_condition(ipp, semaphore_color),
        }
        for p in points
    ]
    return sorted(results, key=lambda x: x["ipp"], reverse=True)
