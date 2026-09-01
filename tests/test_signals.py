"""Tests de app/services/signals.py — señales compuestas, siempre marcadas como
estimación (no medición)."""

from app.services.signals import anoxia_risk, pulso_agua_dulce, tormenta_aproximandose, vendaval_risk


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
    result = vendaval_risk({"puntos": [], "origen": "sin_dato"}, 62.0)
    assert result == {"nivel": None, "estimacion": True}


def test_vendaval_condiciones_tranquilas_da_bajo():
    # CGSM el 29-ago-2026 real (docs/ALERTAS_VENDAVAL.md): CIN alto (capa marina
    # con tapa), poca sequedad sub-nube, ráfaga lejos del umbral — 0/6 días de
    # backtest dispararon con este perfil.
    forecast = {
        "puntos": [
            {
                "timestamp": "2026-08-29T14:00",
                "wind_gust_kmh": 10.0,
                "cape": 500.0,
                "convective_inhibition": 200.0,
                "temperature_2m": 30.0,
                "dew_point_2m": 25.0,
            }
        ],
        "origen": "medido",
    }
    result = vendaval_risk(forecast, 62.0)
    assert result["nivel"] == "bajo"
    assert result["estimacion"] is True


def test_vendaval_condiciones_extremas_da_alto():
    # Chibolo el 29-ago-2026 real: CAPE 3700, CIN 0, T-Td 19.3°C — el día que sí
    # tumbó árboles y casas (docs/ALERTAS_VENDAVAL.md, Parte 1).
    forecast = {
        "puntos": [
            {
                "timestamp": "2026-08-29T14:00",
                "wind_gust_kmh": 20.0,
                "cape": 3700.0,
                "convective_inhibition": 0.0,
                "temperature_2m": 33.0,
                "dew_point_2m": 13.7,
            }
        ],
        "origen": "medido",
    }
    result = vendaval_risk(forecast, 62.0)
    assert result["nivel"] == "alto"


def test_vendaval_sin_ningun_factor_no_opina():
    forecast = {"puntos": [{"timestamp": "2026-08-29T14:00"}], "origen": "medido"}
    result = vendaval_risk(forecast, 62.0)
    assert result == {"nivel": None, "estimacion": True}


_CGSM = (10.859056, -74.460611)


def _destello(lat, lon, timestamp):
    return {"lat": lat, "lon": lon, "timestamp": timestamp}


def test_tormenta_sin_instantanea_previa_no_opina():
    actual = {"flashes": [_destello(0.0, 1.0, "2026-08-29T18:00:00+00:00")] * 5}
    assert tormenta_aproximandose(None, actual, *_CGSM, 90) is None


def test_tormenta_sin_suficientes_destellos_no_opina():
    anterior = {"flashes": [_destello(0.0, 1.0, "2026-08-29T18:00:00+00:00")] * 2}
    actual = {"flashes": [_destello(0.0, 0.5, "2026-08-29T18:10:00+00:00")] * 2}
    assert tormenta_aproximandose(anterior, actual, *_CGSM, 90) is None


def test_tormenta_que_se_aleja_no_opina():
    anterior = {"flashes": [_destello(*_CGSM, "2026-08-29T18:00:00+00:00")] * 5}
    # 1 grado de longitud más lejos del centro que la instantánea anterior
    lejos = (_CGSM[0], _CGSM[1] + 1.0)
    actual = {"flashes": [_destello(*lejos, "2026-08-29T18:10:00+00:00")] * 5}
    assert tormenta_aproximandose(anterior, actual, *_CGSM, 90) is None


def test_tormenta_acercandose_con_eta_dentro_del_maximo():
    lejos = (_CGSM[0], _CGSM[1] + 1.0)
    medio = (_CGSM[0], _CGSM[1] + 0.5)
    anterior = {"flashes": [_destello(*lejos, "2026-08-29T18:00:00+00:00")] * 5}
    actual = {"flashes": [_destello(*medio, "2026-08-29T18:10:00+00:00")] * 5}

    result = tormenta_aproximandose(anterior, actual, *_CGSM, 90)

    assert result is not None
    assert result["eta_min"] > 0
    assert result["distancia_km"] > 0
    assert result["n_descargas"] == 5
    assert result["rumbo"] in {
        "norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste",
    }


def test_tormenta_acercandose_muy_lento_supera_eta_maximo():
    lejos = (_CGSM[0], _CGSM[1] + 1.0)
    apenas_mas_cerca = (_CGSM[0], _CGSM[1] + 0.999)
    anterior = {"flashes": [_destello(*lejos, "2026-08-29T18:00:00+00:00")] * 5}
    actual = {"flashes": [_destello(*apenas_mas_cerca, "2026-08-29T18:10:00+00:00")] * 5}

    assert tormenta_aproximandose(anterior, actual, *_CGSM, 90) is None
