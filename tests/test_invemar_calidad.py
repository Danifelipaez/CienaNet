"""Tests de la ingesta INVEMAR SIICGSM (calidad de agua). Mockea httpx — sin red."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.ingestion import invemar_calidad


def _fake_client(*, token_body: dict | None = None, data_body: list | None = None, raises: Exception | None = None):
    token_resp = MagicMock()
    token_resp.raise_for_status = MagicMock()
    token_resp.json = MagicMock(return_value=token_body or {"access_token": "tok", "expires_in": 3600})

    data_resp = MagicMock()
    data_resp.raise_for_status = MagicMock(side_effect=raises)
    data_resp.json = MagicMock(return_value=data_body or [])

    client = MagicMock()
    client.post = AsyncMock(side_effect=[token_resp, data_resp])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory, client


def setup_function():
    invemar_calidad._data_cache.clear()
    invemar_calidad._token_cache.clear()


def test_get_calidad_agua_normaliza_filas():
    body = [
        {
            "nomest": "Boca de la Barra", "sector": "Ciénaga Grande de Santa Marta",
            "nombre_var": "Oxigeno Disuelto", "prom": 8.71, "unidad": "mg/L",
            "clase": 5, "label": "> 8 mg/l", "lat": 10.99, "lon": -74.29,
            "factualizacion": "2025-08-29T09:31:42",
        }
    ]
    factory, client = _fake_client(data_body=body)
    with patch.object(invemar_calidad.httpx, "AsyncClient", factory):
        out = asyncio.run(invemar_calidad.get_calidad_agua("Oxigeno Disuelto"))

    assert out == [
        {
            "estacion": "Boca de la Barra", "sector": "Ciénaga Grande de Santa Marta",
            "variable": "Oxigeno Disuelto", "valor": 8.71, "unidad": "mg/L",
            "clase": 5, "rango": "> 8 mg/l", "lat": 10.99, "lon": -74.29,
            "actualizado": "2025-08-29T09:31:42",
        }
    ]
    client.post.assert_any_call(f"{invemar_calidad._BASE}/auth-api/token")


def test_fallback_a_cache_si_falla():
    ok_factory, _ = _fake_client(data_body=[{
        "nomest": "X", "sector": "Y", "nombre_var": "pH", "prom": 7.0, "unidad": "",
        "clase": 4, "label": "", "lat": 0, "lon": 0, "factualizacion": "",
    }])
    with patch.object(invemar_calidad.httpx, "AsyncClient", ok_factory):
        first = asyncio.run(invemar_calidad.get_calidad_agua("pH"))

    fail_factory, _ = _fake_client(raises=httpx.HTTPError("boom"))
    with patch.object(invemar_calidad.httpx, "AsyncClient", fail_factory):
        second = asyncio.run(invemar_calidad.get_calidad_agua("pH"))

    assert second == first


def test_fallback_a_lista_vacia_sin_cache_previo():
    factory, _ = _fake_client(raises=httpx.HTTPError("boom"))
    with patch.object(invemar_calidad.httpx, "AsyncClient", factory):
        out = asyncio.run(invemar_calidad.get_calidad_agua("Salinidad"))
    assert out == []
