"""Tests de condicion_message._mensaje_condicion — pura: sin DB, sin red, sin mocks."""

from app.services import condicion_message
from app.services.condicion_message import _mensaje_condicion


def _estado(**overrides):
    base = {
        "semaphore": {"color": "green", "reason": "Condiciones favorables"},
        "weather": {"wind_speed_kmh": 10, "wind_gust_kmh": 15, "precipitation_mm": 0},
        "water": {"salinity_psu": 18, "ph": 7.6},
        "ipp_ranking": [
            {"zone": "Tasajera/Puebloviejo", "ipp": 90.0, "cobertura": 1.0},
            {"zone": "Nueva Venecia", "ipp": 70.0, "cobertura": 1.0},
        ],
        "edad_horas": {"weather": 0.5, "satellite": 48.0, "water": 1.0},
    }
    base.update(overrides)
    return base


def test_mensaje_menciona_rafaga_fuerte_y_mejor_zona():
    estado = _estado(weather={"wind_speed_kmh": 10, "wind_gust_kmh": 40, "precipitation_mm": 0})
    msg = _mensaje_condicion(estado)
    assert "ráfagas fuertes" in msg
    assert "Tasajera/Puebloviejo" in msg


def test_mensaje_avisa_si_el_dato_esta_viejo():
    estado = _estado(edad_horas={"weather": 5.0, "satellite": 48.0, "water": 1.0})
    msg = _mensaje_condicion(estado)
    assert "hace unas horas" in msg


def test_mensaje_no_avisa_si_el_dato_es_reciente():
    estado = _estado(edad_horas={"weather": 0.5, "satellite": 48.0, "water": 1.0})
    msg = _mensaje_condicion(estado)
    assert "hace unas horas" not in msg


def test_mensaje_es_corto():
    estado = _estado(edad_horas={"weather": 5.0, "satellite": 48.0, "water": 1.0})
    msg = _mensaje_condicion(estado)
    oraciones = [o for o in msg.split(".") if o.strip()]
    assert len(oraciones) <= 4


def test_mensaje_sin_datos_no_truena():
    estado = {
        "semaphore": {"color": None, "reason": "Sin datos recientes"},
        "weather": {"wind_speed_kmh": None, "wind_gust_kmh": None, "precipitation_mm": None},
        "ipp_ranking": [],
        "edad_horas": {"weather": None, "satellite": None, "water": None},
    }
    msg = _mensaje_condicion(estado)
    assert "Sin datos recientes" in msg


def test_mensaje_rojo_recomienda_no_salir():
    estado = _estado(semaphore={"color": "red", "reason": "Viento o lluvia peligrosa"})
    msg = _mensaje_condicion(estado)
    assert "espera" in msg.lower()


def test_mensaje_avisa_si_no_hay_lectura_de_agua():
    # El bot degrada en vez de mentir: sin sensores de agua, el IPP se calculó
    # solo con datos satelitales — se dice explícitamente en vez de recomendar
    # una zona en silencio como si estuviera respaldada por lecturas reales.
    estado = _estado(water={})
    msg = _mensaje_condicion(estado)
    assert "lectura de los sensores del agua" in msg


def test_mensaje_oculta_zona_con_cobertura_baja():
    estado = _estado(
        ipp_ranking=[{"zone": "Tasajera/Puebloviejo", "ipp": 100.0, "cobertura": 0.31}]
    )
    msg = _mensaje_condicion(estado)
    assert "Tasajera/Puebloviejo" not in msg
    assert "no tengo suficientes lecturas" in msg.lower()


def test_mensaje_menciona_tendencia_de_salinidad():
    estado = _estado(
        tendencias={"variables": {"salinity_psu": {"direccion": "bajando"}}, "lluvia_72h_mm": 40.0}
    )
    msg = _mensaje_condicion(estado)
    assert "más dulce" in msg


def test_mensaje_tendencia_estable_no_se_menciona():
    estado = _estado(
        tendencias={"variables": {"salinity_psu": {"direccion": "estable"}}, "lluvia_72h_mm": 0.0}
    )
    msg = _mensaje_condicion(estado)
    assert "más dulce" not in msg and "más salada" not in msg


def test_mensaje_anoxia_apagada_por_defecto():
    # _ANOXIA_EN_BOT es False hasta que el equipo científico valide los umbrales
    # contra un evento real — un riesgo "alto" no debe llegar al pescador todavía.
    estado = _estado(senales={"anoxia": {"nivel": "alto"}})
    msg = _mensaje_condicion(estado)
    assert "peces muertos" not in msg


def test_mensaje_anoxia_si_se_habilita(monkeypatch):
    # Prueba de que el mecanismo funciona correctamente una vez encendido —
    # no se activa por sí solo, requiere este flag en True.
    monkeypatch.setattr(condicion_message, "_ANOXIA_EN_BOT", True)
    estado = _estado(senales={"anoxia": {"nivel": "alto"}})
    msg = _mensaje_condicion(estado)
    assert "peces muertos" in msg


def test_mensaje_dato_viejo_desplaza_a_tendencia():
    # Un solo slot para "viejo" o "tendencia" — con ambos disponibles, gana la
    # transparencia sobre el dato (más urgente) y el mensaje se queda en 4.
    estado = _estado(
        edad_horas={"weather": 5.0, "satellite": 48.0, "water": 1.0},
        tendencias={"variables": {"salinity_psu": {"direccion": "subiendo"}}, "lluvia_72h_mm": 0.0},
    )
    msg = _mensaje_condicion(estado)
    assert "hace unas horas" in msg
    assert "más salada" not in msg
    oraciones = [o for o in msg.split(".") if o.strip()]
    assert len(oraciones) <= 4
