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

# lat/lng: 3 de 6 medidas en campo (docs/KNOWLEDGE_BASE.md §12 — Tasajera,
# Buenavista, Nueva Venecia); las otras 3 son estimadas y están marcadas abajo
# — VALIDAR CON DIEGO vía DG-05 (docs/TAREAS_EQUIPO.md), que ya produce
# data/zones.geojson con las 6 zonas. No se derivan del seed de fishing_points
# (alembic/versions/003): ese seed es "comunitario ilustrativo, no coincide con
# las coordenadas medidas" (KNOWLEDGE_BASE.md §12) — lavaría dato no validado
# dentro de algo que después se presenta como posición satelital.
ZONES = [
    {"name": "Boca de la Barra",     "sal_min": 20, "sal_max": 36, "lat": 10.985,     "lng": -74.345},     # ponytail: estimada
    {"name": "Nueva Venecia",         "sal_min":  8, "sal_max": 22, "lat": 10.828694,  "lng": -74.574500},  # medida
    {"name": "Buenavista",           "sal_min":  5, "sal_max": 18, "lat": 10.841333,  "lng": -74.510139},  # medida
    {"name": "Caño Clarín",          "sal_min":  2, "sal_max": 12, "lat": 10.900,     "lng": -74.640},     # ponytail: estimada
    {"name": "Tasajera/Puebloviejo", "sal_min":  3, "sal_max": 15, "lat": 10.976111,  "lng": -74.325833},  # medida
    {"name": "Suroccidente",         "sal_min":  0, "sal_max":  8, "lat": 10.700,     "lng": -74.590},     # ponytail: estimada
]


def _trapezoid(v: float, cero_lo: float, opt_lo: float, opt_hi: float, cero_hi: float) -> float:
    """Score 0-100: 0 fuera de [cero_lo, cero_hi], 100 en la meseta [opt_lo, opt_hi],
    lineal en los hombros. Los 4 scores del IPP son esta misma forma con distintos
    breakpoints — un escalón (la versión anterior) no distingue 26.1°C de 29.9°C."""
    if v <= cero_lo or v >= cero_hi:
        return 0.0
    if v < opt_lo:
        return 100.0 * (v - cero_lo) / (opt_lo - cero_lo)
    if v > opt_hi:
        return 100.0 * (cero_hi - v) / (cero_hi - opt_hi)
    return 100.0


_SST_BREAKS = (22.0, 26.0, 30.0, 34.0)
_CHL_BREAKS = (1.0, 10.0, 30.0, 80.0)  # mg/m³ — VALIDAR CON DIEGO (breakpoints ecológicos)
_PH_BREAKS = (6.0, 7.0, 8.5, 9.5)
_SAL_HOMBRO = 6.0  # PSU de tolerancia fuera del rango de zona — VALIDAR CON DIEGO


def _score_sst(v: float) -> float:
    return _trapezoid(v, *_SST_BREAKS)


def _score_salinity(v: float, zone_min: float, zone_max: float) -> float:
    return _trapezoid(v, zone_min - _SAL_HOMBRO, zone_min, zone_max, zone_max + _SAL_HOMBRO)


def _score_chlorophyll(v: float) -> float:
    # Antes `min(100, v*10)`: monótona creciente, saturaba en 100 con cualquier
    # valor OLCI real de la CGSM (8-80 mg/m³) y era ecológicamente falsa — el
    # exceso de clorofila es floración → respiración nocturna → anoxia (ver seed
    # "Floración intensa... reporte de mortandad" en alembic/versions/003). Ahora
    # unimodal: 60 mg/m³ puntúa peor que 20.
    return _trapezoid(v, *_CHL_BREAKS)


def _score_ph(v: float) -> float:
    return _trapezoid(v, *_PH_BREAKS)


