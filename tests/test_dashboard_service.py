"""Tests de los helpers de satélite en dashboard_service (reintento de filas NULL). Sin red."""

import time
from datetime import date
from unittest.mock import patch

from app.models.environmental import SatelliteData
from app.services import dashboard_service


def _fila(sst, chl) -> SatelliteData:
    return SatelliteData(source="nasa_mur", date=date(2026, 7, 1), sst_celsius=sst, chlorophyll_mgm3=chl)


def test_reintento_no_aplica_sin_fila_o_con_fila_completa():
    with patch.object(dashboard_service, "_sat_ultimo_reintento", None):
        assert dashboard_service._toca_reintento_satelite(None) is False
        assert dashboard_service._toca_reintento_satelite(_fila(29.0, 12.0)) is False
        assert dashboard_service._sat_ultimo_reintento is None  # una fila completa no consume el turno


def test_reintento_una_vez_por_ventana_y_de_nuevo_al_vencer():
    fila = _fila(None, 12.0)
    with patch.object(dashboard_service, "_sat_ultimo_reintento", None):
        assert dashboard_service._toca_reintento_satelite(fila) is True
        assert dashboard_service._toca_reintento_satelite(fila) is False  # dentro de la ventana
        dashboard_service._sat_ultimo_reintento = time.monotonic() - dashboard_service._SAT_REINTENTO_S - 1
        assert dashboard_service._toca_reintento_satelite(fila) is True


def test_sin_baseline_deja_none_y_sin_dato_solo_donde_hubo_baseline():
    sat = {
        "sst_celsius": 28.0,
        "chlorophyll_mgm3": 50.0,
        "date": "2026-07-01",
        "origen": {"sst_celsius": "baseline", "chlorophyll_mgm3": "medido"},
    }
    out = dashboard_service._sin_baseline(sat)
    assert out["sst_celsius"] is None
    assert out["chlorophyll_mgm3"] == 50.0
    assert out["origen"] == {"sst_celsius": "sin_dato", "chlorophyll_mgm3": "medido"}
    assert sat["sst_celsius"] == 28.0  # no muta el original
