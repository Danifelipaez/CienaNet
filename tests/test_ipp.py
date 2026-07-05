"""Tests unitarios del Índice de Potencial Pesquero."""

from app.services.ipp import ZONES, calculate_ipp, rank_zones


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
