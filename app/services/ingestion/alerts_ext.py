"""Alertas externas: ciclones tropicales NOAA NHC (V-03, KNOWLEDGE_BASE §4.3)."""

import logging

import feedparser
import httpx

logger = logging.getLogger(__name__)

NHC_RSS = "https://www.nhc.noaa.gov/index-at.xml"


async def get_cyclone_alerts() -> list[dict]:
    """Retorna alertas tropicales activas en el Atlántico. Lista vacía si la fuente falla."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(NHC_RSS)
        feed = feedparser.parse(resp.text)
        return [
            {"title": e.title, "summary": e.summary, "link": e.link}
            for e in feed.entries
            if "tropical" in e.title.lower() or "hurricane" in e.title.lower()
        ]
    except Exception as exc:
        logger.warning("NOAA NHC RSS no disponible: %s", exc)
        return []
