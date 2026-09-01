"""Señales compuestas de riesgo — ESTIMACIONES, no mediciones (docs/GUARDRAILS.md,
misma regla que ya veta presentar el OD teórico de García-Gordon como dato real).

No vive en derived.py: ese módulo es específicamente para derivadas del
instrumento propio (EC → salinidad → TDS) de confianza alta. Esto es otra cosa —
compuestos de satélite + clima + sensores con umbrales mecanísticos, no una
fórmula física estándar — y nombrarlo distinto evita que se contagien de la
credibilidad de derived.py.
"""

import math
from datetime import datetime


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# VALIDAR CON DIEGO antes de contrastar contra un evento real de mortandad — el
# mecanismo está documentado para la CGSM, los ocho números no.
_FACTOR_LABELS = {
    "chl": "clorofila muy alta",
    "sst": "agua muy caliente",
    "viento": "viento flojo",
    "nivel": "nivel de agua bajo",
}
_NIVEL_ALTO, _NIVEL_MEDIO = 60.0, 35.0
_MIN_FACTORES = 2  # con menos, no hay base para opinar


def anoxia_risk(satellite: dict, weather: dict, water: dict) -> dict:
    """ESTIMACIÓN (no medición) de riesgo de anoxia/mortandad de peces.

    Mecanismo documentado de las mortandades de la CGSM: floración de
    fitoplancton (clorofila alta) + agua caliente (menos O2 en saturación) +
    viento flojo (sin mezcla vertical, la columna se estratifica) + nivel bajo
    (menos volumen que amortigüe) → la respiración nocturna agota el oxígeno de
    madrugada. Promedio simple de los factores con dato — sin pesos inventados
    encima de umbrales ya inventados.
    """
    factores: dict[str, float] = {}

    chl = satellite.get("chlorophyll_mgm3")
    if chl is not None:
        factores["chl"] = _clamp((chl - 30) / 30, 0, 1)  # 30 mg/m³ → 0 ; 60+ → 1

    sst = satellite.get("sst_celsius")
    if sst is not None:
        factores["sst"] = _clamp((sst - 29) / 3, 0, 1)  # 29°C → 0 ; 32+ → 1

    wind = weather.get("wind_speed_kmh")
    if wind is not None:
        factores["viento"] = _clamp((8 - wind) / 8, 0, 1)  # 8 km/h → 0 ; calma → 1

    level = water.get("water_level_cm")
    if level is not None:
        factores["nivel"] = _clamp((40 - level) / 20, 0, 1)  # 40 cm → 0 ; 20 cm → 1

    n_factores = len(factores)
    if n_factores < _MIN_FACTORES:
        return {"score": None, "nivel": None, "factores": [], "n_factores": n_factores, "estimacion": True}

    score = round(100 * sum(factores.values()) / n_factores, 1)
    if score >= _NIVEL_ALTO:
        nivel = "alto"
    elif score >= _NIVEL_MEDIO:
        nivel = "medio"
    else:
        nivel = "bajo"
    activos = [_FACTOR_LABELS[k] for k, v in factores.items() if v > 0.5]

    return {"score": score, "nivel": nivel, "factores": activos, "n_factores": n_factores, "estimacion": True}


_PULSO_UMBRAL_MM = 30.0  # mm acumulados en 72h que anticipan un pulso de agua dulce


def pulso_agua_dulce(lluvia_72h_mm: float | None, salinidad_actual: float | None) -> dict | None:
    """Lluvia acumulada 72h en la cuenca → caída esperada de salinidad en 1 a 3 días.

    Direccional, no cuantificado: el coeficiente mm→PSU no existe todavía —
    ponytail: solo puede salir de regresar la precipitación IDEAM ya persistida
    contra la salinidad de sensores, que es justo lo que los datos que se
    guardan hoy habilitan en unos meses. Mientras tanto, se dice la dirección
    esperada, no un número inventado.
    """
    if lluvia_72h_mm is None or lluvia_72h_mm < _PULSO_UMBRAL_MM:
        return None
    return {
        "lluvia_72h_mm": lluvia_72h_mm,
        "mensaje": "Lluvia reciente en la cuenca — el agua debería entrar más dulce en 1 a 3 días.",
        "estimacion": True,
    }


_CONVECTIVO_ALTO, _CONVECTIVO_MEDIO = 60.0, 35.0  # mismos cortes que anoxia_risk, 0-100


