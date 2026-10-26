"""Tests de app/services/signals.py — señales compuestas, siempre marcadas como
estimación (no medición)."""

from datetime import UTC, datetime, timedelta

from app.services.rain_signals import contar_rayos_cerca, lluvia_nowcast, lluvia_outlook
from app.services.signals import (
    anoxia_risk,
    pulso_agua_dulce,
    tormenta_aproximandose,
    vendaval_risk,
)


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


# --- Lluvia: nowcast (RRQPE) ---

_AHORA = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)


def _feat(caja=0.0, anillo=0.0, nan=0.0, edad_min=10):
    return {
        "scan": _AHORA - timedelta(minutes=edad_min),
        "frac_caja_1mm": caja,
        "frac_anillo_5mm": anillo,
        "frac_nan": nan,
    }


def test_lluvia_caja_con_lluvia_es_lloviendo_y_no_inminente():
    # Falso positivo a evitar: ya llueve encima, aunque el anillo también esté fuerte.
    out = lluvia_nowcast(_feat(caja=0.30, anillo=0.20), _AHORA)
    assert out["estado"] == "lloviendo"
    assert "eta_rango_min" not in out


def test_lluvia_anillo_fuerte_con_caja_seca_es_inminente():
    out = lluvia_nowcast(_feat(caja=0.0, anillo=0.04), _AHORA)
    assert out["estado"] == "inminente"
    assert out["eta_rango_min"] == [30, 60]
    assert out["estimacion"] is True


def test_lluvia_anillo_bajo_el_umbral_no_es_inminente():
    # Falso positivo: 1.9 % del anillo con lluvia fuerte es ruido, no un frente entrando.
    assert lluvia_nowcast(_feat(anillo=0.019), _AHORA)["estado"] == "sin_lluvia"


def test_lluvia_umbrales_son_inclusivos():
    assert lluvia_nowcast(_feat(anillo=0.02), _AHORA)["estado"] == "inminente"
    assert lluvia_nowcast(_feat(caja=0.05, anillo=0.02), _AHORA)["estado"] == "lloviendo"
    # 4.9 % de la caja no cuenta como "lloviendo": una llovizna dispersa no apaga el aviso.
    assert lluvia_nowcast(_feat(caja=0.049, anillo=0.03), _AHORA)["estado"] == "inminente"


def test_lluvia_sin_features_es_sin_dato():
    assert lluvia_nowcast(None, _AHORA)["estado"] == "sin_dato"


def test_lluvia_scan_viejo_es_sin_dato_aunque_el_anillo_este_fuerte():
    # Falso positivo por dato rancio: un scan de hace 30 min no sirve para un nowcast de 30 min.
    assert lluvia_nowcast(_feat(anillo=0.10, edad_min=30), _AHORA)["estado"] == "sin_dato"
    assert lluvia_nowcast(_feat(anillo=0.10, edad_min=25), _AHORA)["estado"] == "inminente"


def test_lluvia_muchos_nan_es_sin_dato_aunque_el_anillo_este_fuerte():
    assert lluvia_nowcast(_feat(anillo=0.10, nan=0.11), _AHORA)["estado"] == "sin_dato"
    assert lluvia_nowcast(_feat(anillo=0.10, nan=0.10), _AHORA)["estado"] == "inminente"


def test_lluvia_features_con_fracciones_none_es_sin_dato():
    # Todos los píxeles inválidos: _frac devuelve None, no se puede decir "sin_lluvia".
    assert lluvia_nowcast({**_feat(), "frac_anillo_5mm": None}, _AHORA)["estado"] == "sin_dato"


def test_lluvia_tormenta_electrica_por_rayos_no_cambia_el_estado():
    assert lluvia_nowcast(_feat(anillo=0.04), _AHORA, rayos_100km=3)["tormenta_electrica"] is True
    out = lluvia_nowcast(_feat(anillo=0.04), _AHORA, rayos_100km=2)
    assert out["tormenta_electrica"] is False and out["estado"] == "inminente"
    # Falso negativo a evitar: rayos sin lluvia en anillo no inventan "inminente".
    assert lluvia_nowcast(_feat(), _AHORA, rayos_100km=50)["estado"] == "sin_lluvia"
    # Los rayos se siguen reportando aunque el satélite falle.
    assert lluvia_nowcast(None, _AHORA, rayos_100km=5)["tormenta_electrica"] is True


