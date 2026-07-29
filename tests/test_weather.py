"""Tests de la ingesta Open-Meteo (ráfagas). Mockea httpx — sin red."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ingestion import weather


def _fake_client(*, current: dict):
    """Devuelve un mock usable como `async with httpx.AsyncClient(...) as c`
    (mismo patrón que tests/test_ideam_hidro.py)."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"current": current})

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory, client


def setup_function():
    weather._cache.clear()


def test_get_weather_forecast_incluye_rafaga():
    current = {
        "temperature_2m": 30.0,
        "relative_humidity_2m": 70.0,
        "wind_speed_10m": 15.0,
        "wind_direction_10m": 90.0,
        "wind_gusts_10m": 28.5,
        "precipitation": 0.0,
    }
    factory, client = _fake_client(current=current)
    with patch.object(weather.httpx, "AsyncClient", factory):
        out = asyncio.run(weather.get_weather_forecast(1.23, 4.56))

    assert out["wind_gust_kmh"] == 28.5
    assert out["origen"] == "medido"
    params = client.get.call_args.kwargs["params"]
    assert "wind_gusts_10m" in params["current"]


def test_fallback_sin_cache_incluye_clave_rafaga_en_none():
    # La clave debe existir aunque en None: si desaparece justo cuando falla la
    # API, el consumidor no puede distinguir "sin dato" de "no implementado".
    client_that_raises = MagicMock()
    client_that_raises.get = AsyncMock(side_effect=Exception("boom"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_that_raises)
    ctx.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(weather.httpx, "AsyncClient", MagicMock(return_value=ctx)),
        patch.object(weather.asyncio, "sleep", AsyncMock()),  # sin esperar los reintentos reales
    ):
        out = asyncio.run(weather.get_weather_forecast(9.87, 6.54))

    assert "wind_gust_kmh" in out
    assert out["wind_gust_kmh"] is None
    assert out["origen"] == "sin_dato"


def test_fallback_a_cache_marca_origen_cache():
    # Fetch fresco falla pero hay cache vigente (aunque su TTL ya venció, o no
    # habríamos llegado aquí) — sigue siendo el mejor dato disponible, pero debe
    # distinguirse de "medido" para no ocultar que está rancio.
    ok_factory, _ = _fake_client(
        current={
            "temperature_2m": 30.0,
            "relative_humidity_2m": 70.0,
            "wind_speed_10m": 15.0,
            "wind_direction_10m": 90.0,
            "wind_gusts_10m": 28.5,
            "precipitation": 0.0,
        }
    )
    with patch.object(weather.httpx, "AsyncClient", ok_factory):
        asyncio.run(weather.get_weather_forecast(3.33, 3.33))

    client_that_raises = MagicMock()
    client_that_raises.get = AsyncMock(side_effect=Exception("boom"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_that_raises)
    ctx.__aexit__ = AsyncMock(return_value=False)
    # Fuerza a que el próximo fetch entre a la rama de reintentos fallidos
    # aunque el cache siga "vigente" en TTL, parcheando el TTL a 0.
    with (
        patch.object(weather, "_TTL", -1.0),
        patch.object(weather.httpx, "AsyncClient", MagicMock(return_value=ctx)),
        patch.object(weather.asyncio, "sleep", AsyncMock()),
    ):
        out = asyncio.run(weather.get_weather_forecast(3.33, 3.33))

    assert out["origen"] == "cache"
    assert out["wind_gust_kmh"] == 28.5
