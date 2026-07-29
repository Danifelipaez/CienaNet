"""Tests de app/services/system_status_service.py."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.services.system_status_service import (
    _satellite_status,
    _weather_status,
    get_system_status,
)


def test_weather_status_sin_dato_es_caido():
    assert _weather_status(None) == "caido"


def test_weather_status_reciente_es_ok():
    assert _weather_status(datetime.now(UTC) - timedelta(minutes=30)) == "ok"


def test_weather_status_unas_horas_es_degradado():
    assert _weather_status(datetime.now(UTC) - timedelta(hours=3)) == "degradado"


def test_weather_status_muy_viejo_es_caido():
    assert _weather_status(datetime.now(UTC) - timedelta(hours=10)) == "caido"


def test_satellite_status_sin_dato_es_caido():
    assert _satellite_status(None) == "caido"


def test_satellite_status_dentro_del_lag_esperado_es_ok():
    # jplMURSST41 tiene ~2 días de rezago normal — no es una falla (ver docstring).
    assert _satellite_status(date.today() - timedelta(days=1)) == "ok"


def test_satellite_status_pasado_el_lag_es_degradado():
    assert _satellite_status(date.today() - timedelta(days=5)) == "degradado"


def test_satellite_status_muy_viejo_es_caido():
    assert _satellite_status(date.today() - timedelta(days=10)) == "caido"


def test_get_system_status_sin_datos_no_truena():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar_one.return_value = 0
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result

    status = asyncio.run(get_system_status(db))

    assert [api["estado"] for api in status["apis"]] == ["caido", "caido"]
    assert all(m["valor"] == 0 for m in status["bot_metricas"])
    assert status["log_alertas"] == []
