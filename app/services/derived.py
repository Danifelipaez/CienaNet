"""Variables derivadas del instrumento propio (§10 entregables Diego).

Se calculan al vuelo desde las mediciones crudas (EC, temperatura); NO se
almacenan. El crudo persistido (conductivity_mscm, temperature_c) es la fuente
reproducible y la base del futuro modelo ML — cualquier derivada se recomputa.

- salinidad: PSS-78 vía gsw (TEOS-10, estándar IOC/UNESCO). Confianza alta.
- TDS: factor APHA sobre EC compensada a 25°C. Confianza alta.
- OD teórico (García-Gordon): NO se calcula aquí. Confianza baja — Diego prohíbe
  presentarlo como medición real en el dashboard o el bot.
"""

import math

import gsw


def ec25(ec_mscm: float | None, temp_c: float | None) -> float | None:
    """Conductividad compensada a 25°C (paso previo obligatorio al TDS)."""
    if ec_mscm is None or temp_c is None:
        return None
    return ec_mscm / (1 + 0.02 * (temp_c - 25))


def salinity_psu(ec_mscm: float | None, temp_c: float | None) -> float | None:
    """Salinidad práctica PSS-78 desde EC cruda (mS/cm) y temperatura in-situ (°C).

    gsw.SP_from_C aplica la compensación de temperatura internamente, así que
    recibe la EC medida (no la compensada) y la temperatura del sensor.
    """
    if ec_mscm is None or temp_c is None:
        return None
    sp = float(gsw.SP_from_C(ec_mscm, temp_c, 0))  # presión 0 dbar (superficie)
    if not math.isfinite(sp):  # EC casi nula → PSS-78 fuera de dominio
        return None
    return round(max(0.0, sp), 2)  # salinidad negativa es no física


def tds_mgl(ec_mscm: float | None, temp_c: float | None) -> float | None:
    """Sólidos disueltos totales (mg/L), estándar APHA sobre EC25."""
    ec = ec25(ec_mscm, temp_c)
    if ec is None:
        return None
    # ponytail: factor APHA 0.64 (agua salobre); knob de calibración si se
    # contrasta contra TDS de laboratorio de la CGSM. EC25 en mS/cm → µS/cm ×1000.
    return round(0.64 * ec * 1000, 1)
