"""Alertas externas: ciclones tropicales NOAA NHC (V-03, KNOWLEDGE_BASE §4.3) y
sistemas sinópticos del Caribe (frente frío, onda tropical, vaguada) leídos del
Tropical Weather Discussion de NHC."""

import html
import logging
import re
import time
from datetime import datetime, timezone

import feedparser
import httpx

logger = logging.getLogger(__name__)

NHC_RSS = "https://www.nhc.noaa.gov/index-at.xml"
_TTL = 900.0  # 15 min: el feed cambia poco (buenas prácticas del doc)

# ponytail: cache de módulo, el feed es único y global
_cache: dict = {"data": None, "ts": 0.0}

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

# Frases de boletines de rutina de NOAA que confirman que NO hay actividad —
# ponytail: filtro por palabra clave sobre texto libre, no infalible; si NOAA
# cambia la redacción esto puede colar un falso positivo. Si hace falta más
# certeza, migrar a la API estructurada https://www.nhc.noaa.gov/CurrentStorms.json
# (lista ciclones activos reales, sin ambigüedad de texto).
_NO_ACTIVITY_PHRASES = (
    "tropical cyclone formation is not expected",
    "there are no tropical cyclones",
    "no tropical cyclones at this time",
)


def _clean_summary(raw: str) -> str:
    text = _BR_RE.sub("\n", raw)
    text = _TAG_RE.sub("", text)
    return text.strip()


def _is_active_threat(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return not any(phrase in text for phrase in _NO_ACTIVITY_PHRASES)


async def get_cyclone_alerts() -> list[dict]:
    """Retorna alertas tropicales activas en el Atlántico. Lista vacía si la fuente falla
    o si no hay actividad real (boletines de rutina sin amenaza no cuentan como alerta)."""
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL:
        return _cache["data"]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(NHC_RSS)
        feed = feedparser.parse(resp.text)
        alerts = [
            {"title": e.title, "summary": _clean_summary(e.summary), "link": e.link}
            for e in feed.entries
            if ("tropical" in e.title.lower() or "hurricane" in e.title.lower())
            and _is_active_threat(e.title, e.summary)
        ]
        _cache["data"] = alerts
        _cache["ts"] = now
        return alerts
    except Exception as exc:
        logger.warning("NOAA NHC RSS no disponible: %s", exc)
        return _cache["data"] if _cache["data"] is not None else []


# El nombre viejo (axnt20.knhc.twdat.txt) da 301 -> 404 desde oct-2026.
TWD_URL = "https://tgftp.nws.noaa.gov/data/raw/ax/axnt20.knhc.twd.at.txt"
TWD_URL_HTML = "https://www.nhc.noaa.gov/text/MIATWDAT.shtml"
_TWD_TTL = 3600.0  # el TWD sale cada 6 h (00/06/12/18 UTC)
_twd_cache: dict = {"data": None, "ts": 0.0, "fallo_ts": None}
_TWD_FALLO_TTL = 300.0  # 5 min: tras una falla, no volver a pedir en cada request


def get_sinoptico_cacheado() -> dict | None:
    """Último TWD parseado ya en memoria, sin red (None si nunca se bajó).
    Para caminos de solo lectura como snapshot_service.read_persisted."""
    return _twd_cache["data"]

_SECCION_RE = re.compile(r"^\s*(?:\.{3})?\s*([A-Z][A-Z /,\-]{3,}?)\s*(?:\.{3})?\s*$", re.MULTILINE)
_ORACION_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_LON_W_RE = re.compile(r"(?<!\d)(\d{2}(?:\.\d)?)\s?W\b")
_REGION_RE = re.compile(r"caribbean|yucatan|cuba|colombia|panama|hispaniola|jamaica|honduras|nicaragua", re.I)
_CONVECCION_RE = re.compile(r"convection|showers|thunderstorms|squalls|rain", re.I)
# Dónde ubica la oración el sistema: términos que el NHC usa para el SW/centro-sur del Caribe.
_AFECTA_RE = re.compile(
    r"colombia|(?:sw|southwestern|south[- ]central|southern) caribbean|magdalena|santa marta|barranquilla|cartagena|guajira",
    re.I,
)
# (tipo, patrón del sistema, exige convección asociada en la oración o la siguiente)
_SISTEMAS = (
    ("frente_frio", re.compile(r"\b(?:cold|stationary) front\b", re.I), False),
    ("onda_tropical", re.compile(r"\btropical wave\b", re.I), False),
    ("vaguada", re.compile(r"\b(?:surface|monsoon) trough\b", re.I), True),
    ("baja_presion", re.compile(r"\blow pressure\b|\bsurface low\b|\d{3,4}\s?mb low\b", re.I), True),
)
_SECCIONES_UTILES = ("CARIBBEAN SEA", "TROPICAL WAVES", "MONSOON TROUGH")


def _twd_a_texto(raw: str) -> str:
    """HTML (fallback MIATWDAT.shtml) -> texto plano; el .txt crudo pasa casi igual."""
    return html.unescape(_TAG_RE.sub("", raw))


def _secciones_twd(texto: str) -> dict[str, str]:
    """Parte el TWD en secciones por sus encabezados en mayúsculas (`...CARIBBEAN SEA...`)."""
    marcas = list(_SECCION_RE.finditer(texto))
    return {
        m.group(1).strip(): texto[m.end() : marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)]
        for i, m in enumerate(marcas)
    }


