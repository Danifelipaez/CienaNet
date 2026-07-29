"""Tests unitarios del Índice de Potencial Pesquero."""

from app.services.ipp import (
    ZONES,
    _score_chlorophyll,
    _score_salinity,
    _zone_satellite,
    calculate_ipp,
    ipp_cobertura,
    rank_zones,
)


def _water_opt():
    return {"salinity_psu": 15, "ph": 7.8}


def _satellite_opt():
    return {"sst_celsius": 28, "chlorophyll_mgm3": 5}


def test_rank_zones_retorna_seis():
    ranking = rank_zones(_water_opt(), _satellite_opt())
    assert len(ranking) == 6


def test_rank_zones_ordenado_desc():
    ranking = rank_zones(_water_opt(), _satellite_opt())
    ipps = [z["ipp"] for z in ranking]
    assert ipps == sorted(ipps, reverse=True)


def test_rank_zones_tiene_campos():
    ranking = rank_zones(_water_opt(), _satellite_opt())
    assert all("zone" in z and "ipp" in z for z in ranking)


def test_ipp_optimo_alto():
    # Tasajera/Puebloviejo con salinidad 10 (dentro de rango 3-15)
    zone = next(z for z in ZONES if z["name"] == "Tasajera/Puebloviejo")
    score = calculate_ipp(_water_opt(), _satellite_opt(), zone)
    assert score > 70


def test_ipp_salinidad_fuera_rango_baja_score():
    zone = ZONES[0]  # Boca de la Barra: sal_min=20, sal_max=36
    water_low_sal = {"salinity_psu": 5}  # salinity=5, fuera de 20-36
    score = calculate_ipp(water_low_sal, _satellite_opt(), zone)
    # salinity 0 puntos (0.31 peso) baja el score
    assert score < 80


def test_ipp_rango_0_100():
    for zone in ZONES:
        score = calculate_ipp(_water_opt(), _satellite_opt(), zone)
        assert 0 <= score <= 100


def test_ipp_tolera_valores_none():
    # water/satellite con clave presente pero en None (dato ausente persistido
    # explícitamente, ver points_service.py) — no debe lanzar TypeError, y la
    # cobertura debe reflejar que no hubo NINGÚN dato real (no rellenar con
    # defaults inventados: sin señal, el IPP es 0, no un número que parezca normal).
    water_none = {"salinity_psu": None, "ph": None}
    satellite_none = {"sst_celsius": None, "chlorophyll_mgm3": None}
    assert ipp_cobertura(water_none, satellite_none) == 0
    for zone in ZONES:
        score = calculate_ipp(water_none, satellite_none, zone)
        assert score == 0.0


def test_ipp_renormaliza_pesos():
    # Solo salinidad tiene dato real: cobertura == su propio peso (0.31), y con
    # una sola señal presente el IPP renormalizado coincide con su score crudo
    # (no se diluye mezclándolo con defaults inventados para sst/clorofila/ph).
    water = {"salinity_psu": 15}  # Tasajera/Puebloviejo: sal_min=3, sal_max=15 → óptimo
    satellite = {}
    zone = next(z for z in ZONES if z["name"] == "Tasajera/Puebloviejo")
    assert ipp_cobertura(water, satellite) == 0.31
    assert calculate_ipp(water, satellite, zone) == 100.0


def test_rank_zones_incluye_cobertura():
    ranking = rank_zones({"salinity_psu": 15, "ph": 7.8}, {"sst_celsius": 28, "chlorophyll_mgm3": 5})
    assert all(z["cobertura"] == 1.0 for z in ranking)


def test_rank_zones_discrimina_mas_de_dos_niveles():
    # Antes: chl*10 saturaba y sst/ph eran escalón → el IPP solo podía valer
    # 100.0 (en rango) o 69.0 (fuera) para las 6 zonas. Con curvas graduadas,
    # la salinidad sola ya reparte el ranking en más de dos niveles.
    water = {"salinity_psu": 18, "ph": 7.6}
    satellite = {"sst_celsius": 28.5, "chlorophyll_mgm3": 25}
    assert len({z["ipp"] for z in rank_zones(water, satellite)}) >= 4


def test_score_clorofila_penaliza_floracion():
    assert _score_chlorophyll(60) < _score_chlorophyll(20)


def test_score_salinidad_decae_gradual():
    s1, s5, s10 = (_score_salinity(v, 3, 15) for v in (16, 20, 25))
    assert 100 > s1 > s5 > 0 and s10 == 0


def test_zone_satellite_cae_al_box_si_falta_la_zona():
    satellite = {
        "sst_celsius": 28,
        "chlorophyll_mgm3": 5,
        "por_zona": {"Tasajera/Puebloviejo": {"chlorophyll_mgm3": 60}},
    }
    resultado = _zone_satellite(satellite, "Suroccidente")  # sin override propio
    assert resultado["chlorophyll_mgm3"] == 5  # cae al box
    assert resultado["sst_celsius"] == 28


def test_zone_satellite_usa_el_override_cuando_existe():
    satellite = {
        "sst_celsius": 28,
        "chlorophyll_mgm3": 5,
        "por_zona": {"Tasajera/Puebloviejo": {"chlorophyll_mgm3": 60}},
    }
    resultado = _zone_satellite(satellite, "Tasajera/Puebloviejo")
    assert resultado["chlorophyll_mgm3"] == 60
    assert resultado["sst_celsius"] == 28  # sst no tiene override, sigue siendo el del box


def test_rank_zones_usa_clorofila_por_zona():
    water = {"salinity_psu": 15, "ph": 7.8}
    satellite_sin_zona = {"sst_celsius": 28, "chlorophyll_mgm3": 5}
    satellite_con_zona = {
        **satellite_sin_zona,
        "por_zona": {"Tasajera/Puebloviejo": {"chlorophyll_mgm3": 60}},
    }

    def _ipp_de(ranking, zona):
        return next(z for z in ranking if z["zone"] == zona)["ipp"]

    # La zona con override cambia de IPP...
    assert _ipp_de(rank_zones(water, satellite_con_zona), "Tasajera/Puebloviejo") != _ipp_de(
        rank_zones(water, satellite_sin_zona), "Tasajera/Puebloviejo"
    )
    # ...las demás, que no tienen override propio, siguen usando el box sin cambio.
    assert _ipp_de(rank_zones(water, satellite_con_zona), "Nueva Venecia") == _ipp_de(
        rank_zones(water, satellite_sin_zona), "Nueva Venecia"
    )
