"""Contexto ambiental para el prompt de IA y heurística tradicional de pesca."""

from datetime import UTC, datetime

_SIN_REVISAR = {
    "viento": "viento",
    "lluvia": "lluvia",
    "oleaje": "oleaje",
    "ciclon": "ciclones",
    "frente_frio": "frentes fríos",
    "enso": "El Niño/La Niña",
    "ideam": "alertas del IDEAM",
}


def avisos_para_pescador(avisos: dict | None, solo_alertas: bool = False) -> str | None:
    """Avisos del tiempo (app/services/avisos.py) como texto de WhatsApp. Completo para
    la palabra *avisos*; `solo_alertas` (saludo, condición) devuelve None si no hay
    ningún aviso alto, para no alargar esas respuestas."""
    if avisos is None:
        return None if solo_alertas else "Todavía no tengo los avisos del tiempo. Intenta en un rato."
    altos = [a["mensaje"] for a in avisos.get("vigentes") or [] if a.get("nivel") == "alto"]
    if solo_alertas:
        return " ".join(altos) or None
    faltan = [_SIN_REVISAR.get(x, x) for x in avisos.get("sin_revisar") or []]
    medios = [a["titulo"] for a in avisos.get("vigentes") or [] if a.get("nivel") == "medio"]
    lineas = list(altos)
    if medios:
        lineas.append(f"🟡 Estar atento: {'; '.join(medios)}.")
    if not lineas:
        lineas.append("✅ Sin avisos del tiempo para las próximas horas" + (" en lo que pude revisar." if faltan else "."))
    if faltan:
        lineas.append(f"⚠️ No pude revisar: {', '.join(faltan)} (fuente sin datos). Pregunta a la Capitanía.")
    t = avisos.get("temporada")
    if t:
        lineas.append(
            f"📅 Ahora estamos en la {t['actual']}; la {t['proxima']} empieza a {t['proxima_cuando']}. "
            f"{t.get('efecto_enso') or ''}".strip()
        )
    return "\n\n".join(lineas)


def build_ai_context(snapshot: dict, vendaval: dict | None = None) -> str:
    """Arma el bloque de contexto ambiental para el prompt de Gemini (dashboard.ask_ai
    y message_router.py).

    Cubre las mismas fuentes que /data/latest — clima por estación (CGSM + Tasajera,
    con humedad) e hidrometeorología IDEAM (lluvia/nivel de río) — resumidas a su
    última lectura por estación para no inflar el prompt con series completas; el
    histórico completo ya vive en /data/history si se necesita más adelante.

    `vendaval`: outlook de vendaval de signals.vendaval_risk() (48h, modelo CAPE/CIN).
    Siempre en el contexto cuando hay dato, para que la respuesta no dependa de si
    el pescador preguntó con la frase exacta que dispara un tool — el clima es uno
    solo, no debería variar según cómo se formuló la pregunta.
    """
    parts = [
        f"Semáforo: {snapshot['semaphore']['reason']}.",
        f"Clorofila-a: {snapshot['satellite'].get('chlorophyll_mgm3')} mg/m³ (Sentinel-3 OLCI vía NOAA "
        f"CoastWatch). Temperatura superficial del agua: {snapshot['satellite'].get('sst_celsius')} °C "
        f"(NASA MUR, jplMURSST41).",
    ]

    def fmt_weather(label: str, w: dict) -> str:
        return (
            f"{label} (Open-Meteo): temperatura {w.get('temperature_c')} °C, "
            f"humedad {w.get('humidity_pct')}%, viento {w.get('wind_speed_kmh')} km/h, "
            f"precipitación {w.get('precipitation_mm')} mm."
        )

    parts.append(fmt_weather("CGSM", snapshot.get("weather") or {}))
    tasajera = snapshot.get("tasajera_weather")
    if tasajera:
        parts.append(fmt_weather("Tasajera", tasajera))

    def latest_por_estacion(rows: list[dict], value_key: str) -> dict[str, tuple[str, float]]:
        latest: dict[str, tuple[str, float]] = {}
        for r in rows:
            prev = latest.get(r["estacion"])
            if prev is None or r["date"] > prev[0]:
                latest[r["estacion"]] = (r["date"], r[value_key])
        return latest

    precip = latest_por_estacion(snapshot.get("ideam_precipitacion") or [], "precipitacion_mm")
    if precip:
        detalle = "; ".join(f"{est} {v} mm ({fecha})" for est, (fecha, v) in precip.items())
        parts.append(f"Precipitación IDEAM, última lectura por estación: {detalle}.")

    nivel = latest_por_estacion(snapshot.get("ideam_nivel_rio") or [], "nivel_m")
    if nivel:
        detalle = "; ".join(f"{est} {v} m ({fecha})" for est, (fecha, v) in nivel.items())
        parts.append(f"Nivel de río IDEAM, última lectura por estación: {detalle}.")

    # Solo oxígeno disuelto en el camino rápido (el más ligado a riesgo de
    # anoxia/mortandad de peces) — el resto de variables INVEMAR (salinidad, pH,
    # temperatura, SST) quedan detrás del tool calidad_agua_estaciones para no
    # inflar el prompt con las 12 estaciones x 5 variables en cada pregunta.
    oxigeno = [r for r in snapshot.get("calidad_agua") or [] if r.get("variable") == "Oxigeno Disuelto"]
    if oxigeno:
        detalle = "; ".join(f"{r['estacion']} {r['valor']} {r['unidad']} ({r['rango']})" for r in oxigeno)
        parts.append(f"Oxígeno disuelto INVEMAR (REDCAM) por estación: {detalle}.")

    nivel_vendaval = (vendaval or {}).get("nivel")
    if nivel_vendaval:
        parts.append(
            f"Outlook de vendaval/ráfagas para las próximas 48h (modelo, NO es medición "
            f"ni alerta oficial, con historial de falsos positivos en temporada de "
            f"lluvias): nivel {nivel_vendaval}. Menciónalo siempre que respondas sobre "
            "pronóstico o si va a llover/haber viento fuerte, dejando claro que es una "
            "estimación de modelo, no una certeza."
        )

    lluvia = (snapshot.get("senales") or {}).get("lluvia") or {}
    estado = (lluvia.get("nowcast") or {}).get("estado")
    outlook = lluvia.get("outlook") or {}
    if estado in ("lloviendo", "inminente") or outlook.get("nivel") in ("medio", "alto"):
        probs = [
            f"{etiqueta} {round(p * 100)} %"
            for etiqueta, p in (("en 6h", outlook.get("prob_6h")), ("en 24h", outlook.get("prob_24h")))
            if p is not None
        ]
        modelo = f"; probabilidad de lluvia fuerte {' y '.join(probs)} (modelo, falla seguido)" if probs else ""
        parts.append(
            f"Lluvia sobre la Ciénaga (estimaciones, NO certezas): ahora {(estado or 'sin dato').replace('_', ' ')} "
            "(satélite, 10-60 min; 'inminente' = lluvia fuerte llegando en ~30-60 min)"
            f"{modelo}. Menciónalo si preguntan por lluvia o salir a pescar."
        )

    avisos = (snapshot.get("senales") or {}).get("avisos")
    if avisos:
        vigentes = "; ".join(
            f"{a['titulo']} ({'confirmado' if a['nivel'] == 'alto' else 'posible, un solo modelo'}, {a['fuente']}): "
            f"{a['mensaje']}"
            for a in avisos.get("vigentes") or []
        )
        t = avisos.get("temporada") or {}
        faltan = ", ".join(_SIN_REVISAR.get(x, x) for x in avisos.get("sin_revisar") or [])
        parts.append(
            f"Avisos del tiempo (próximas {avisos.get('horas', 36)} h; consenso de modelos ECMWF/GFS/ICON, NOAA NHC, NOAA CPC): "
            f"{vigentes or 'ninguno'}."
            + (f" No se pudo revisar: {faltan}." if faltan else "")
            + (f" Temporada: {t['actual']}; próxima {t['proxima']} desde {t['proxima_cuando']}. "
               f"{t.get('efecto_enso') or ''}" if t else "")
            + " Menciónalos si preguntan por el tiempo, el pronóstico o si es seguro salir a pescar."
        )

    return " ".join(parts)


