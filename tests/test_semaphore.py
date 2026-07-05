"""Tests unitarios del semáforo de condiciones."""

from app.services.semaphore import evaluate


def _weather(wind=10, precip=0):
    return {"wind_speed_kmh": wind, "precipitation_mm": precip, "temperature_c": 28}


def _satellite(sst=28):
    return {"sst_celsius": sst, "chlorophyll_mgm3": 4.5}


def test_verde_condiciones_normales():
    result = evaluate(_weather(), _satellite(), {})
    assert result.color == "green"
    assert result.safe is True


def test_rojo_viento_alto():
    result = evaluate(_weather(wind=35), _satellite(), {})
    assert result.color == "red"
    assert result.safe is False


def test_rojo_lluvia_intensa():
    result = evaluate(_weather(precip=15), _satellite(), {})
    assert result.color == "red"
    assert result.safe is False


def test_amarillo_sst_fuera_rango():
    result = evaluate(_weather(), _satellite(sst=24), {})
    assert result.color == "yellow"
    assert result.safe is True


def test_amarillo_salinidad_alta():
    result = evaluate(_weather(), _satellite(), {"salinity_psu": 35})
    assert result.color == "yellow"


def test_rojo_gust_estimado():
    # viento 33 → gust estimado 46.2 > 45: rojo
    result = evaluate(_weather(wind=33), _satellite(), {})
    assert result.color == "red"
