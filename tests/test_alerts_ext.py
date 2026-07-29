"""Tests de app/services/ingestion/alerts_ext.py — limpieza de HTML y filtro
de contenido (boletines de rutina "sin actividad" no deben contar como alerta).
Mockea feedparser — sin red.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ingestion import alerts_ext


def _fake_client():
    resp = MagicMock()
    resp.text = "<rss></rss>"  # contenido real irrelevante: feedparser.parse va mockeado
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


def _entry(title, summary, link="https://www.nhc.noaa.gov/"):
    return SimpleNamespace(title=title, summary=summary, link=link)


def setup_function():
    alerts_ext._cache["data"] = None
    alerts_ext._cache["ts"] = 0.0


def _run_with_entries(entries):
    factory = _fake_client()
    fake_feed = MagicMock(entries=entries)
    with (
        patch.object(alerts_ext.httpx, "AsyncClient", factory),
        patch.object(alerts_ext.feedparser, "parse", return_value=fake_feed),
    ):
        return asyncio.run(alerts_ext.get_cyclone_alerts())


def test_limpia_br_y_tags_de_un_alerta_real():
    entries = [
        _entry(
            "Tropical Storm Example Advisory Number 5",
            "Storm intensifying.<br />Max winds 60 mph.<br/>Moving NW at 10 mph.",
        )
    ]

    out = _run_with_entries(entries)

    assert len(out) == 1
    assert "<br" not in out[0]["summary"]
    assert out[0]["summary"] == "Storm intensifying.\nMax winds 60 mph.\nMoving NW at 10 mph."


def test_descarta_boletin_de_outlook_sin_actividad():
    entries = [
        _entry(
            "Atlantic Tropical Weather Outlook",
            "Tropical cyclone formation is not expected during the next 7 days.",
        )
    ]

    out = _run_with_entries(entries)

    assert out == []


def test_descarta_boletin_sin_ciclones_activos():
    entries = [_entry("Tropical Cyclones", "There are no tropical cyclones at this time.")]

    out = _run_with_entries(entries)

    assert out == []


def test_mezcla_filtra_solo_lo_sin_actividad():
    entries = [
        _entry("Atlantic Tropical Weather Outlook", "Tropical cyclone formation is not expected."),
        _entry("Hurricane Example Advisory Number 1", "Hurricane Example is a category 2 storm."),
    ]

    out = _run_with_entries(entries)

    assert len(out) == 1
    assert out[0]["title"] == "Hurricane Example Advisory Number 1"