def vendaval_risk(convective: dict, gust_threshold_kmh: float) -> dict:
    """ESTIMACIÓN de outlook de vendaval (24-48h, dashboard) — índice
    ambiental sobre `get_convective_forecast`, no umbral directo de ráfaga.

    La versión anterior disparaba WhatsApp cuando `wind_gusts_10m` cruzaba
    `gust_threshold_kmh`: contra el vendaval real del 29-ago-2026 esa ráfaga
    pronosticada nunca pasó de 21,6 km/h (umbral 62) — el pronóstico de
    ráfaga de un modelo global no tiene destreza para el downburst de escala
    sub-malla que de verdad tumba árboles (docs/ALERTAS_VENDAVAL.md). El
    índice compuesto (CAPE + CIN + sequedad sub-nube + ráfaga) sí distingue
    geográficamente Chibolo/Tenerife de la CGSM en el backtest, pero dispara
    high la mayoría de días de temporada de lluvias tierra adentro — por eso
    es un outlook informativo, nunca el disparador de push (ver
    signals.py::tormenta_aproximandose para el nowcast que sí empuja).
    Promedio de factores con dato, mismo patrón que anoxia_risk.
    """
    puntos = convective.get("puntos") or []
    if convective.get("origen") == "sin_dato" or not puntos:
        return {"nivel": None, "estimacion": True}

    factores: dict[str, float] = {}

    capes = [p["cape"] for p in puntos if p.get("cape") is not None]
    if capes:
        factores["cape"] = _clamp((max(capes) - 1500) / 1500, 0, 1)  # 1500 J/kg → 0 ; 3000+ → 1

    cins = [p["convective_inhibition"] for p in puntos if p.get("convective_inhibition") is not None]
    if cins:
        factores["cin"] = _clamp((50 - min(cins)) / 50, 0, 1)  # CIN 50 J/kg → 0 ; 0 (sin tapa) → 1

    t_td = [
        p["temperature_2m"] - p["dew_point_2m"]
        for p in puntos
        if p.get("temperature_2m") is not None and p.get("dew_point_2m") is not None
    ]
    if t_td:
        factores["sequedad"] = _clamp((max(t_td) - 12) / 8, 0, 1)  # T-Td 12°C → 0 ; 20+ → 1

    gusts = [p["wind_gust_kmh"] for p in puntos if p.get("wind_gust_kmh") is not None]
    if gusts:
        factores["rafaga"] = _clamp(max(gusts) / gust_threshold_kmh, 0, 1)

    if not factores:
        return {"nivel": None, "estimacion": True}

    score = round(100 * sum(factores.values()) / len(factores), 1)
    if score >= _CONVECTIVO_ALTO:
        nivel = "alto"
    elif score >= _CONVECTIVO_MEDIO:
        nivel = "medio"
    else:
        nivel = "bajo"

    return {"nivel": nivel, "score": score, "estimacion": True}


_MIN_DESTELLOS_CENTROIDE = 5  # menos que esto, el centroide de rayos es ruido


def _centroide(flashes: list[dict]) -> tuple[float, float]:
    lat = sum(f["lat"] for f in flashes) / len(flashes)
    lon = sum(f["lon"] for f in flashes) / len(flashes)
    return lat, lon


def _instante(flashes: list[dict]) -> datetime:
    return max(datetime.fromisoformat(f["timestamp"]) for f in flashes)


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


_CARDINALES = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]


def _rumbo_desde(origen: tuple[float, float], hacia: tuple[float, float]) -> str:
    """Dirección cardinal desde la que se acerca algo ubicado en `hacia`,
    visto desde `origen` (la CGSM)."""
    lat1, lon1 = math.radians(origen[0]), math.radians(origen[1])
    lat2, lon2 = math.radians(hacia[0]), math.radians(hacia[1])
    dl = lon2 - lon1
    x = math.sin(dl) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dl)
    deg = (math.degrees(math.atan2(x, y)) + 360) % 360
    return _CARDINALES[round(deg / 45) % 8]


def tormenta_aproximandose(
    anterior: dict | None,
    actual: dict,
    centro_lat: float,
    centro_lon: float,
    eta_max_min: float,
) -> dict | None:
    """Nowcast: compara dos instantáneas de rayos (~10 min aparte, ver
    ingestion/lightning.py::get_lightning_flashes) y estima si una tormenta
    se acerca al centro (centro_lat, centro_lon — la CGSM) con
    ETA <= eta_max_min. A diferencia de vendaval_risk, esto SÍ dispara
    WhatsApp (ver alert_service.py::maybe_send_storm_alert): es un sistema
    real detectado en movimiento, no un pronóstico de campo a 24h.

    None si falta la instantánea anterior (recién arrancó el proceso, se
    resuelve solo en el próximo ciclo), si cualquiera de las dos no tiene
    suficientes destellos para un centroide confiable, si el centroide no se
    está acercando, o si el ETA lineal supera `eta_max_min`.

    Backtest real: scripts/verify_glm_lead_29ago.py — 270 min de lead medidos
    contra el vendaval del 29-ago-2026 en Tenerife. Límite conocido: una
    tormenta que se forma encima del propio objetivo no da ningún lead (así
    pasó en Chibolo ese mismo día) — límite físico de cualquier nowcast, no
    de esta implementación (ver docs/ALERTAS_VENDAVAL.md).
    """
    flashes_prev = (anterior or {}).get("flashes") or []
    flashes_now = actual.get("flashes") or []
    if len(flashes_prev) < _MIN_DESTELLOS_CENTROIDE or len(flashes_now) < _MIN_DESTELLOS_CENTROIDE:
        return None

    centro = (centro_lat, centro_lon)
    c_prev = _centroide(flashes_prev)
    c_now = _centroide(flashes_now)

    d_prev = _haversine_km(c_prev, centro)
    d_now = _haversine_km(c_now, centro)
    if d_now >= d_prev:
        return None  # no se acerca

    dt_min = (_instante(flashes_now) - _instante(flashes_prev)).total_seconds() / 60
    if dt_min <= 0:
        return None  # instantáneas fuera de orden — dato inconsistente

    closing_kmh = (d_prev - d_now) / (dt_min / 60)
    eta_min = (d_now / closing_kmh) * 60
    if eta_min > eta_max_min:
        return None

    return {
        "eta_min": round(eta_min),
        "rumbo": _rumbo_desde(centro, c_now),
        "distancia_km": round(d_now, 1),
        "n_descargas": len(flashes_now),
    }
