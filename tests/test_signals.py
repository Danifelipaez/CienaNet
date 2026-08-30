"""Tests de app/services/signals.py — señales compuestas, siempre marcadas como
estimación (no medición)."""

from app.services.signals import anoxia_risk, pulso_agua_dulce, vendaval_risk


def test_anoxia_alto_con_floracion_calor_y_calma():
    result = anoxia_risk({"chlorophyll_mgm3": 70, "sst_celsius": 31}, {"wind_speed_kmh": 2}, {})
    assert result["nivel"] == "alto"
    assert result["estimacion"] is True


def test_anoxia_promedia_solo_factores_con_dato():
    # Sin nivel de agua en `water` — solo 3 factores contribuyen al promedio.
    result = anoxia_risk({"chlorophyll_mgm3": 70, "sst_celsius": 31}, {"wind_speed_kmh": 2}, {})
    assert result["n_factores"] == 3


def test_anoxia_menos_de_dos_factores_no_opina():
    result = anoxia_risk({"chlorophyll_mgm3": 70}, {}, {})
    assert result["nivel"] is None
    assert result["n_factores"] == 1


def test_anoxia_bajo_con_condiciones_normales():
    result = anoxia_risk(
        {"chlorophyll_mgm3": 5, "sst_celsius": 27},
        {"wind_speed_kmh": 15},
        {"water_level_cm": 60},
    )
    assert result["nivel"] == "bajo"


def test_anoxia_nombra_los_factores_activos():
    result = anoxia_risk({"chlorophyll_mgm3": 70, "sst_celsius": 31}, {"wind_speed_kmh": 2}, {})
    assert "clorofila muy alta" in result["factores"]
    assert "viento flojo" in result["factores"]


def test_pulso_requiere_umbral():
    assert pulso_agua_dulce(10.0, 15.0) is None
    assert pulso_agua_dulce(None, 15.0) is None


def test_pulso_sobre_umbral_es_direccional_no_cuantificado():
    result = pulso_agua_dulce(40.0, 15.0)
    assert result is not None
    assert result["estimacion"] is True
    assert "psu" not in result["mensaje"].lower()  # direccional, sin coeficiente mm→PSU inventado


def test_vendaval_sin_dato_no_opina():
    assert vendaval_risk({"puntos": [], "origen": "sin_dato"}, 62.0) is None


def test_vendaval_bajo_umbral_no_alerta():
    forecast = {"puntos": [{"timestamp": "2026-08-30T10:00", "wind_gust_kmh": 30.0}], "origen": "medido"}
    assert vendaval_risk(forecast, 62.0) is None


def test_vendaval_sobre_umbral_devuelve_primera_hora():
    forecast = {
        "puntos": [
            {"timestamp": "2026-08-30T10:00", "wind_gust_kmh": 40.0},
            {"timestamp": "2026-08-30T14:00", "wind_gust_kmh": 65.0},
            {"timestamp": "2026-08-30T15:00", "wind_gust_kmh": 80.0},
        ],
        "origen": "medido",
    }
    result = vendaval_risk(forecast, 62.0)
    assert result["timestamp"] == "2026-08-30T14:00"
    assert result["wind_gust_kmh"] == 65.0
    assert result["umbral_kmh"] == 62.0
