"""Avisos del tiempo para pescadores (docs/AVISOS_CLIMA.md): viento fuerte, lluvia
fuerte y oleaje por consenso de modelos; alertas oficiales del IDEAM; ciclones y
frentes fríos del NHC; temporada seca/lluviosa próxima con el estado ENSO del CPC
(las oficiales y la temporada viven en avisos_oficiales.py).

Confiabilidad por consenso, no por un solo número: un aviso de pronóstico empuja
WhatsApp (`push`, nivel "alto") solo si al menos `aviso_consenso` modelos
independientes lo ven en las próximas `aviso_horas` h. Con un solo modelo queda
"medio" (dashboard, "posible"), y solo en ese caso se consulta Xweather como
desempate — así la cuota de Xweather se gasta únicamente cuando cambia la decisión.

Fuente caída = el tipo de aviso queda en `sin_revisar` (el dashboard y el bot lo
dicen): nunca se presenta "sin avisos" cuando en realidad no se pudo mirar.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.services.avisos_oficiales import (
    BOGOTA,
    aviso,
    aviso_frente_frio,
    avisos_ciclon,
    avisos_ideam,
    cuando,
    temporada_y_aviso,
)
from app.services.ingestion import avisos_ext, ideam_cap
from app.services.ingestion.alerts_ext import get_sistemas_sinopticos

Serie = dict[str, list]


def _ventana(serie: Serie, ahora: datetime, horas: int) -> list[int]:
    """Índices de `serie["times"]` (UTC naive, fin de hora) dentro de (ahora, ahora+horas]."""
    t0 = ahora.astimezone(UTC).replace(tzinfo=None)
    fin = t0 + timedelta(hours=horas)
    return [i for i, t in enumerate(serie["times"]) if t0 < datetime.fromisoformat(t) <= fin]


Regla = Callable[[Serie, int], tuple[bool, float] | None]


def _voto(serie: Serie, idx: list[int], regla: Regla) -> tuple[str | None, float | None]:
    """(primera hora que cumple la regla, máximo mostrado en la ventana) — hora None si
    no la cumple; máximo None si el modelo no tiene ningún dato en la ventana."""
    vals = [(i, r) for i in idx if (r := regla(serie, i)) is not None]
    if not vals:
        return None, None
    primera = next((i for i, (cumple, _) in vals if cumple), None)
    return (serie["times"][primera] if primera is not None else None), max(v for _, (_, v) in vals)


def _regla_viento(s: Serie, i: int) -> tuple[bool, float] | None:
    """Mismas dos reglas del semáforo rojo (sostenido o ráfaga); se muestra la ráfaga."""
    v, r = s["viento"][i], s["rafaga"][i]
    if v is None and r is None:
        return None
    cumple = (v or 0.0) >= settings.aviso_viento_kmh or (r or 0.0) >= settings.aviso_rafaga_kmh
    return cumple, max(v or 0.0, r or 0.0)


def _regla_lluvia(s: Serie, i: int) -> tuple[bool, float] | None:
    """Acumulado de las 6 h que terminan en `i` (Open-Meteo etiqueta cada hora con su fin)."""
    if i < 5:
        return None
    bloque = s["lluvia"][i - 5 : i + 1]
    if None in bloque:
        return None
    total = sum(bloque)
    return total >= settings.aviso_lluvia_mm_6h, total


def _regla_ola(s: Serie, i: int) -> tuple[bool, float] | None:
    h = s["ola"][i]
    return None if h is None else (h >= settings.aviso_ola_m, h)


def _consenso(series: dict[str, Serie], ahora: datetime, regla: Regla) -> dict:
    """Votos por modelo. Para lluvia, solo bloques de 6 h enteros dentro de la ventana."""
    votos = {}
    for nombre, s in series.items():
        idx = _ventana(s, ahora, settings.aviso_horas)
        if regla is _regla_lluvia:
            dentro = set(idx)
            idx = [i for i in idx if all(j in dentro for j in range(i - 5, i))]
        votos[nombre] = _voto(s, idx, regla)
    si = {n: (t, m) for n, (t, m) in votos.items() if t is not None}
    return {"si": si, "total": sum(1 for _, m in votos.values() if m is not None)}


def necesita_desempate(modelos: dict[str, Serie] | None, ahora: datetime) -> bool:
    """True si viento o lluvia quedan a un voto del consenso (p.ej. 1 de 3)."""
    if not modelos:
        return False
    faltan = settings.aviso_consenso - 1
    return any(
        len(_consenso(modelos, ahora, regla)["si"]) == faltan for regla in (_regla_viento, _regla_lluvia)
    )


def _de_consenso(tipo: str, c: dict, ahora: datetime, armar: Callable[[str, float], tuple[str, str]]) -> dict | None:
    """Aviso alto (push) con >= aviso_consenso votos, medio con uno solo, None sin votos.
    `armar(cuando, valor)` da (titulo, mensaje); valor = el que comparten al menos dos
    modelos (el segundo máximo), no el del modelo más alarmista. La hora es la primera
    en que algún modelo lo ve: para avisar, mejor temprano."""
    si = c["si"]
    if not si:
        return None
    primera = min(datetime.fromisoformat(t) for t, _ in si.values()).replace(tzinfo=UTC)
    maximos = sorted((m for _, m in si.values()), reverse=True)
    valor = maximos[1] if len(maximos) > 1 else maximos[0]
    nivel = "alto" if len(si) >= settings.aviso_consenso else "medio"
    titulo, mensaje = armar(cuando(primera, ahora), valor)
    return aviso(
        tipo, nivel, titulo if nivel == "alto" else f"Posible {titulo.lower()}", mensaje,
        f"{len(si)} de {c['total']} modelos ({', '.join(sorted(si))})",
        primera.astimezone(BOGOTA).date().isoformat(),  # clave: día local del evento
        primera.isoformat(),
    )


def evaluar_avisos(
    ahora: datetime,
    *,
    modelos: dict[str, Serie] | None = None,
    oleaje: dict[str, Serie] | None = None,
    ciclones: list[dict] | None = None,
    sinoptico: dict | None = None,
    enso: dict | None = None,
    ideam: list[dict] | None = None,
    xweather: Serie | None = None,
) -> dict:
    """Función pura: datos ya bajados -> avisos. None en una fuente = no se pudo revisar."""
    vigentes: list[dict] = []
    sin_revisar: list[str] = []
    frente = "frente_frio" in ((sinoptico or {}).get("sistemas") or [])
    extra_frente = " Hay un frente frío en el Caribe." if frente else ""

    if ideam is None:
        sin_revisar.append("ideam")
    else:
        vigentes += avisos_ideam(ideam, ahora)

    if not modelos or len(modelos) < settings.aviso_consenso:
        sin_revisar += ["viento", "lluvia"]  # sin modelos suficientes no hay consenso posible
    if modelos:
        votantes = {**modelos, **({"xweather": xweather} if xweather else {})}
        vigentes += [a for a in (
            _de_consenso("viento_fuerte", _consenso(votantes, ahora, _regla_viento), ahora, lambda cuando, v: (
                "Viento fuerte",
                f"💨 Viento fuerte {cuando}, con ráfagas de hasta {v:.0f} km/h.{extra_frente} Evita cruzar "
                "la ciénaga abierta, no te alejes de la orilla y asegura tu canoa.")),
            _de_consenso("lluvia_fuerte", _consenso(votantes, ahora, _regla_lluvia), ahora, lambda cuando, v: (
                "Lluvia fuerte",
                f"🌧️ Aguacero fuerte {cuando}, puede venir con tormenta eléctrica. Planea la faena "
                "para volver a tierra antes.")),
        ) if a]

    if not oleaje or len(oleaje) < settings.aviso_consenso:
        sin_revisar.append("oleaje")
    if oleaje:
        aviso_ola = _de_consenso("oleaje", _consenso(oleaje, ahora, _regla_ola), ahora, lambda cuando, v: (
            "Mar picado",
            f"🌊 Mar picado {cuando}: olas de hasta {v:.1f} m frente a la Boca de la Barra.{extra_frente} "
            "No salgas al mar en lancha pequeña."))
        if aviso_ola:
            vigentes.append(aviso_ola)

    if ciclones is None:
        sin_revisar.append("ciclon")
    else:
        vigentes += avisos_ciclon(ciclones)

    if sinoptico is None:
        sin_revisar.append("frente_frio")
    elif (a := aviso_frente_frio(sinoptico, ahora)) is not None:
        vigentes.append(a)

    t, aviso_temporada = temporada_y_aviso(ahora, enso)
    if aviso_temporada:
        vigentes.append(aviso_temporada)
    if enso is None:
        sin_revisar.append("enso")

    # Altos primero, luego por hora real (los `desde` traen offsets distintos: -05:00 IDEAM, +00:00 modelos).
    sin_hora = datetime.max.replace(tzinfo=UTC)
    vigentes.sort(key=lambda a: (a["nivel"] != "alto", datetime.fromisoformat(a["desde"]) if a["desde"] else sin_hora))
    # Misma (tipo, clave) = mismo aviso (p.ej. dos CAP del IDEAM del mismo evento y día para
    # cuencas distintas): uno solo, el de mayor nivel, o se enviaría dos veces el mismo texto.
    unicos: dict[tuple[str, str], dict] = {}
    for a in vigentes:
        unicos.setdefault((a["tipo"], a["clave"]), a)
    vigentes = list(unicos.values())
    return {
        "vigentes": vigentes, "temporada": t, "sin_revisar": sin_revisar, "horas": settings.aviso_horas,
        "actualizado": ahora.isoformat(),
    }


# ponytail: último resultado en memoria de proceso, igual que el nowcast de lluvia;
# un reinicio lo repone en el primer refresco horario.
_ultimo: dict | None = None


def get_avisos_cacheados() -> dict | None:
    """Último cálculo de avisos, sin red (None si este proceso todavía no calculó)."""
    return _ultimo


async def calcular_avisos() -> dict:
    """Baja las fuentes en paralelo y evalúa. Xweather solo si hay empate (ver arriba).
    El TWD sale de alerts_ext (cache de 1 h compartido con el snapshot)."""
    global _ultimo
    (modelos, o_mod), (oleaje, o_ola), (ciclones, o_cic), (enso, o_enso), (ideam, o_ideam), sinoptico = (
        await asyncio.gather(
            avisos_ext.get_pronostico_modelos(),
            avisos_ext.get_oleaje_modelos(),
            avisos_ext.get_ciclones_activos(),
            avisos_ext.get_estado_enso(),
            ideam_cap.get_alertas_ideam(),
            get_sistemas_sinopticos(),
        )
    )
    ahora = datetime.now(UTC)
    xweather, o_xw = None, "no_consultado"
    if avisos_ext.xweather_configurado() and necesita_desempate(modelos, ahora):
        xweather, o_xw = await avisos_ext.get_xweather_pronostico()
    result = evaluar_avisos(
        ahora, modelos=modelos, oleaje=oleaje, ciclones=ciclones, sinoptico=sinoptico, enso=enso,
        ideam=ideam, xweather=xweather,
    )
    result["origen"] = {
        "modelos": o_mod, "oleaje": o_ola, "ciclones": o_cic, "enso": o_enso, "ideam": o_ideam,
        "xweather": o_xw, "sinoptico": "medido" if sinoptico is not None else "sin_dato",
    }
    result["xweather_cuota"] = dict(avisos_ext.xweather_cuota)
    _ultimo = result
    return result
