"""Tests de app/services/trends.py — tendencias 24h/7d desde lo persistido, sin red."""

import asyncio
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from app.services.trends import _delta, _direccion, _serie_diaria_sensores, _variable, get_trends


# ── helpers puros: sin DB, sin mocks ────────────────────────────────────────────


def test_delta_toma_el_valor_mas_cercano_a_n_dias():
    serie = [(date(2026, 7, 1), 10.0), (date(2026, 7, 3), 12.0), (date(2026, 7, 8), 15.0)]
    # delta a 7 días desde el último punto (07-08) → objetivo 07-01. El punto más
    # cercano a esa fecha es (07-01, 10.0), no (07-03, 12.0).
    assert _delta(serie, 7) == 5.0


def test_delta_sin_historico_es_none():
    assert _delta([(date(2026, 7, 8), 15.0)], 7) is None
    assert _delta([], 7) is None


def test_direccion_banda_muerta():
    assert _direccion(0.3, 1.0) == "estable"


def test_direccion_subiendo_y_bajando():
    assert _direccion(2.0, 1.0) == "subiendo"
    assert _direccion(-2.0, 1.0) == "bajando"


def test_direccion_sin_dato_es_none():
    # No inventa "estable" cuando falta el histórico — None es una respuesta
    # distinta a "no hay tendencia", es "no lo sé".
    assert _direccion(None, 1.0) is None


def test_variable_vacia_es_none():
    assert _variable([], 1.0) is None


def test_variable_con_datos():
    # Con un único punto histórico, delta_24h y delta_7d caen sobre el mismo
    # punto más cercano disponible — _delta no exige que esté a esa distancia
    # exacta, solo toma el más cercano (ver honestidad del campo en trends.py).
    serie = [(date(2026, 7, 1), 10.0), (date(2026, 7, 8), 15.0)]
    v = _variable(serie, 1.0)
    assert v == {"actual": 15.0, "delta_24h": 5.0, "delta_7d": 5.0, "direccion": "subiendo"}


# ── serie diaria de sensores: agrupa por día y deriva salinidad del promedio ────


def _result(scalars_all=None):
    r = MagicMock()
    r.scalars.return_value.all.return_value = scalars_all or []
    return r


def test_serie_diaria_sensores_agrupa_por_dia_y_deriva_salinidad():
    # C=42.914 mS/cm, t=15°C → SP=35.0 (punto de definición PSS-78, test_derived.py)
    r1 = MagicMock(
        timestamp=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
        conductivity_mscm=42.914,
        temperature_c=15.0,
        water_level_cm=50.0,
    )
    r2 = MagicMock(
        timestamp=datetime(2026, 7, 8, 8, 0, tzinfo=UTC),
        conductivity_mscm=42.914,
        temperature_c=15.0,
        water_level_cm=60.0,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(scalars_all=[r1, r2]))

    salinidad, nivel = asyncio.run(_serie_diaria_sensores(db))

    assert salinidad == [(date(2026, 7, 1), 35.0), (date(2026, 7, 8), 35.0)]
    assert nivel == [(date(2026, 7, 1), 50.0), (date(2026, 7, 8), 60.0)]


# ── get_trends end-to-end: DB mockeada, cero red ────────────────────────────────


def test_get_trends_sin_datos_no_truena():
    db = AsyncMock()
    # sensores, satélite, ideam (lluvia) → vacío, dispara el fallback a weather
    db.execute = AsyncMock(side_effect=[_result(), _result(), _result(), _result()])
    estado = asyncio.run(get_trends(db))
    assert estado == {"variables": {}, "lluvia_72h_mm": None}


def test_get_trends_lluvia_suma_ideam_sin_fallback():
    ideam_rows = [MagicMock(valor=10.0), MagicMock(valor=5.0)]
    db = AsyncMock()
    # sensores, satélite, ideam (con filas) → no llega a pedir weather
    db.execute = AsyncMock(side_effect=[_result(), _result(), _result(scalars_all=ideam_rows)])
    estado = asyncio.run(get_trends(db))
    assert estado["lluvia_72h_mm"] == 15.0
    assert db.execute.call_count == 3
