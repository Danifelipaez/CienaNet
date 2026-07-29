"""Tests del respaldo en DB de datos IDEAM y del contexto de IA."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard_service import _save_ideam_hidro, _save_satellite, build_ai_context


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


def test_build_ai_context_nombra_las_fuentes_reales():
    # "Copernicus Marine"/"NASA MODIS" eran falsos: la clorofila viene de
    # Sentinel-3 OLCI vía NOAA CoastWatch y la SST de NASA MUR (jplMURSST41),
    # ver app/services/ingestion/satellite.py.
    texto = build_ai_context(_BASE_SNAPSHOT)
    assert "OLCI" in texto
    assert "MUR" in texto
    assert "MODIS" not in texto
    assert "Copernicus Marine" not in texto


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