def _emitido_twd(texto: str, ahora: datetime) -> str | None:
    """Fecha de emisión (UTC, ISO) del encabezado WMO `AXNT20 KNHC DDHHMM`."""
    m = re.search(r"AXNT20 KNHC (\d{2})(\d{2})(\d{2})", texto)
    if not m:
        return None
    dia, hh, mm = (int(g) for g in m.groups())
    anio, mes = ahora.year, ahora.month
    if dia > ahora.day:  # emisión del mes anterior (cambio de mes)
        anio, mes = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    try:
        return datetime(anio, mes, dia, hh, mm, tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def parse_twd(texto: str, ahora: datetime | None = None) -> dict:
    """Detecta sistemas sinópticos en las secciones del Caribe del TWD.

    Trabaja por oración. `afecta_cgsm` exige que la MISMA oración ubique el
    sistema en Colombia / SW o centro-sur del Caribe / Magdalena / Santa Marta,
    o que un eje de onda caiga entre 73.5W y 75.5W (la CGSM está en 74.5W). Un
    frente frío en el Canal de Yucatán es un sistema pero NO afecta. Vaguada y
    baja exigen además convección en esa oración o la siguiente: la vaguada
    monzónica de Colombia/Panamá aparece en el TWD casi a diario y sin lluvia
    asociada marcarla "afecta" sería ruido permanente.

    ponytail: regex sobre texto libre; si el NHC cambia la redacción puede dar
    falsos negativos (lista vacía) en silencio. No sustituye al GEFS: da contexto.
    """
    ahora = ahora or datetime.now(timezone.utc)
    secciones = {
        k: v for k, v in _secciones_twd(texto).items() if any(k.startswith(u) for u in _SECCIONES_UTILES)
    }
    if not secciones:
        logger.warning("TWD sin secciones del Caribe reconocibles — ¿cambió el formato?")

    tipos: list[str] = []
    afectan: list[str] = []  # qué sistemas en concreto afectan (afecta_cgsm no dice cuál)
    afecta, extracto = False, None
    for nombre, cuerpo in secciones.items():
        oraciones = [" ".join(o.split()) for o in _ORACION_RE.split(cuerpo.strip()) if o.strip()]
        for i, oracion in enumerate(oraciones):
            contexto = " ".join(oraciones[i : i + 2])
            en_caribe = nombre.startswith("CARIBBEAN") or bool(_REGION_RE.search(oracion))
            lons = [float(x) for x in _LON_W_RE.findall(oracion)]
            for tipo, patron, exige_conveccion in _SISTEMAS:
                if not patron.search(oracion):
                    continue
                if tipo == "onda_tropical":
                    # El eje de la onda va en grados W, sin nombre de región.
                    if not (any(70 <= x <= 80 for x in lons) or re.search("colombia", oracion, re.I)):
                        continue  # onda lejos de 70W-80W: no es del Caribe sudoccidental
                elif not en_caribe:
                    continue
                if tipo not in tipos:
                    tipos.append(tipo)
                cerca = bool(_AFECTA_RE.search(oracion)) or any(73.5 <= x <= 75.5 for x in lons)
                if exige_conveccion:
                    cerca = cerca and bool(_CONVECCION_RE.search(contexto))
                if cerca and tipo not in afectan:
                    afectan.append(tipo)
                if cerca and not afecta:
                    afecta, extracto = True, oracion[:300]  # primera oración que afecta gana
                elif extracto is None and not afecta:
                    extracto = oracion[:300]
    return {
        "sistemas": tipos,
        "afecta_cgsm": afecta,
        "afectan": afectan,
        "extracto": extracto,
        "emitido": _emitido_twd(texto, ahora),
    }


async def get_sistemas_sinopticos() -> dict | None:
    """Sistemas sinópticos (frente frío, onda tropical, vaguada, baja) en el Caribe
    según el TWD del NHC — el "evento estacional" de las lluvias de oct-nov
    (docs/ALERTAS_LLUVIA.md). Solo contexto de dashboard, nunca dispara push.

    Prueba el texto crudo de tgftp y, si falla, la página HTML del NHC. None si
    ambas fallan y no hay cache; con cache vencido devuelve el último resultado.
    """
    now = time.monotonic()
    if _twd_cache["data"] is not None and now - _twd_cache["ts"] < _TWD_TTL:
        return _twd_cache["data"]
    fallo = _twd_cache["fallo_ts"]
    if fallo is not None and now - fallo < _TWD_FALLO_TTL:
        return _twd_cache["data"]
    for url in (TWD_URL, TWD_URL_HTML):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            texto = _twd_a_texto(resp.text)
            if "TROPICAL WEATHER DISCUSSION" not in texto.upper():
                raise ValueError("respuesta que no parece un TWD")
            result = parse_twd(texto)
            _twd_cache["data"], _twd_cache["ts"], _twd_cache["fallo_ts"] = result, now, None
            return result
        except Exception as exc:
            logger.warning("NHC TWD no disponible (%s): %s", url.split("/")[2], exc)
    _twd_cache["fallo_ts"] = now
    return _twd_cache["data"]
