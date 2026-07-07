"""Tests del respaldo en DB de datos IDEAM — foco en la deduplicación pedida."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard_service import _save_ideam_hidro


def _result(scalar):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    return r


def test_save_ideam_hidro_inserta_solo_filas_nuevas():
    """Fila ya existente (mismo variable+estacion+date) se salta; la nueva se inserta."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(None), _result(MagicMock())])
    db.add = MagicMock()

    precipitacion = [
        {"date": "2026-07-01", "estacion": "Media Luna", "precipitacion_mm": 3.5},
        {"date": "2026-07-01", "estacion": "La Gran Via", "precipitacion_mm": 0.0},
    ]

    asyncio.run(_save_ideam_hidro(db, precipitacion, []))

    assert db.add.call_count == 1
    added = db.add.call_args.args[0]
    assert added.estacion == "Media Luna"
    assert added.valor == 3.5
    assert added.variable == "precipitacion_mm"
    db.commit.assert_awaited_once()


def test_save_ideam_hidro_no_inserta_si_todo_ya_existe():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(MagicMock()))
    db.add = MagicMock()

    nivel = [{"date": "2026-07-01", "estacion": "Puerto Rico Hacienda", "nivel_m": 1.79}]

    asyncio.run(_save_ideam_hidro(db, [], nivel))

    db.add.assert_not_called()
    db.commit.assert_awaited_once()
