"""Tests de los avisos del tiempo (docs/AVISOS_CLIMA.md): consenso de modelos,
avisos oficiales (IDEAM, NHC), temporada + ENSO, parsers y el texto para el bot.
"""

from datetime import UTC, date, datetime, timedelta

from app.services.ai_context import avisos_para_pescador
from app.services.avisos import evaluar_avisos, necesita_desempate
from app.services.ingestion.avisos_ext import _fin_de_hora_utc, parse_enso
from app.services.ingestion.ideam_cap import parse_cap, zona_de
from app.services.temporadas import temporada

AHORA = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)  # 07:00 en Bogotá


def _serie(**valores: float | list) -> dict:
    """72 h horarias desde AHORA; cada variable constante (float) o lista explícita."""
    times = [(AHORA + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(72)]
    out = {"times": times}
    for k in ("lluvia", "viento", "rafaga", "dir", "ola"):
        v = valores.get(k, 0.0)
        out[k] = list(v) if isinstance(v, list) else [v] * 72
    return out


def _tipos(r: dict) -> dict[str, dict]:
    return {a["tipo"]: a for a in r["vigentes"]}


TODO_OK = dict(ciclones=[], sinoptico={"sistemas": []}, enso=None, ideam=[])


def test_viento_dos_de_tres_modelos_empuja():
    calma, ventoso = _serie(viento=10, rafaga=20), _serie(viento=12, rafaga=48)
    r = evaluar_avisos(AHORA, modelos={"a": ventoso, "b": ventoso, "c": calma}, oleaje=None, **TODO_OK)
    a = _tipos(r)["viento_fuerte"]
    assert a["nivel"] == "alto" and a["push"]
    assert "48 km/h" in a["mensaje"]
    assert a["fuente"].startswith("2 de 3 modelos")
    assert a["clave"] == "2026-11-02"  # día local del evento


def test_viento_un_solo_modelo_queda_posible_sin_push():
    calma, ventoso = _serie(viento=10, rafaga=20), _serie(viento=35, rafaga=40)
    r = evaluar_avisos(AHORA, modelos={"a": ventoso, "b": calma, "c": calma}, **TODO_OK)
    a = _tipos(r)["viento_fuerte"]
    assert a["nivel"] == "medio" and not a["push"]
    assert a["titulo"] == "Posible viento fuerte"
    assert necesita_desempate({"a": ventoso, "b": calma, "c": calma}, AHORA)
    assert not necesita_desempate({"a": ventoso, "b": ventoso, "c": calma}, AHORA)


def test_xweather_desempata():
    calma, ventoso = _serie(viento=10, rafaga=20), _serie(viento=35, rafaga=40)
    r = evaluar_avisos(AHORA, modelos={"a": ventoso, "b": calma, "c": calma}, xweather=ventoso, **TODO_OK)
    assert _tipos(r)["viento_fuerte"]["nivel"] == "alto"


def test_lluvia_bloque_de_6h_dentro_de_la_ventana():
    # 2 mm/h durante 6 h = 12 mm >= 10: dispara. 1.5 mm/h = 9 mm: no.
    lluvia = [0.0] * 72
    for h in range(10, 16):
        lluvia[h] = 2.0
    mojado, seco = _serie(lluvia=lluvia), _serie(lluvia=[x * 0.75 for x in lluvia])
    r = evaluar_avisos(AHORA, modelos={"a": mojado, "b": mojado, "c": seco}, **TODO_OK)
    assert _tipos(r)["lluvia_fuerte"]["nivel"] == "alto"
    r = evaluar_avisos(AHORA, modelos={"a": seco, "b": seco, "c": mojado}, **TODO_OK)
    assert _tipos(r)["lluvia_fuerte"]["nivel"] == "medio"


def test_lluvia_que_ya_cayo_no_cuenta():
    # El bloque termina en la primera hora de la ventana: 5 de sus 6 h son pasado.
    lluvia = [0.0] * 72
    lluvia[0] = 30.0
    pasado = _serie(lluvia=lluvia)
    r = evaluar_avisos(AHORA, modelos={"a": pasado, "b": pasado, "c": pasado}, **TODO_OK)
    assert "lluvia_fuerte" not in _tipos(r)


def test_fuera_de_la_ventana_no_avisa():
    rafaga = [20.0] * 72
    rafaga[50] = 60.0  # +50 h, fuera de aviso_horas=36
    tarde = _serie(rafaga=rafaga)
    r = evaluar_avisos(AHORA, modelos={"a": tarde, "b": tarde}, **TODO_OK)
    assert "viento_fuerte" not in _tipos(r)


def test_oleaje_consenso():
    alto, bajo = _serie(ola=1.8), _serie(ola=0.9)
    r = evaluar_avisos(AHORA, oleaje={"a": alto, "b": alto, "c": bajo}, **TODO_OK)
    assert _tipos(r)["oleaje"]["nivel"] == "alto"
    assert "1.8 m" in _tipos(r)["oleaje"]["mensaje"]


def test_fuentes_caidas_quedan_sin_revisar_y_el_bot_lo_dice():
    r = evaluar_avisos(AHORA)  # todo None
    assert set(r["sin_revisar"]) >= {"viento", "lluvia", "oleaje", "ciclon", "frente_frio", "enso", "ideam"}
    texto = avisos_para_pescador(r)
    assert "No pude revisar" in texto
    assert "en lo que pude revisar" in texto


def test_un_solo_modelo_disponible_no_permite_consenso():
    r = evaluar_avisos(AHORA, modelos={"a": _serie(viento=40)}, **TODO_OK)
    assert "viento" in r["sin_revisar"]
    assert _tipos(r)["viento_fuerte"]["nivel"] == "medio"


def test_ciclon_por_distancia():
    cerca = {"id": "al142026", "nombre": "Kappa", "clasificacion": "HU", "lat": 13.0, "lon": -76.0}
    medio = {**cerca, "id": "al152026", "lat": 20.0, "lon": -76.0}  # ~1000-2000 km
    lejos = {**cerca, "id": "al162026", "lat": 30.0, "lon": -50.0}
    r = evaluar_avisos(AHORA, ciclones=[cerca, medio, lejos], sinoptico={"sistemas": []}, ideam=[])
    ciclones = [a for a in r["vigentes"] if a["tipo"] == "ciclon"]
    assert [(a["clave"], a["nivel"]) for a in ciclones] == [("al142026:HU", "alto"), ("al152026:HU", "medio")]
    assert "Huracán Kappa" in ciclones[0]["mensaje"]


def test_frente_frio_solo_empuja_si_el_frente_afecta():
    r = evaluar_avisos(AHORA, sinoptico={"sistemas": ["frente_frio"], "afecta_cgsm": False}, ideam=[], ciclones=[])
    assert _tipos(r)["frente_frio"]["nivel"] == "medio"
    # Una onda tropical cerca pone afecta_cgsm=True, pero el frente sigue lejos: no empuja.
    lejos = {"sistemas": ["frente_frio", "onda_tropical"], "afecta_cgsm": True, "afectan": ["onda_tropical"]}
    assert _tipos(evaluar_avisos(AHORA, sinoptico=lejos, ideam=[], ciclones=[]))["frente_frio"]["nivel"] == "medio"
    cerca = {"sistemas": ["frente_frio"], "afecta_cgsm": True, "afectan": ["frente_frio"]}
    r = evaluar_avisos(AHORA, sinoptico=cerca, ideam=[], ciclones=[])
    a = _tipos(r)["frente_frio"]
    assert a["nivel"] == "alto" and a["clave"] == "2026-W45"


def _cap(tipo: str, severidad: str, expira: str = "2026-11-03T11:00:00-05:00", evento: str = "Tiempo lluvioso") -> dict:
    return {
        "id": "x", "evento": evento, "severidad": severidad, "tipo": tipo, "zona": "la zona",
        "inicio": "2026-11-02T06:00:00-05:00", "expira": expira,
    }


def test_ideam_severidad_por_zona():
    r = evaluar_avisos(AHORA, ideam=[
        _cap("ideam_mar", "Severe"),
        _cap("ideam_cuenca", "Severe", evento="Creciente"),
        _cap("ideam_cuenca", "Extreme"),
        _cap("ideam_mar", "Moderate", evento="Pleamar"),
        _cap("ideam_mar", "Extreme", expira="2026-11-02T06:00:00-05:00"),  # ya vencida
    ])
    ideam = [(a["tipo"], a["nivel"]) for a in r["vigentes"] if a["tipo"].startswith("ideam")]
    assert sorted(ideam) == sorted([
        ("ideam_mar", "alto"), ("ideam_cuenca", "medio"), ("ideam_cuenca", "alto"), ("ideam_mar", "medio")
    ])
    alto = next(a for a in r["vigentes"] if a["tipo"] == "ideam_mar" and a["nivel"] == "alto")
    assert "Alerta naranja del IDEAM" in alto["mensaje"] and "hasta mañana a las 11:00" in alto["mensaje"]
    assert alto["clave"] == "Tiempo lluvioso:2026-11-02"


def test_temporada_y_enso():
    el_nino = {"estado": "El Niño Advisory", "fase": "el_nino", "vigente": True, "sinopsis": ""}
    t = temporada(date(2026, 10, 31), el_nino)
    assert (t["actual"], t["proxima"], t["dias_para_proxima"]) == ("segunda temporada de lluvias", "temporada seca", 45)
    assert "menos lluvia" in t["efecto_enso"]
    # A 14 días del inicio de la seca: aviso con push y el efecto de El Niño.
    r = evaluar_avisos(datetime(2026, 12, 1, 15, tzinfo=UTC), enso=el_nino, ideam=[], ciclones=[], sinoptico={})
    a = _tipos(r)["temporada"]
    assert a["push"] and a["clave"] == "seca:2026"
    assert "mediados de diciembre" in a["mensaje"] and "El Niño" in a["mensaje"]
    assert temporada(date(2027, 1, 10), None)["proxima_clave"] == "lluvias_1:2027"


def test_parse_enso():
    raw = (
        "<b>ENSO Alert System Status:</b> El Ni&ntilde;o Advisory<br>&nbsp;<b>Synopsis:</b>&nbsp;"
        "El Ni&ntilde;o continues to strengthen. More text here."
    )
    e = parse_enso(raw)
    assert e == {"estado": "El Niño Advisory", "fase": "el_nino", "vigente": True, "terminando": False,
                 "sinopsis": "El Niño continues to strengthen."}
    assert parse_enso(raw.replace("Advisory", "Watch").replace("El Ni&ntilde;o Watch", "La Ni&ntilde;a Watch"))[
        "fase"] == "la_nina"


def test_ideam_cap_parser_y_zonas():
    xml = """<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>id1</identifier>
      <info><language>en-CO</language><event>Severe weather warning</event><severity>Severe</severity></info>
      <info><language>es-CO</language><event>Tiempo lluvioso</event><severity>Severe</severity>
      <onset>2026-11-02T11:00:00-05:00</onset><expires>2026-11-03T11:00:00-05:00</expires></info></alert>"""
    assert parse_cap(xml) == {"id": "id1", "evento": "Tiempo lluvioso", "severidad": "Severe",
                              "inicio": "2026-11-02T11:00:00-05:00", "expira": "2026-11-03T11:00:00-05:00"}
    assert zona_de("Severe weather warning for Caribbean central; Pacific southern")[0] == "ideam_mar"
    assert zona_de("Flash flood probability watch for Alto Cesar, Cga. Grande de Santa Marta")[0] == "ideam_cuenca"
    assert zona_de("Landslide warning for Magdalena (Ciénaga)") is None
    assert zona_de("Severe weather warning for Pacific northern") is None


def test_xweather_etiqueta_fin_de_hora():
    assert _fin_de_hora_utc("2026-10-31T19:00:00-05:00") == "2026-11-01T01:00"


def test_texto_para_pescador():
    r = evaluar_avisos(AHORA, modelos={"a": _serie(viento=35), "b": _serie(viento=35)}, **TODO_OK)
    corto = avisos_para_pescador(r, solo_alertas=True)
    assert corto.startswith("💨 Viento fuerte")
    completo = avisos_para_pescador(r)
    assert "Viento fuerte" in completo and "📅 Ahora estamos en la" in completo
    assert avisos_para_pescador(evaluar_avisos(AHORA, **TODO_OK), solo_alertas=True) is None
    assert avisos_para_pescador(None, solo_alertas=True) is None


def test_mismo_tipo_y_clave_sale_una_vez_y_orden_cronologico():
    dos_cuencas = [
        {**_cap("ideam_cuenca", "Extreme"), "evento": "Creciente", "zona": "el río Aracataca"},
        {**_cap("ideam_cuenca", "Extreme"), "evento": "Creciente", "zona": "la Ciénaga Grande"},
    ]
    r = evaluar_avisos(AHORA, ideam=dos_cuencas)
    assert [a["tipo"] for a in r["vigentes"]].count("ideam_cuenca") == 1
    # Viento desde 20:00Z; IDEAM desde 16:00-05:00 = 21:00Z, que como texto ordenaría antes.
    viento = _serie(viento=[35.0 if h >= 8 else 5.0 for h in range(72)])
    ideam = {**_cap("ideam_mar", "Severe"), "inicio": "2026-11-02T16:00:00-05:00"}
    r = evaluar_avisos(AHORA, modelos={"a": viento, "b": viento}, ideam=[ideam])
    assert [a["tipo"] for a in r["vigentes"]][:2] == ["viento_fuerte", "ideam_mar"]


def test_ideam_feed_que_no_es_atom_es_falla_no_lista_vacia():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.ingestion import avisos_ext, ideam_cap

    avisos_ext._cache.pop("ideam_cap", None)
    html = MagicMock(text="<html><body>Mantenimiento</body></html>")
    with patch.object(ideam_cap, "_get", new=AsyncMock(return_value=html)), patch.object(
        avisos_ext.asyncio, "sleep", new=AsyncMock()
    ):
        assert asyncio.run(ideam_cap.get_alertas_ideam()) == (None, "sin_dato")
    avisos_ext._cache.pop("ideam_cap", None)


def test_xweather_cuota_guard_y_reinicio():
    from app.core.config import settings
    from app.services.ingestion import avisos_ext

    viejo = (settings.xweather_client_id, settings.xweather_client_secret, dict(avisos_ext.xweather_cuota))
    try:
        settings.xweather_client_id, settings.xweather_client_secret = "id", "secret"
        avisos_ext.xweather_cuota.update(restante=10, reinicia="Mon, 23 Nov 2099 00:00:00 GMT")
        assert not avisos_ext.xweather_configurado()  # bajo la reserva: no gastar lo del radar
        avisos_ext.xweather_cuota.update(restante=10, reinicia="Mon, 23 Nov 2020 00:00:00 GMT")
        assert avisos_ext.xweather_configurado()  # el periodo ya reinició
        avisos_ext._leer_cuota({}, agotada=True)  # 429 sin headers
        assert not avisos_ext.xweather_configurado()
    finally:
        settings.xweather_client_id, settings.xweather_client_secret = viejo[0], viejo[1]
        avisos_ext.xweather_cuota.clear()
        avisos_ext.xweather_cuota.update(viejo[2])


def test_ideam_solo_sigue_enlaces_cap_del_propio_host():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.services.ingestion import avisos_ext, ideam_cap

    feed = """<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
      <title>Current Watches, Warnings and Advisories Issued by Ideam</title>
      <entry><id>1</id><title>Severe weather warning for Caribbean central issued x</title>
        <link rel="related" type="application/cap+xml" href="http://169.254.169.254/latest"/></entry>
    </feed>"""
    avisos_ext._cache.pop("ideam_cap", None)
    get = AsyncMock(return_value=MagicMock(text=feed))
    with patch.object(ideam_cap, "_get", new=get):
        assert asyncio.run(ideam_cap.get_alertas_ideam()) == ([], "medido")
    assert get.await_count == 1  # solo el índice; el enlace externo no se pidió
    avisos_ext._cache.pop("ideam_cap", None)


def test_enso_final_advisory_es_terminando_no_llegando():
    raw = "ENSO Alert System Status: Final El Ni&ntilde;o Advisory Synopsis: ENSO-neutral is favored. More."
    e = parse_enso(raw)
    assert e["terminando"] and not e["vigente"]
    t = temporada(date(2027, 4, 1), e)
    assert "terminando" in t["efecto_enso"] and "Podría llegar" not in t["efecto_enso"]


def test_ideam_severidad_desconocida_no_rompe_el_mensaje():
    r = evaluar_avisos(AHORA, ideam=[_cap("ideam_mar", "Unknown")])
    assert "⚠️ Alerta del IDEAM (tiempo lluvioso)" in r["vigentes"][0]["mensaje"]
