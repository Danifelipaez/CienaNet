"""Tests del respaldo en DB de datos IDEAM y del contexto de IA."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard_service import _save_ideam_hidro, build_ai_context


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


_BASE_SNAPSHOT = {
    "semaphore": {"color": "green", "reason": "Condiciones favorables", "safe": True},
    "satellite": {"sst_celsius": 27.4, "chlorophyll_mgm3": 3.8, "date": "2026-07-08"},
    "weather": {"temperature_c": 32.2, "humidity_pct": 70.0, "wind_speed_kmh": 9.8, "precipitation_mm": 0.0},
}


def test_build_ai_context_incluye_cgsm_sin_tasajera_ni_ideam():
    """Sin tasajera_weather/ideam_* en el snapshot (compatibilidad hacia atrás), solo CGSM."""
    texto = build_ai_context(_BASE_SNAPSHOT)
    assert "CGSM" in texto
    assert "humedad 70.0%" in texto
    assert "Tasajera" not in texto
    assert "IDEAM" not in texto


def test_build_ai_context_incluye_tasajera_y_ultima_lectura_ideam_por_estacion():
    """Con tasajera_weather e IDEAM presentes, toma la lectura más reciente por estación."""
    snapshot = {
        **_BASE_SNAPSHOT,
        "tasajera_weather": {"temperature_c": 27.3, "humidity_pct": 88.0, "wind_speed_kmh": 42.9, "precipitation_mm": 0.0},
        "ideam_precipitacion": [
            {"date": "2026-07-01", "estacion": "Media Luna", "precipitacion_mm": 3.5},
            {"date": "2026-07-03", "estacion": "Media Luna", "precipitacion_mm": 1.2},
        ],
        "ideam_nivel_rio": [{"date": "2026-07-02", "estacion": "Puerto Rico Hacienda", "nivel_m": 1.79}],
    }
    texto = build_ai_context(snapshot)
    assert "Tasajera" in texto and "humedad 88.0%" in texto
    assert "Media Luna 1.2 mm (2026-07-03)" in texto  # la más reciente, no la primera
    assert "Puerto Rico Hacienda 1.79 m (2026-07-02)" in texto
