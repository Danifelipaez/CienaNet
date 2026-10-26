"""Señales de lluvia sobre la CGSM — ESTIMACIONES, mismas reglas que signals.py
(docs/ALERTAS_LLUVIA.md). Separado de signals.py por el límite de tamaño de
docs/GUARDRAILS.md.
"""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services.signals import _haversine_km

def contar_rayos_cerca(
    flashes: list[dict], centro_lat: float, centro_lon: float, radio_km: float = 100.0
) -> int:
    """Destellos de `flashes` (los de get_lightning_flashes) a <= radio_km del centro."""
    return sum(
        1 for f in flashes if _haversine_km((f["lat"], f["lon"]), (centro_lat, centro_lon)) <= radio_km
    )


def lluvia_nowcast(features: dict | None, ahora: datetime, rayos_100km: int = 0) -> dict:
    """Nowcast de lluvia 10-90 min sobre la CGSM con el último scan RRQPE
    (ingestion/rain_nowcast.py::get_rain_features). Solo "inminente" dispara
    WhatsApp (alert_service.py::maybe_send_rain_alert).

    - "lloviendo": >= lluvia_caja_umbral de la caja con >= 1 mm/h. Ya se está
      mojando, avisar sería tarde -> sin push.
    - "inminente": la caja no llueve y >= lluvia_anillo_umbral del anillo
      20-60 km tiene >= 5 mm/h. Lluvia fuerte entrando, ~30-60 min (mediana de
      antelación 30 min, rango 10-80). Backtest 27-sep..26-oct-2026: POD 0.71,
      FAR por episodio 0.43. Muestra de 34 episodios y un solo mes: puede fallar.
    - "sin_dato": sin scan, scan de más de lluvia_scan_max_min o más de
      lluvia_nan_max de NaN. Nunca se inventa "sin_lluvia" con dato dudoso.
    `tormenta_electrica` (>= lluvia_rayos_umbral destellos GLM en 30 min a
    <=100 km) es severidad, no predictor: no cambia el estado.
    """
    tormenta = rayos_100km >= settings.lluvia_rayos_umbral
    base = {"tormenta_electrica": tormenta, "n_rayos_30min": rayos_100km, "estimacion": True}

    scan = (features or {}).get("scan")
    frac_caja = (features or {}).get("frac_caja_1mm")
    frac_anillo = (features or {}).get("frac_anillo_5mm")
    frac_nan = (features or {}).get("frac_nan")
    if (
        features is None
        or scan is None
        or frac_caja is None
        or frac_anillo is None
        or frac_nan is None
        or frac_nan > settings.lluvia_nan_max
        or ahora - scan > timedelta(minutes=settings.lluvia_scan_max_min)
    ):
        return {"estado": "sin_dato", **base}

    base |= {
        "scan": scan.isoformat(),
        "frac_caja_1mm": round(frac_caja, 3),
        "frac_anillo_5mm": round(frac_anillo, 3),
    }
    if frac_caja >= settings.lluvia_caja_umbral:
        return {"estado": "lloviendo", **base}
    if frac_anillo >= settings.lluvia_anillo_umbral:
        return {"estado": "inminente", "eta_rango_min": [30, 60], **base}
    return {"estado": "sin_lluvia", **base}


_LLUVIA_ALTO, _LLUVIA_MEDIO = 0.5, 0.3
_LLUVIA_MM_6H = 5.0  # mm acumulados en un bloque de 6 h que cuentan como lluvia significativa


def _prob_bloque(miembros: list[list[float | None]], idx: list[int]) -> float | None:
    """Fracción de miembros del ensamble con >= 5 mm acumulados en las horas `idx`.
    Un miembro con algún hueco (null) en el bloque no vota."""
    if len(idx) < 6:
        return None  # pronóstico más corto que el bloque: no opinar con un bloque parcial
    sumas = [sum(m[i] for i in idx) for m in miembros if all(i < len(m) and m[i] is not None for i in idx)]
    if not sumas:
        return None
    return sum(1 for v in sumas if v >= _LLUVIA_MM_6H) / len(sumas)


def lluvia_outlook(ens: dict, ahora: datetime) -> dict:
    """ESTIMACIÓN de outlook de lluvia 6 h / 24 h (dashboard, SIN push) sobre
    el ensamble GEFS de `ingestion/weather.py::get_rain_ensemble` (31 miembros).

    prob_6h: fracción de miembros con >= 5 mm en las próximas 6 h.
    prob_24h: máximo de esa probabilidad en los bloques +6..+12, +12..+18 y
    +18..+24 h. `nivel` usa el mayor de los dos: bajo < 0.3 <= medio < 0.5 <= alto.

    Open-Meteo etiqueta cada hora con su FIN (acumulado de la hora previa), así
    que el bloque [t0, t0+6h) toma las etiquetas en (t0, t0+6h]. Backtest propio
    del GEFS (12-26 oct, 57 bloques, sobre el máximo de celdas de la caja) dio a
    ~12 h P>=0.5: POD 0.70 / FAR 0.42; a ~24 h POD 0.60 / FAR 0.50, n pequeño.
    Esto usa el punto de Open-Meteo, que no fue backtesteado; por eso no empuja.
    """
    horas = ens.get("times") or []
    miembros = ens.get("miembros") or []
    if ens.get("origen") == "sin_dato" or not horas or not miembros:
        return {"nivel": None, "estimacion": True}

    # Las etiquetas de Open-Meteo vienen en UTC naive.
    t0 = ahora.astimezone(timezone.utc).replace(tzinfo=None)
    etiquetas = [datetime.fromisoformat(h) for h in horas]

    def bloque(desde_h: int) -> list[int]:
        return [
            i
            for i, t in enumerate(etiquetas)
            if t0 + timedelta(hours=desde_h) < t <= t0 + timedelta(hours=desde_h + 6)
        ]

    p6 = _prob_bloque(miembros, bloque(0))
    p24 = [_prob_bloque(miembros, bloque(h)) for h in (6, 12, 18)]
    p24 = [p for p in p24 if p is not None]
    if p6 is None or not p24:
        return {"nivel": None, "estimacion": True}

    prob_24h = max(p24)
    peor = max(p6, prob_24h)
    nivel = "alto" if peor >= _LLUVIA_ALTO else "medio" if peor >= _LLUVIA_MEDIO else "bajo"
    return {
        "nivel": nivel,
        "prob_6h": round(p6, 2),
        "prob_24h": round(prob_24h, 2),
        "umbral_mm_6h": _LLUVIA_MM_6H,
        "n_miembros": len(miembros),
        "estimacion": True,
    }
