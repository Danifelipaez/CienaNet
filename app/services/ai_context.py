"""Contexto ambiental para el prompt de IA y heurística tradicional de pesca."""

from datetime import UTC, datetime

# ponytail: alerta puntual hardcodeada (no hay ingesta de alertas IDEAM todavía).
# Vence después del 18-sep-2026 — borrar esta constante y sus usos en dashboard.py
# / message_router.py cuando la onda tropical pase, o subir a una fuente en vivo
# si esto se vuelve recurrente. Fuente: IDEAM, vía prensa (diariolalibertad.com,
# eltiempo.com), 16-sep-2026.
ALERTA_IDEAM_ONDA_TROPICAL = (
    "onda tropical sobre el Caribe colombiano (14 al 18 de septiembre de 2026), "
    "con lluvias fuertes, tormentas eléctricas y vientos, más intensa el jueves 17 "
    "y viernes 18 — precaución cerca de ríos y caños por crecientes súbitas"
)


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