def test_contar_rayos_cerca_respeta_el_radio():
    cerca = {"lat": _CGSM[0], "lon": _CGSM[1] + 0.5}  # ~54 km
    lejos = {"lat": _CGSM[0], "lon": _CGSM[1] + 1.5}  # ~160 km
    assert contar_rayos_cerca([cerca, cerca, lejos], *_CGSM) == 2


# --- Lluvia: outlook (GEFS) ---


def _ens(por_hora_mm: list[float], n_miembros: int = 31, miembros_con_lluvia: int = 0):
    """Ensamble de 72 h desde 2026-10-24T00:00: los primeros `miembros_con_lluvia`
    miembros siguen `por_hora_mm` (mm/h a partir de la etiqueta 01:00); el resto, 0."""
    horas = [(datetime(2026, 10, 24) + timedelta(hours=h)).isoformat(timespec="minutes") for h in range(72)]
    llueve = [0.0] + por_hora_mm + [0.0] * (71 - len(por_hora_mm))
    return {
        "times": horas,
        "miembros": [llueve if k < miembros_con_lluvia else [0.0] * 72 for k in range(n_miembros)],
        "origen": "medido",
    }


_T0 = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)


def test_outlook_0_de_31_miembros_es_bajo():
    out = lluvia_outlook(_ens([2.0] * 24, miembros_con_lluvia=0), _T0)
    assert out["nivel"] == "bajo" and out["prob_6h"] == 0.0 and out["prob_24h"] == 0.0
    assert out["n_miembros"] == 31 and out["estimacion"] is True


def test_outlook_31_de_31_miembros_es_alto():
    out = lluvia_outlook(_ens([1.0] * 24, miembros_con_lluvia=31), _T0)  # 6 mm por bloque
    assert out["nivel"] == "alto" and out["prob_6h"] == 1.0 and out["prob_24h"] == 1.0


def test_outlook_lluvia_debil_no_cuenta():
    # 31/31 miembros con 4 mm en 6 h (< 5 mm): falso positivo si se contara.
    out = lluvia_outlook(_ens([4 / 6] * 24, miembros_con_lluvia=31), _T0)
    assert out["nivel"] == "bajo"


def test_outlook_niveles_en_los_cortes():
    # 9/31 = 0.29 bajo ; 10/31 = 0.32 medio ; 16/31 = 0.52 alto
    assert lluvia_outlook(_ens([1.0] * 6, miembros_con_lluvia=9), _T0)["nivel"] == "bajo"
    assert lluvia_outlook(_ens([1.0] * 6, miembros_con_lluvia=10), _T0)["nivel"] == "medio"
    assert lluvia_outlook(_ens([1.0] * 6, miembros_con_lluvia=16), _T0)["nivel"] == "alto"


def test_outlook_distingue_6h_de_24h():
    # Lluvia solo entre +12 h y +18 h: prob_6h = 0, prob_24h = 1.
    por_hora = [0.0] * 12 + [1.0] * 6
    out = lluvia_outlook(_ens(por_hora, miembros_con_lluvia=31), _T0)
    assert out["prob_6h"] == 0.0 and out["prob_24h"] == 1.0 and out["nivel"] == "alto"


def test_outlook_fuera_de_24h_no_cuenta():
    out = lluvia_outlook(_ens([0.0] * 24 + [2.0] * 6, miembros_con_lluvia=31), _T0)
    assert out["prob_6h"] == 0.0 and out["prob_24h"] == 0.0


def test_outlook_un_bloque_parcial_no_opina():
    ens = _ens([1.0] * 24, miembros_con_lluvia=31)
    # Pronóstico que termina 3 h después de "ahora": no alcanza para un bloque de 6 h.
    corto = {**ens, "times": ens["times"][:4], "miembros": [m[:4] for m in ens["miembros"]]}
    assert lluvia_outlook(corto, _T0)["nivel"] is None


def test_outlook_sin_dato_no_opina():
    assert lluvia_outlook({"times": [], "miembros": [], "origen": "sin_dato"}, _T0) == {
        "nivel": None,
        "estimacion": True,
    }
