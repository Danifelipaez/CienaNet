"""Tests de ingesta satelital: procedencia medido/baseline y desglose por zona. Sin red."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ingestion import satellite


def test_get_sst_baseline_si_falla():
    with patch.object(satellite, "_fetch_sst", side_effect=Exception("boom")):
        result = asyncio.run(satellite.get_sst())
    assert result == {"box": satellite._SST_BASELINE, "origen": "baseline", "por_zona": {}}


def test_get_sst_medido_si_ok():
    esperado = {"box": 27.3, "origen": "medido", "por_zona": {"Tasajera/Puebloviejo": 27.1}}
    with patch.object(satellite, "_fetch_sst", return_value=esperado):
        result = asyncio.run(satellite.get_sst())
    assert result == esperado


def _fake_client(*, json_body: dict):
    """Mismo patrón que tests/test_ideam_hidro.py — mock usable como
    `async with httpx.AsyncClient(...) as c`."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_body)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


_COLS = ["time", "latitude", "longitude", "chlor_a"]


def test_get_chlorophyll_baseline_sin_pixeles_validos():
    body = {"table": {"columnNames": _COLS, "rows": [["t", 10.9, -74.5, None]]}}
    with patch.object(satellite.httpx, "AsyncClient", _fake_client(json_body=body)):
        result = asyncio.run(satellite.get_chlorophyll())
    assert result["box"] == satellite._CHL_BASELINE
    assert result["origen"] == "baseline"
    assert result["por_zona"] == {}


def test_get_chlorophyll_medido_con_pixeles_validos():
    body = {"table": {"columnNames": _COLS, "rows": [["t", 10.9, -74.5, 12.5]]}}
    with patch.object(satellite.httpx, "AsyncClient", _fake_client(json_body=body)):
        result = asyncio.run(satellite.get_chlorophyll())
    assert result["box"] == 12.5
    assert result["origen"] == "medido"


def test_mean_near_promedia_solo_el_vecindario():
    rows = [
        ["t", 10.0, -74.0, 20.0],   # dentro del radio
        ["t", 10.01, -74.01, 30.0],  # dentro del radio
        ["t", 11.0, -75.0, 999.0],  # lejos — no debe contarse
    ]
    resultado = satellite._mean_near(rows, _COLS, lat=10.0, lon=-74.0, radius_deg=0.045)
    assert resultado == 25.0


def test_mean_near_sin_pixeles_devuelve_none():
    rows = [["t", 11.0, -75.0, 20.0]]  # ningún píxel dentro del radio
    assert satellite._mean_near(rows, _COLS, lat=10.0, lon=-74.0, radius_deg=0.045) is None


def test_get_chlorophyll_desglosa_por_zona_cercana():
    # Dos píxeles justo en el centroide de Tasajera/Puebloviejo (10.976111,
    # -74.325833) y uno lejos de cualquier zona — solo el cercano promedia.
    body = {
        "table": {
            "columnNames": _COLS,
            "rows": [
                ["t", 10.976111, -74.325833, 20.0],
                ["t", 10.976111, -74.325833, 24.0],
                ["t", 10.60, -74.60, 60.0],  # a >0.1° de cualquier centroide de zona
            ],
        }
    }
    with patch.object(satellite.httpx, "AsyncClient", _fake_client(json_body=body)):
        result = asyncio.run(satellite.get_chlorophyll())
    assert result["por_zona"]["Tasajera/Puebloviejo"] == 22.0
    assert "Suroccidente" not in result["por_zona"]


def test_get_satellite_data_combina_por_zona_de_sst_y_clorofila():
    sst_result = {"box": 28.0, "origen": "medido", "por_zona": {"Tasajera/Puebloviejo": 27.5}}
    chl_result = {
        "box": 12.0,
        "origen": "medido",
        "por_zona": {"Tasajera/Puebloviejo": 22.0, "Nueva Venecia": 15.0},
    }
    with (
        patch.object(satellite, "get_sst", new_callable=AsyncMock, return_value=sst_result),
        patch.object(satellite, "get_chlorophyll", new_callable=AsyncMock, return_value=chl_result),
    ):
        out = asyncio.run(satellite.get_satellite_data())

    assert out["sst_celsius"] == 28.0
    assert out["chlorophyll_mgm3"] == 12.0
    assert out["origen"] == {"sst_celsius": "medido", "chlorophyll_mgm3": "medido"}
    # Tasajera tiene ambas métricas; Nueva Venecia solo clorofila — no se
    # fabrica un sst_celsius que no llegó.
    assert out["por_zona"]["Tasajera/Puebloviejo"] == {"sst_celsius": 27.5, "chlorophyll_mgm3": 22.0}
    assert out["por_zona"]["Nueva Venecia"] == {"chlorophyll_mgm3": 15.0}
    assert "Buenavista" not in out["por_zona"]


def test_bounding_box_contiene_los_vertices_medidos():
    # docs/KNOWLEDGE_BASE.md §12: Vértice NE (Tasajera) 10.976111,-74.325833;
    # Vértice Sur 10.543611,-74.510000; Vértice NW 11.009444,-74.681944.
    # El box ajustado debe seguir cubriendo el vértice NE y NW usados a diario
    # (el Sur queda fuera a propósito: es la punta angosta del triángulo, lejos
    # de cualquier zona de pesca real).
    assert satellite.LAT_MIN <= 10.976111 <= satellite.LAT_MAX
    assert satellite.LON_MIN <= -74.325833 <= satellite.LON_MAX
    assert satellite.LAT_MIN <= 11.009444 <= satellite.LAT_MAX
    assert satellite.LON_MIN <= -74.681944 <= satellite.LON_MAX
