"""Tests de la ingesta IDEAM (precipitación + nivel de río). Mockea httpx — sin red."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.ingestion import ideam_hidro


def _fake_client(*, json_body: list | None = None, raises: Exception | None = None):
    """Devuelve un mock usable como `async with httpx.AsyncClient(...) as c`."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=raises)
    resp.json = MagicMock(return_value=json_body or [])

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory, client


def setup_function():
    ideam_hidro._cache.clear()


def test_get_precipitacion_historia_parsea_filas():
    body = [
        {"fecha": "2026-07-01T00:00:00.000", "codigoestacion": "0029065000", "nombreestacion": "MEDIA LUNA", "precipitacion_mm": "3.5"},
        {"fecha": "2026-07-02T00:00:00.000", "codigoestacion": "0029065130", "nombreestacion": "LA GRAN VIA", "precipitacion_mm": "0"},
    ]
    factory, _ = _fake_client(json_body=body)
    with patch.object(ideam_hidro.httpx, "AsyncClient", factory):
        out = asyncio.run(ideam_hidro.get_precipitacion_historia(days=7))
    assert out == [
        {"date": "2026-07-01", "estacion": "Media Luna", "precipitacion_mm": 3.5},
        {"date": "2026-07-02", "estacion": "La Gran Via", "precipitacion_mm": 0.0},
    ]


def test_get_nivel_historia_ignora_filas_sin_valor():
    body = [
        {"fecha": "2026-07-01T00:00:00.000", "codigoestacion": "0029067060", "nombreestacion": "PUERTO RICO HACIENDA", "nivel_m": "1.79"},
        {"fecha": "2026-07-01T00:00:00.000", "codigoestacion": "0029067150", "nombreestacion": "GANADERIA CARIBE", "nivel_m": None},
    ]
    factory, _ = _fake_client(json_body=body)
    with patch.object(ideam_hidro.httpx, "AsyncClient", factory):
        out = asyncio.run(ideam_hidro.get_nivel_historia(days=7))
    assert out == [{"date": "2026-07-01", "estacion": "Puerto Rico Hacienda", "nivel_m": 1.79}]


def test_fallback_a_cache_si_falla():
    ok_factory, _ = _fake_client(
        json_body=[{"fecha": "2026-07-01T00:00:00.000", "codigoestacion": "0029065000", "nombreestacion": "MEDIA LUNA", "precipitacion_mm": "1"}]
    )
    with patch.object(ideam_hidro.httpx, "AsyncClient", ok_factory):
        first = asyncio.run(ideam_hidro.get_precipitacion_historia(days=7))

    fail_factory, _ = _fake_client(raises=httpx.HTTPError("boom"))
    with patch.object(ideam_hidro.httpx, "AsyncClient", fail_factory):
        second = asyncio.run(ideam_hidro.get_precipitacion_historia(days=7))

    assert second == first


def test_fallback_a_lista_vacia_sin_cache_previo():
    factory, _ = _fake_client(raises=httpx.HTTPError("boom"))
    with patch.object(ideam_hidro.httpx, "AsyncClient", factory):
        out = asyncio.run(ideam_hidro.get_nivel_historia(days=7))
    assert out == []