_SYNODIC_MONTH_DAYS = 29.530588853
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=UTC)


def _moonrise_hour_aprox(now: datetime) -> float:
    """Hora local aproximada (0-23.99) de salida de la luna.

    ponytail: aproximación sin librería de astronomía (mismo criterio que
    frontend/lib/moon.ts) — ancla la luna nueva a la salida del sol (~06:00,
    razonable para la latitud tropical de la Ciénaga) y avanza la salida ~50
    min/día a lo largo del mes sinódico hasta completar el ciclo de 24h. Subir
    a un cálculo efemérides real (p.ej. skyfield) si la precisión no alcanza.
    """
    age_days = (now - _KNOWN_NEW_MOON).total_seconds() / 86400 % _SYNODIC_MONTH_DAYS
    return (6 + 24 * (age_days / _SYNODIC_MONTH_DAYS)) % 24


def camaron_moonrise_hint(now: datetime | None = None) -> str:
    """Creencia tradicional de los pescadores sobre la zona probable de camarón
    según la hora de salida de la luna — NO es un dato medido, se debe presentar
    como conocimiento comunitario (ver docs/GUARDRAILS.md)."""
    hour = _moonrise_hour_aprox(now or datetime.now(UTC))
    if 23 <= hour or hour < 1:
        zona = "la zona media de la costa, como Tasajera"
    elif 1 <= hour < 6:
        zona = "la parte sur de esa costa"
    else:
        zona = "la parte norte de la costa que colinda con el mar"
    hora_str = f"{int(hour):02d}:{int((hour % 1) * 60):02d}"
    return (
        "Conocimiento tradicional de los pescadores (no es un dato medido): dividen "
        "la noche en tres partes según la hora en que sale la luna — si sale temprano "
        "en la noche, el camarón está en la parte norte de la costa que colinda con el "
        "mar; si sale entre 11pm y 1am, está a la mitad, como en Tasajera; si sale "
        f"después de la 1am, está en la parte sur. Hoy la luna sale aprox. a las "
        f"{hora_str}, por lo que según esta creencia el camarón estaría hacia {zona}."
    )
