"""Alertas externas: ciclones tropicales NOAA NHC (V-03, KNOWLEDGE_BASE §4.3)."""

import logging
import re
import time

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