def calculate_ipp(water: dict, satellite: dict, zone: dict) -> float:
    """Solo puntúa las señales con dato real y renormaliza los pesos sobre ellas.

    Antes se rellenaba con defaults (sst=28, salinity=15, ph=7.5) cuando faltaba
    el dato — un IPP calculado sobre valores inventados es indistinguible de uno
    calculado sobre mediciones. Ver ipp_cobertura() para saber cuánta señal real
    sostiene el número.
    """
    scores = {}
    sst = satellite.get("sst_celsius")
    if sst is not None:
        scores["sst"] = _score_sst(sst)
    salinity = water.get("salinity_psu")
    if salinity is not None:
        scores["salinity"] = _score_salinity(salinity, zone["sal_min"], zone["sal_max"])
    chlorophyll = satellite.get("chlorophyll_mgm3")
    if chlorophyll is not None:
        scores["chlorophyll"] = _score_chlorophyll(chlorophyll)
    ph = water.get("ph")
    if ph is not None:
        scores["ph"] = _score_ph(ph)

    total_weight = sum(WEIGHTS[k] for k in scores)
    if total_weight == 0:
        return 0.0
    return round(sum(scores[k] * WEIGHTS[k] for k in scores) / total_weight, 1)


def ipp_cobertura(water: dict, satellite: dict) -> float:
    """Fracción del peso total (0.0-1.0) que tuvo dato real — no depende de la
    zona, solo de qué señales llegaron con valor. Un IPP con cobertura baja está
    calculado sobre poca señal real, aunque el número en sí luzca normal."""
    present = 0.0
    if satellite.get("sst_celsius") is not None:
        present += WEIGHTS["sst"]
    if water.get("salinity_psu") is not None:
        present += WEIGHTS["salinity"]
    if satellite.get("chlorophyll_mgm3") is not None:
        present += WEIGHTS["chlorophyll"]
    if water.get("ph") is not None:
        present += WEIGHTS["ph"]
    return round(present, 2)


def _zone_satellite(satellite: dict, zone_name: str) -> dict:
    """Satélite específico de la zona si existe; si no, la media del box (compat).
    `por_zona` es aditivo sobre `satellite` (ver ingestion/satellite.py) — sin él,
    esto se comporta exactamente como antes de F9."""
    return {**satellite, **(satellite.get("por_zona") or {}).get(zone_name, {})}


def _zona_mas_cercana(lat: float, lng: float) -> str:
    """Zona IPP de centroide más cercano — Euclidiana simple en grados, suficiente
    a esta escala (~decenas de km) para no traer una librería de geodesia."""
    return min(ZONES, key=lambda z: (z["lat"] - lat) ** 2 + (z["lng"] - lng) ** 2)["name"]


def rank_zones(water: dict, satellite: dict) -> list[dict]:
    cobertura = ipp_cobertura(water, satellite)
    results = [
        {
            "zone": z["name"],
            "ipp": calculate_ipp(water, _zone_satellite(satellite, z["name"]), z),
            "cobertura": cobertura,
        }
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
    """Igual que rank_zones pero sobre fishing_points reales (FishingPoint ORM).

    Cada punto usa el satélite de su zona IPP más cercana (por centroide) — el
    mismo dato con el que se calcula su IPP, no el promedio global del box.
    """
    cobertura = ipp_cobertura(water, satellite)

    def _punto(p: FishingPoint) -> dict:
        sat_zona = _zone_satellite(satellite, _zona_mas_cercana(p.lat, p.lng))
        ipp = calculate_ipp(water, sat_zona, {"sal_min": p.sal_min, "sal_max": p.sal_max})
        return {
            "id": str(p.id),
            "nombre": p.nombre,
            "lat": p.lat,
            "lng": p.lng,
            "especies": p.especies or [],
            "observacion": p.observacion,
            "temp": sat_zona.get("sst_celsius"),
            "clorofila": sat_zona.get("chlorophyll_mgm3"),
            "viento": weather.get("wind_speed_kmh"),
            "salinidad": water.get("salinity_psu"),
            "tds": water.get("tds_mgl"),
            "ipp": ipp,
            "cobertura": cobertura,
            "condicion": point_condition(ipp, semaphore_color),
        }

    results = [_punto(p) for p in points]
    return sorted(results, key=lambda x: x["ipp"], reverse=True)
