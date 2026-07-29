"""Tests de snapshot_service.read_persisted — sin llamadas de red, solo DB mockeada."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.snapshot_service import read_persisted

_TENDENCIAS_VACIAS = {"variables": {}, "lluvia_72h_mm": None}


@pytest.fixture(autouse=True)
def _sin_tendencias(monkeypatch):
    """get_trends() hace sus propias queries de DB (ver test_trends.py) — se
    neutraliza acá para que el side_effect de _make_db() no tenga que anticipar
    llamadas ajenas a lo que cada test de read_persisted realmente ejercita."""

    async def _vacio(db):
        return _TENDENCIAS_VACIAS

    monkeypatch.setattr("app.services.snapshot_service.get_trends", _vacio)


def _result(scalar=None, scalars_all=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = scalars_all or []
    return r


def _make_db(weather=None, tasajera=None, satellite=None, semaphore=None, readings=None, ideam=None):
    """Orden de `db.execute` dentro de read_persisted: weather CGSM, weather
    Tasajera, satellite, semaphore, get_latest_readings, ideam."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=weather),
            _result(scalar=tasajera),
            _result(scalar=satellite),
            _result(scalar=semaphore),
            _result(scalars_all=readings or []),
            _result(scalars_all=ideam or []),
        ]
    )
    return db


def test_sin_ninguna_fuente_no_truena():
    db = _make_db()
    estado = asyncio.run(read_persisted(db))
    assert estado["semaphore"] == {"color": None, "reason": "Sin datos recientes"}
    assert estado["satellite"] == {
        "sst_celsius": None,
        "chlorophyll_mgm3": None,
        "date": None,
        "por_zona": {},
    }
    assert estado["ipp_ranking"] == []
    assert estado["edad_horas"] == {"weather": None, "satellite": None, "water": None}
    assert estado["tendencias"] == _TENDENCIAS_VACIAS


def test_tendencias_viaja_desde_get_trends(monkeypatch):
    esperado = {"variables": {"salinity_psu": {"actual": 18, "direccion": "bajando"}}, "lluvia_72h_mm": 12.0}

    async def _con_datos(db):
        return esperado

    monkeypatch.setattr("app.services.snapshot_service.get_trends", _con_datos)
    db = _make_db()
    estado = asyncio.run(read_persisted(db))
    assert estado["tendencias"] == esperado


def test_filtra_weather_por_estacion_cgsm():
    # Bug que esto reemplaza: points_service.py tomaba el WeatherSnapshot más
    # reciente sin filtrar estación (podía devolver viento de Tasajera).
    db = _make_db()
    asyncio.run(read_persisted(db))
    first_stmt = str(db.execute.call_args_list[0].args[0])
    assert "weather_snapshots.estacion" in first_stmt


def test_edad_horas_weather_se_calcula_en_horas():
    weather_row = MagicMock(
        timestamp=datetime.now(UTC) - timedelta(hours=2),
        temperature_c=30,
        humidity_pct=70,
        wind_speed_kmh=10,
        wind_direction_deg=90,
        wind_gust_kmh=15,
        precipitation_mm=0,
    )
    db = _make_db(weather=weather_row)
    estado = asyncio.run(read_persisted(db))
    assert 1.9 < estado["edad_horas"]["weather"] < 2.1
    assert estado["weather"]["wind_gust_kmh"] == 15


def test_ideam_separa_precipitacion_y_nivel():
    rows = [
        MagicMock(variable="precipitacion_mm", estacion="Media Luna", date=date(2026, 7, 1), valor=3.5),
        MagicMock(variable="nivel_m", estacion="Puerto Rico Hacienda", date=date(2026, 7, 1), valor=1.79),
    ]
    db = _make_db(ideam=rows)
    estado = asyncio.run(read_persisted(db))
    assert estado["ideam_precipitacion"] == [
        {"date": "2026-07-01", "estacion": "Media Luna", "precipitacion_mm": 3.5}
    ]
    assert estado["ideam_nivel_rio"] == [
        {"date": "2026-07-01", "estacion": "Puerto Rico Hacienda", "nivel_m": 1.79}
    ]


def test_ipp_ranking_viene_del_semaforo_persistido():
    semaphore_row = MagicMock(color="green", reason="Condiciones favorables", ipp_ranking=[{"zone": "X", "ipp": 80.0}])
    db = _make_db(semaphore=semaphore_row)
    estado = asyncio.run(read_persisted(db))
    assert estado["ipp_ranking"] == [{"zone": "X", "ipp": 80.0}]
    assert estado["semaphore"]["color"] == "green"
