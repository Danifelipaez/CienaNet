"""Temporada seca / de lluvias próxima en el litoral del Magdalena, modulada por el
estado ENSO del NOAA CPC (docs/AVISOS_CLIMA.md). Calendario = climatología, no
pronóstico: el inicio real se corre semanas de un año a otro; el ENSO dice si la
temporada viene más seca o más lluviosa de lo normal.
"""

from datetime import date

# Régimen bimodal del Caribe colombiano (IDEAM): (mes, día de inicio típico, clave,
# nombre, qué esperar).
TEMPORADAS = (
    (4, 15, "lluvias_1", "primera temporada de lluvias", "vuelven las lluvias y los aguaceros con tormenta"),
    (6, 20, "veranillo", "veranillo de San Juan", "unas semanas con menos lluvia"),
    (8, 15, "lluvias_2", "segunda temporada de lluvias", "la época más lluviosa del año, con tormentas eléctricas"),
    (12, 15, "seca", "temporada seca", "poca lluvia, brisa fuerte del noreste y mar picado"),
)
DIAS_PREVIOS = 15  # cuántos días antes del inicio típico se avisa por WhatsApp
_SECAS = ("seca", "veranillo")
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]


def temporada(hoy: date, enso: dict | None) -> dict:
    """Temporada actual, la próxima, cuántos días faltan y el efecto ENSO esperado."""
    inicios = sorted((date(a, t[0], t[1]), t) for a in (hoy.year - 1, hoy.year, hoy.year + 1) for t in TEMPORADAS)
    actual = max((x for x in inicios if x[0] <= hoy), key=lambda x: x[0])
    inicio, prox = min((x for x in inicios if x[0] > hoy), key=lambda x: x[0])
    parte = "comienzos" if inicio.day <= 10 else "mediados" if inicio.day <= 20 else "finales"
    return {
        "actual": actual[1][3],
        "proxima": prox[3],
        "proxima_clave": f"{prox[2]}:{inicio.year}",
        "proxima_inicio": inicio.isoformat(),
        "proxima_cuando": f"{parte} de {_MESES[inicio.month - 1]}",
        "dias_para_proxima": (inicio - hoy).days,
        "que_esperar": prox[4],
        "enso": enso,
        "efecto_enso": efecto_enso(enso, seca=prox[2] in _SECAS),
    }


def efecto_enso(enso: dict | None, seca: bool) -> str | None:
    if not enso or enso["fase"] == "neutral":
        return None
    fen = "El Niño" if enso["fase"] == "el_nino" else "La Niña"
    if enso.get("terminando"):  # "Final ... Advisory": el evento se está acabando, no llegando
        return f"{fen} se está terminando: las lluvias deberían volver poco a poco a lo normal."
    if not enso["vigente"]:
        return f"Podría llegar {fen} en los próximos meses."
    if enso["fase"] == "el_nino":
        if seca:
            return (f"Hay {fen}: se espera menos lluvia y más calor de lo normal; la ciénaga puede bajar "
                    "de nivel y ponerse más salada.")
        return f"Hay {fen}: se esperan menos lluvias de lo normal."
    if seca:
        return f"Hay {fen}: puede llover más de lo normal para la época."
    return f"Hay {fen}: se esperan más lluvias de lo normal; atento a las crecientes."


def mensaje_temporada(t: dict) -> str:
    return f"📅 Desde {t['proxima_cuando']} empieza la {t['proxima']}: {t['que_esperar']}. {t['efecto_enso'] or ''}".strip()
