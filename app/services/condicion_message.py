"""Compone el mensaje de 'condición' que recibe el pescador por WhatsApp.

_mensaje_condicion es pura (dict de estado persistido -> texto): sin DB, sin
red, fácil de testear. Separado de message_router.py (que ya pasaba las 300
líneas de docs/GUARDRAILS.md) porque el enrutamiento de intención y la
composición del mensaje son responsabilidades distintas.
"""

_SEMAFORO_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

_RAFAGA_FUERTE_KMH = 35  # ráfaga que amerita advertencia explícita en el mensaje
_DATO_VIEJO_HORAS = 3


def _frase_seguridad(sem: dict, weather: dict) -> str:
    emoji = _SEMAFORO_EMOJI.get(sem["color"], "")
    gust = weather.get("wind_gust_kmh")
    aviso = " con ráfagas fuertes de viento" if gust is not None and gust > _RAFAGA_FUERTE_KMH else ""
    return f"{emoji} {sem['reason']}{aviso}."


_COBERTURA_MINIMA = 0.5  # bajo esto, el IPP está calculado sobre muy poca señal real


def _frase_donde(ranking: list[dict], water: dict) -> str | None:
    if not ranking:
        return None
    mejor = ranking[0]
    if mejor.get("cobertura", 1.0) < _COBERTURA_MINIMA:
        return "Hoy no tengo suficientes lecturas de los sensores para recomendarte una zona."
    aviso = "" if water else ", aunque hoy no tengo lectura de los sensores del agua (solo datos satelitales)"
    return f"La mejor zona hoy parece ser {mejor['zone']}{aviso}."


def _frase_dato_viejo(edad_horas: dict) -> str | None:
    edad = (edad_horas or {}).get("weather")
    if edad is not None and edad > _DATO_VIEJO_HORAS:
        return "Ojo: estos datos son de hace unas horas."
    return None


# Solo salinidad y nivel de agua — son las que le importan al pescador para
# decidir dónde tirar la atarraya; sst/clorofila quedan para el dashboard.
_TENDENCIA_TEXTO = {
    "salinity_psu": {
        "subiendo": "en los últimos días el agua se ha puesto más salada",
        "bajando": "en los últimos días el agua se ha puesto más dulce",
    },
    "water_level_cm": {
        "subiendo": "el nivel del agua ha estado subiendo estos días",
        "bajando": "el nivel del agua ha estado bajando estos días",
    },
}


def _frase_tendencia(tendencias: dict) -> str | None:
    variables = (tendencias or {}).get("variables") or {}
    for clave in ("salinity_psu", "water_level_cm"):
        var = variables.get(clave)
        if not var:
            continue
        texto = _TENDENCIA_TEXTO[clave].get(var.get("direccion"))
        if texto:
            return f"{texto.capitalize()}."
    return None


def _frase_accion(color: str | None) -> str:
    if color == "red":
        return "Mejor espera a que mejoren las condiciones antes de salir."
    if color == "yellow":
        return "Sal con precaución y mantente cerca de la orilla."
    return "Buen día para salir a pescar."


# ponytail: el mecanismo ya está listo (mensaje en lenguaje llano, siempre
# marcado como posibilidad) pero apagado — los 8 umbrales de anoxia
# (app/services/signals.py) no están validados contra un evento real todavía,
# y el riesgo de un falso positivo (día de pesca perdido, credibilidad quemada)
# es asimétrico frente al de un falso negativo. Subir a True cuando el equipo
# científico lo confirme en el dashboard.
_ANOXIA_EN_BOT = False


def _frase_anoxia(senales: dict) -> str | None:
    anoxia = (senales or {}).get("anoxia") or {}
    if anoxia.get("nivel") != "alto":
        return None
    return "El agua está muy verde y sin brisa — podría haber peces muertos de madrugada."


def _mensaje_condicion(estado: dict) -> str:
    """Respuesta del bot desde el estado persistido. Pura: sin DB, sin red.

    Regla de producto (docs/ONBOARDING_SENIOR_DEV.md:38-43): 3-4 oraciones, sin
    jerga, siempre con una acción concreta.
    """
    sem = estado["semaphore"]
    frases = [_frase_seguridad(sem, estado["weather"])]
    donde = _frase_donde(estado.get("ipp_ranking") or [], estado.get("water") or {})
    if donde:
        frases.append(donde)

    # Un solo slot para "viejo", "anoxia" o "tendencia" (no varios a la vez) —
    # mantiene el mensaje en 3-4 oraciones. Prioridad: transparencia sobre el
    # dato > riesgo de anoxia (cuando está habilitado) > tendencia.
    viejo = _frase_dato_viejo(estado.get("edad_horas") or {})
    anoxia = _frase_anoxia(estado.get("senales") or {}) if _ANOXIA_EN_BOT else None
    if viejo:
        frases.append(viejo)
    elif anoxia:
        frases.append(anoxia)
    else:
        tendencia = _frase_tendencia(estado.get("tendencias") or {})
        if tendencia:
            frases.append(tendencia)

    frases.append(_frase_accion(sem.get("color")))
    return " ".join(frases)
