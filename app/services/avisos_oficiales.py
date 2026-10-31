"""Avisos de fuentes oficiales y de calendario (docs/AVISOS_CLIMA.md): alertas CAP del
IDEAM, ciclones del NHC, frente frío del TWD del NHC y temporada próxima. Separado de
avisos.py (consenso de modelos) por el límite de tamaño de docs/GUARDRAILS.md; también
tiene los helpers de fecha/forma que comparten los dos.
"""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services.signals import _haversine_km, _rumbo_desde
from app.services.temporadas import DIAS_PREVIOS, mensaje_temporada, temporada

BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _dia(local: datetime, ahora: datetime) -> str:
    dias = (local.date() - ahora.astimezone(BOGOTA).date()).days
    return "hoy" if dias <= 0 else "mañana" if dias == 1 else f"el {_DIAS[local.weekday()]}"


def cuando(t: datetime, ahora: datetime) -> str:
    """'hoy en la tarde', 'mañana en la madrugada', 'el lunes en la noche' (hora local)."""
    local = t.astimezone(BOGOTA)
    h = local.hour
    franja = "madrugada" if h < 6 else "mañana" if h < 12 else "tarde" if h < 18 else "noche"
    return f"{_dia(local, ahora)} en la {franja}"


def hasta(t: datetime, ahora: datetime) -> str:
    """'hasta hoy a las 16:00', 'hasta el lunes a las 11:00' (hora local)."""
    local = t.astimezone(BOGOTA)
    return f"hasta {_dia(local, ahora)} a las {local:%H:%M}"


def aviso(tipo: str, nivel: str, titulo: str, mensaje: str, fuente: str, clave: str, desde: str | None) -> dict:
    """Forma única de un aviso. `push` = nivel "alto"; `clave` = dedup en avisos_push."""
    return {
        "tipo": tipo,
        "nivel": nivel,
        "titulo": titulo,
        "mensaje": mensaje,
        "fuente": fuente,
        "desde": desde,
        "clave": clave,
        "push": nivel == "alto",
    }


_COLOR_IDEAM = {"Minor": "amarilla", "Moderate": "amarilla", "Severe": "naranja", "Extreme": "roja"}
_CONSEJO_IDEAM = {
    "ideam_mar": "No salgas al mar y sigue los avisos de la Capitanía de Puerto.",
    "ideam_cuenca": "Cuidado en ríos y caños: pueden crecer de repente.",
}


def avisos_ideam(alertas: list[dict], ahora: datetime) -> list[dict]:
    """CAP del IDEAM vigentes. Empujan WhatsApp: en el mar, naranja o roja; en las
    cuencas, solo roja — la de crecientes súbitas sale casi a diario para decenas de
    cuencas a la vez y en naranja sería ruido. El resto queda en el dashboard."""
    out = []
    for a in alertas:
        expira = datetime.fromisoformat(a["expira"]) if a.get("expira") else None
        if expira is not None and expira <= ahora:
            continue  # cache viejo: la alerta ya venció
        inicio = datetime.fromisoformat(a["inicio"]) if a.get("inicio") else ahora
        severo = a["severidad"] == "Extreme" or (a["severidad"] == "Severe" and a["tipo"] == "ideam_mar")
        color = f" {_COLOR_IDEAM[a['severidad']]}" if a["severidad"] in _COLOR_IDEAM else ""
        out.append(aviso(
            a["tipo"], "alto" if severo else "medio", f"IDEAM: {a['evento']}",
            f"⚠️ Alerta{color} del IDEAM ({a['evento'].lower()}) para {a['zona']}"
            f"{' ' + hasta(expira, ahora) if expira else ''}. {_CONSEJO_IDEAM[a['tipo']]}",
            "IDEAM (alerta oficial CAP)",
            # Un aviso por evento y día: el IDEAM reemite la misma alerta con otro id en cada boletín.
            f"{a['evento']}:{inicio.astimezone(BOGOTA).date().isoformat()}",
            inicio.isoformat(),
        ))
    return out


_CLASES = {
    "TD": "Depresión tropical", "TS": "Tormenta tropical", "HU": "Huracán", "MH": "Huracán mayor",
    "STD": "Depresión subtropical", "STS": "Tormenta subtropical", "PTC": "Posible ciclón tropical",
}


def avisos_ciclon(ciclones: list[dict]) -> list[dict]:
    """Ciclón a <= aviso_ciclon_km empuja; hasta el doble, solo dashboard. La clave lleva
    la categoría: si sube de tormenta a huracán se vuelve a avisar."""
    centro = (settings.cienaga_lat, settings.cienaga_lon)
    out = []
    for c in ciclones:
        pos = (c["lat"], c["lon"])
        d = _haversine_km(centro, pos)
        if d > 2 * settings.aviso_ciclon_km:
            continue
        clase = _CLASES.get(c["clasificacion"], "Ciclón tropical")
        out.append(aviso(
            "ciclon", "alto" if d <= settings.aviso_ciclon_km else "medio", f"{clase} {c['nombre']}",
            f"🌀 {clase} {c['nombre']} a unos {round(d, -1):.0f} km al {_rumbo_desde(centro, pos)} de la Ciénaga. "
            "Puede traer lluvia, viento y mar de leva: sigue los avisos de la Capitanía de Puerto y no salgas al mar.",
            "NOAA NHC", f"{c['id']}:{c['clasificacion']}", None,
        ))
    return out


def aviso_frente_frio(sinoptico: dict, ahora: datetime) -> dict | None:
    """Frente frío nombrado en las secciones del Caribe del TWD. Empuja solo si el NHC
    ubica EL FRENTE sobre Colombia / SW del Caribe (`afectan`; `afecta_cgsm` es True
    también por una onda o vaguada cercana); si no, el viento y el oleaje que traiga
    los avisa el consenso de modelos."""
    if "frente_frio" not in (sinoptico.get("sistemas") or []):
        return None
    anio, semana, _ = ahora.astimezone(BOGOTA).isocalendar()
    return aviso(
        "frente_frio", "alto" if "frente_frio" in (sinoptico.get("afectan") or []) else "medio",
        "Frente frío en el Caribe",
        "🌬️ Un frente frío avanza por el Caribe: en los próximos días puede traer brisa fuerte del "
        "norte y mar de leva. Revisa el pronóstico antes de salir.",
        # Clave semanal: el TWD sale cada 6 h y un frente dura días.
        "NOAA NHC (discusión tropical)", f"{anio}-W{semana:02d}", None,
    )


def temporada_y_aviso(ahora: datetime, enso: dict | None) -> tuple[dict, dict | None]:
    """(temporada para el dashboard, aviso si la próxima arranca en <= DIAS_PREVIOS días)."""
    t = temporada(ahora.astimezone(BOGOTA).date(), enso)
    if t["dias_para_proxima"] > DIAS_PREVIOS:
        return t, None
    return t, aviso(
        "temporada", "alto", f"Se acerca la {t['proxima']}", mensaje_temporada(t),
        "Climatología IDEAM" + (" + NOAA CPC (ENSO)" if enso else ""), t["proxima_clave"], None,
    )
