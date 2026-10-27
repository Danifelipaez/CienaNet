"""Tests de dashboard_persistence (guardado en DB del snapshot ambiental)."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.models.environmental import SatelliteData
from app.services.dashboard_persistence import _save_ideam_hidro, _save_invemar_calidad, _save_satellite


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


def _db_con_fila_existente(existing: SatelliteData) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute.return_value = result
    db.add = MagicMock()
    return db


def _fila(sst=None, chl=None, por_zona=None) -> SatelliteData:
    return SatelliteData(
        source="nasa_mur", date=date(2026, 7, 1), sst_celsius=sst, chlorophyll_mgm3=chl, por_zona=por_zona
    )


_MEDIDO = {"sst_celsius": "medido", "chlorophyll_mgm3": "medido"}


def test_save_satellite_reintento_rellena_solo_los_campos_nulos():
    """Un día guardado con NULL por una falla puntual de la API se completa en el
    reintento, sin crear una fila duplicada."""
    existing = _fila(sst=None, chl=12.0)
    db = _db_con_fila_existente(existing)
    data = {"sst_celsius": 29.9, "chlorophyll_mgm3": 99.0, "date": "2026-07-01", "origen": _MEDIDO}

    asyncio.run(_save_satellite(db, data, date(2026, 7, 1)))

    assert existing.sst_celsius == 29.9
    assert existing.chlorophyll_mgm3 == 12.0  # la medición ya guardada no se pisa
    db.add.assert_not_called()
    db.commit.assert_awaited_once()


def test_save_satellite_reintento_con_baseline_o_sin_cambios_no_toca_nada():
    existing = _fila(sst=None, chl=None)
    db = _db_con_fila_existente(existing)
    data = {
        "sst_celsius": 28.0,
        "chlorophyll_mgm3": 4.5,
        "date": "2026-07-01",
        "origen": {"sst_celsius": "baseline", "chlorophyll_mgm3": "baseline"},
    }

    asyncio.run(_save_satellite(db, data, date(2026, 7, 1)))

    assert existing.sst_celsius is None and existing.chlorophyll_mgm3 is None
    db.commit.assert_not_awaited()


def test_save_satellite_reintento_fusiona_por_zona_sin_pisar_lo_medido():
    existing = _fila(sst=29.0, chl=None, por_zona={"Nueva Venecia": {"sst_celsius": 29.1}})
    db = _db_con_fila_existente(existing)
    data = {
        "sst_celsius": 30.0,
        "chlorophyll_mgm3": 50.0,
        "date": "2026-07-01",
        "origen": _MEDIDO,
        "por_zona": {
            "Nueva Venecia": {"sst_celsius": 99.9, "chlorophyll_mgm3": 48.0},
            "Buenavista": {"chlorophyll_mgm3": 52.0},
        },
    }

    asyncio.run(_save_satellite(db, data, date(2026, 7, 1)))

    assert existing.por_zona == {
        "Nueva Venecia": {"sst_celsius": 29.1, "chlorophyll_mgm3": 48.0},
        "Buenavista": {"chlorophyll_mgm3": 52.0},
    }
    assert existing.sst_celsius == 29.0 and existing.chlorophyll_mgm3 == 50.0


def test_save_ideam_hidro_no_ejecuta_nada_si_no_hay_filas():
    db = AsyncMock()

    asyncio.run(_save_ideam_hidro(db, [], []))

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_save_invemar_calidad_hace_un_solo_upsert_con_todas_las_filas():
    """Un único INSERT ON CONFLICT DO UPDATE — a diferencia de ideam_hidro, acá SÍ
    se sobreescribe: no hay 'día' que preservar, el dato ya es el vigente."""
    db = AsyncMock()

    filas = [
        {"estacion": "Boca de la Barra", "sector": "CGSM", "variable": "Oxigeno Disuelto", "valor": 8.71, "unidad": "mg/L", "clase": 5, "rango": "> 8 mg/l", "lat": 10.99, "lon": -74.29, "actualizado": "2025-08-29T09:31:42"},
        {"estacion": "Río Córdoba", "sector": "Isla Aguja", "variable": "pH", "valor": 7.5, "unidad": "", "clase": 4, "rango": "", "lat": 11.03, "lon": -74.2, "actualizado": "2025-08-29T09:31:42"},
    ]

    asyncio.run(_save_invemar_calidad(db, filas))

    db.execute.assert_awaited_once()
    stmt = db.execute.call_args.args[0]
    assert stmt.compile().params  # el statement lleva las filas embebidas como VALUES
    db.commit.assert_awaited_once()


def test_save_invemar_calidad_no_ejecuta_nada_si_no_hay_filas():
    db = AsyncMock()

    asyncio.run(_save_invemar_calidad(db, []))

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
