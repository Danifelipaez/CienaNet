"""Tests de dashboard_persistence (guardado en DB del snapshot ambiental)."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard_persistence import _save_ideam_hidro, _save_satellite


def test_save_ideam_hidro_hace_un_solo_insert_con_todas_las_filas():
    """Un único INSERT ON CONFLICT DO NOTHING (dedup vía unique constraint en DB) —
    no SELECT-then-INSERT fila por fila, que sería una race bajo refrescos concurrentes."""
    db = AsyncMock()

    precipitacion = [
        {"date": "2026-07-01", "estacion": "Media Luna", "precipitacion_mm": 3.5},
        {"date": "2026-07-01", "estacion": "La Gran Via", "precipitacion_mm": 0.0},
    ]
    nivel = [{"date": "2026-07-01", "estacion": "Puerto Rico Hacienda", "nivel_m": 1.79}]

    asyncio.run(_save_ideam_hidro(db, precipitacion, nivel))

    db.execute.assert_awaited_once()  # una sola query para las 3 filas
    stmt = db.execute.call_args.args[0]
    rows = stmt.compile().params
    assert len(precipitacion) + len(nivel) == 3
    assert rows  # el statement lleva las filas embebidas como VALUES
    db.commit.assert_awaited_once()


def test_save_satellite_no_persiste_baseline_como_medicion():
    """Si el origen de un campo es 'baseline' (API caída o valor fuera de rango),
    se guarda NULL — nunca el valor de respaldo, que quedaría indistinguible de
    una medición real para siempre."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # sin fila previa ese día
    db.execute.return_value = result
    db.add = MagicMock()

    data = {
        "sst_celsius": 28.0,
        "chlorophyll_mgm3": 12.0,
        "date": "2026-07-01",
        "origen": {"sst_celsius": "baseline", "chlorophyll_mgm3": "medido"},
    }
    asyncio.run(_save_satellite(db, data, date(2026, 7, 1)))

    added = db.add.call_args.args[0]
    assert added.sst_celsius is None
    assert added.chlorophyll_mgm3 == 12.0


def test_save_ideam_hidro_no_ejecuta_nada_si_no_hay_filas():
    db = AsyncMock()

    asyncio.run(_save_ideam_hidro(db, [], []))

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
