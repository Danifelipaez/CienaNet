"""Alertas externas: ciclones tropicales NOAA NHC (V-03, KNOWLEDGE_BASE §4.3)."""

import logging
import time

import feedparser
import httpx

logger = logging.getLogger(__name__)

NHC_RSS = "https://www.nhc.noaa.gov/index-at.xml"
_TTL = 900.0  # 15 min: el feed cambia poco (buenas prácticas del doc)

# ponytail: cache de módulo, el feed es único y global
_cache: dict = {"data": None, "ts": 0.0}


async def get_cyclone_alerts() -> list[dict]:
    """Retorna alertas tropicales activas en el Atlántico. Lista vacía si la fuente falla."""
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL:
        return _cache["data"]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(NHC_RSS)
        feed = feedparser.parse(resp.text)
        alerts = [
            {"title": e.title, "summary": e.summary, "link": e.link}
            for e in feed.entries
            if "tropical" in e.title.lower() or "hurricane" in e.title.lower()
        ]
        _cache["data"] = alerts
        _cache["ts"] = now
        return alerts
    except Exception as exc:
        logger.warning("NOAA NHC RSS no disponible: %s", exc)
        return _cache["data"] if _cache["data"] is not None else []
