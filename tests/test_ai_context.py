"""Tests del contexto de IA (app/services/ai_context.py)."""

from app.services.ai_context import build_ai_context

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
