"""Señales compuestas de riesgo — ESTIMACIONES, no mediciones (docs/GUARDRAILS.md,
misma regla que ya veta presentar el OD teórico de García-Gordon como dato real).

No vive en derived.py: ese módulo es específicamente para derivadas del
instrumento propio (EC → salinidad → TDS) de confianza alta. Esto es otra cosa —
compuestos de satélite + clima + sensores con umbrales mecanísticos, no una
fórmula física estándar — y nombrarlo distinto evita que se contagien de la
credibilidad de derived.py.
"""


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
