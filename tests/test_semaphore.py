"""Tests unitarios del semáforo de condiciones."""

from app.services.semaphore import evaluate


def _weather(wind=10, precip=0, gust=None):
    return {
        "wind_speed_kmh": wind,
        "wind_gust_kmh": gust,
        "precipitation_mm": precip,
        "temperature_c": 28,
    }


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


def test_rojo_viento_sostenido():
    result = evaluate(_weather(wind=33), _satellite(), {})
    assert result.color == "red"


def test_rojo_por_rafaga_real():
    # viento medio seguro (20) pero ráfaga real de chubasco (50) → rojo.
    # Antes, con gust=wind*1.4, la ráfaga "estimada" para wind=20 era solo 28
    # y este caso salía verde pese al riesgo real de zozobra para una canoa.
    result = evaluate(_weather(wind=20, gust=50), _satellite(), {})
    assert result.color == "red"


def test_sin_rafaga_no_se_inventa():
    result = evaluate(_weather(wind=20), _satellite(), {})
    assert result.color == "green"


def test_tolera_valores_none():
    # sst_celsius/salinity_psu presentes pero en None (dato ausente persistido
    # explícitamente, ver points_service.py) — no debe lanzar TypeError.
    satellite_none = {"sst_celsius": None, "chlorophyll_mgm3": None}
    water_none = {"salinity_psu": None, "ph": None}
    result = evaluate(_weather(), satellite_none, water_none)
    assert result.color in {"green", "yellow", "red"}


def test_amarillo_sin_viento_ni_lluvia_no_dice_seguro():
    # Desconocido ≠ seguro: sin ni viento ni lluvia, el check de rojo nunca corrió
    # — antes num() rellenaba con un default y esto caía en verde por accidente.
    weather_sin_datos = {
        "wind_speed_kmh": None,
        "wind_gust_kmh": None,
        "precipitation_mm": None,
        "temperature_c": None,
    }
    result = evaluate(weather_sin_datos, _satellite(), {})
    assert result.color == "yellow"
    assert result.safe is False
    assert "viento" in result.datos_faltantes and "lluvia" in result.datos_faltantes


def test_con_solo_viento_conocido_si_evalua():
    # Dato parcial (viento sí, lluvia no) sigue siendo suficiente para el check
    # de rojo — el "ambos None" de arriba es la excepción, no la regla.
    weather_parcial = {"wind_speed_kmh": 35, "wind_gust_kmh": None, "precipitation_mm": None}
    result = evaluate(weather_parcial, _satellite(), {})
    assert result.color == "red"
