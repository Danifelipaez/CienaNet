"""Tests de app/services/ingestion/alerts_ext.py — limpieza de HTML y filtro
de contenido (boletines de rutina "sin actividad" no deben contar como alerta).
Mockea feedparser — sin red.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ingestion import alerts_ext


def _fake_client():
    resp = MagicMock()
    resp.text = "<rss></rss>"  # contenido real irrelevante: feedparser.parse va mockeado
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


def _entry(title, summary, link="https://www.nhc.noaa.gov/"):
    return SimpleNamespace(title=title, summary=summary, link=link)


def setup_function():
    alerts_ext._cache["data"] = None
    alerts_ext._cache["ts"] = 0.0


def _run_with_entries(entries):
    factory = _fake_client()
    fake_feed = MagicMock(entries=entries)
    with (
        patch.object(alerts_ext.httpx, "AsyncClient", factory),
        patch.object(alerts_ext.feedparser, "parse", return_value=fake_feed),
    ):
        return asyncio.run(alerts_ext.get_cyclone_alerts())


def test_limpia_br_y_tags_de_un_alerta_real():
    entries = [
        _entry(
            "Tropical Storm Example Advisory Number 5",
            "Storm intensifying.<br />Max winds 60 mph.<br/>Moving NW at 10 mph.",
        )
    ]

    out = _run_with_entries(entries)

    assert len(out) == 1
    assert "<br" not in out[0]["summary"]
    assert out[0]["summary"] == "Storm intensifying.\nMax winds 60 mph.\nMoving NW at 10 mph."


def test_descarta_boletin_de_outlook_sin_actividad():
    entries = [
        _entry(
            "Atlantic Tropical Weather Outlook",
            "Tropical cyclone formation is not expected during the next 7 days.",
        )
    ]

    out = _run_with_entries(entries)

    assert out == []


def test_descarta_boletin_sin_ciclones_activos():
    entries = [_entry("Tropical Cyclones", "There are no tropical cyclones at this time.")]

    out = _run_with_entries(entries)

    assert out == []


def test_mezcla_filtra_solo_lo_sin_actividad():
    entries = [
        _entry("Atlantic Tropical Weather Outlook", "Tropical cyclone formation is not expected."),
        _entry("Hurricane Example Advisory Number 1", "Hurricane Example is a category 2 storm."),
    ]

    out = _run_with_entries(entries)

    assert len(out) == 1
    assert out[0]["title"] == "Hurricane Example Advisory Number 1"


# --- Sistemas sinópticos (NHC TWD) ---

_TWD_ENCABEZADO = """000
AXNT20 KNHC 261205
TWDAT

Tropical Weather Discussion
NWS National Hurricane Center Miami FL
805 AM EDT Mon Oct 26 2026

Tropical Weather Discussion for North America, Central America
Gulf of Mexico, Caribbean Sea, northern sections of South
America, and Atlantic Ocean to the African coast from the
Equator to 31N.

...SPECIAL FEATURES...

"""

_TWD_RUTINA_CARIBE = """...CARIBBEAN SEA...

A weak pressure gradient between the Atlantic ridge and the Colombian
low is supporting moderate to fresh trade winds across the central
Caribbean, with fresh to strong winds off Colombia. Seas are 4 to 6 ft.
Little change is expected through the week.
"""

_TWD_GOLFO_CON_FRENTE = """...GULF OF MEXICO...

A cold front extends from the Florida Panhandle to the Bay of Campeche.
Scattered showers and thunderstorms are ahead of the front over the
northern Gulf. Fresh to strong northerly winds follow the front.

$$
Forecaster Example
"""


def _parse(*secciones: str) -> dict:
    return alerts_ext.parse_twd(
        _TWD_ENCABEZADO + "\n".join(secciones), ahora=datetime(2026, 10, 26, 13, tzinfo=UTC)
    )


def test_twd_de_rutina_sin_sistemas_da_lista_vacia():
    out = _parse(_TWD_RUTINA_CARIBE, _TWD_GOLFO_CON_FRENTE)
    assert out["sistemas"] == []
    assert out["afecta_cgsm"] is False
    assert out["extracto"] is None
    assert out["emitido"] == "2026-10-26T12:05:00+00:00"


def test_twd_frente_frio_lejano_en_el_golfo_no_afecta_la_cgsm():
    # Falso positivo a evitar: el frente del Golfo de México no es sección del Caribe.
    out = _parse(_TWD_GOLFO_CON_FRENTE)
    assert out["sistemas"] == [] and out["afecta_cgsm"] is False


def test_twd_frente_frio_en_el_caribe_noroccidental_es_sistema_pero_no_afecta():
    caribe = """...CARIBBEAN SEA...

A cold front extends from western Cuba to the Yucatan Channel. Fresh to
strong NE winds are noted behind the front over the NW Caribbean.
"""
    out = _parse(caribe)
    assert out["sistemas"] == ["frente_frio"]
    assert out["afecta_cgsm"] is False
    assert "Yucatan Channel" in out["extracto"]


def test_twd_onda_tropical_en_74w_afecta_la_cgsm():
    ondas = """...TROPICAL WAVES...

A tropical wave is along 74W from 05N to 14N, moving west at 15 kt.
Scattered moderate convection is noted from 09N to 12N between 72W and 76W.
"""
    out = _parse(ondas)
    assert out["sistemas"] == ["onda_tropical"]
    assert out["afecta_cgsm"] is True
    assert out["extracto"].startswith("A tropical wave is along 74W")


def test_twd_onda_tropical_lejos_no_afecta_o_ni_siquiera_cuenta():
    # En 60W (lejos, ya salió del Caribe) no es del Caribe sudoccidental: ni sistema.
    lejos = "...TROPICAL WAVES...\n\nA tropical wave is along 60W from 05N to 15N, moving west at 15 kt.\n"
    assert _parse(lejos)["sistemas"] == []
    # En 71W entra a la ventana 70W-80W pero está lejos de la CGSM (74.5W): sistema, no afecta.
    cerca = "...TROPICAL WAVES...\n\nA tropical wave is along 71W from 05N to 15N, moving west at 15 kt.\n"
    out = _parse(cerca)
    assert out["sistemas"] == ["onda_tropical"] and out["afecta_cgsm"] is False


def test_twd_onda_con_mencion_de_colombia_afecta():
    ondas = """...TROPICAL WAVES...

A tropical wave is moving across northern Colombia and the SW Caribbean
with numerous showers.
"""
    out = _parse(ondas)
    assert out["sistemas"] == ["onda_tropical"] and out["afecta_cgsm"] is True


def test_twd_vaguada_monzonica_sin_conveccion_no_afecta():
    # La vaguada monzónica de Colombia/Panamá sale en el TWD casi a diario: sin
    # convección asociada es sistema (contexto) pero no debe marcar "afecta".
    monzon = """...MONSOON TROUGH...

The monsoon trough extends from the coast of Colombia near 09N77W to
the Pacific. Winds are light across the region.
"""
    out = _parse(monzon)
    assert out["sistemas"] == ["vaguada"] and out["afecta_cgsm"] is False


def test_twd_vaguada_con_conveccion_en_colombia_afecta():
    caribe = """...CARIBBEAN SEA...

A surface trough extends from the Gulf of Venezuela to northern Colombia.
Scattered moderate to isolated strong convection is noted over the south-central
Caribbean, including off the coast of Colombia.
"""
    out = _parse(caribe)
    assert out["sistemas"] == ["vaguada"] and out["afecta_cgsm"] is True


def test_twd_baja_presion_en_el_caribe_sudoccidental_afecta():
    caribe = """...CARIBBEAN SEA...

Low pressure of 1008 mb is centered over the SW Caribbean near 11N80W.
Numerous showers and thunderstorms are noted near the low.
"""
    out = _parse(caribe)
    assert out["sistemas"] == ["baja_presion"] and out["afecta_cgsm"] is True


def test_twd_extracto_se_corta_a_300_caracteres():
    largo = "...TROPICAL WAVES...\n\nA tropical wave is along 74W " + "and far away " * 60 + "now.\n"
    assert len(_parse(largo)["extracto"]) == 300


def _mock_twd(textos_por_url: dict[str, str | Exception]):
    async def _get(url, **kwargs):
        valor = textos_por_url[url]
        if isinstance(valor, Exception):
            raise valor
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = valor
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx), client


def _limpiar_twd():
    alerts_ext._twd_cache["data"] = None
    alerts_ext._twd_cache["ts"] = 0.0
    alerts_ext._twd_cache["fallo_ts"] = None


def test_get_sistemas_sinopticos_usa_el_texto_crudo():
    _limpiar_twd()
    factory, client = _mock_twd({alerts_ext.TWD_URL: _TWD_ENCABEZADO + _TWD_RUTINA_CARIBE})
    with patch.object(alerts_ext.httpx, "AsyncClient", factory):
        out = asyncio.run(alerts_ext.get_sistemas_sinopticos())
        asyncio.run(alerts_ext.get_sistemas_sinopticos())  # 2ª llamada: cache (TTL 1h)

    assert out["sistemas"] == []
    assert client.get.await_count == 1


def test_get_sistemas_sinopticos_cae_al_html_y_lo_limpia():
    _limpiar_twd()
    onda = "...TROPICAL WAVES...\n\nA tropical wave is along 74W from 05N to 14N.\n"
    html_page = "<html><body><pre>" + _TWD_ENCABEZADO + onda.replace("&", "&amp;") + "</pre></body></html>"
    factory, client = _mock_twd({alerts_ext.TWD_URL: Exception("boom"), alerts_ext.TWD_URL_HTML: html_page})
    with patch.object(alerts_ext.httpx, "AsyncClient", factory):
        out = asyncio.run(alerts_ext.get_sistemas_sinopticos())

    assert out["sistemas"] == ["onda_tropical"] and out["afecta_cgsm"] is True


def test_get_sistemas_sinopticos_si_todo_falla_es_none_o_el_ultimo_resultado():
    _limpiar_twd()
    falla = Exception("boom")
    factory, _ = _mock_twd({alerts_ext.TWD_URL: falla, alerts_ext.TWD_URL_HTML: falla})
    with patch.object(alerts_ext.httpx, "AsyncClient", factory):
        assert asyncio.run(alerts_ext.get_sistemas_sinopticos()) is None

    previo = {"sistemas": ["vaguada"], "afecta_cgsm": False, "extracto": "x", "emitido": None}
    alerts_ext._twd_cache["data"], alerts_ext._twd_cache["ts"] = previo, -1e9  # vencido
    with patch.object(alerts_ext.httpx, "AsyncClient", factory):
        assert asyncio.run(alerts_ext.get_sistemas_sinopticos()) == previo


def test_get_sistemas_sinopticos_tras_una_falla_no_reintenta_dentro_del_cache_negativo():
    _limpiar_twd()
    falla = Exception("boom")
    factory, client = _mock_twd({alerts_ext.TWD_URL: falla, alerts_ext.TWD_URL_HTML: falla})
    with patch.object(alerts_ext.httpx, "AsyncClient", factory):
        asyncio.run(alerts_ext.get_sistemas_sinopticos())
        asyncio.run(alerts_ext.get_sistemas_sinopticos())  # 2ª: dentro de los 5 min

    assert client.get.await_count == 2  # solo la 1ª ronda (url cruda + html)


def test_get_sistemas_sinopticos_rechaza_respuestas_que_no_son_un_twd():
    _limpiar_twd()
    basura = "<html>Service unavailable</html>"
    factory, _ = _mock_twd({alerts_ext.TWD_URL: basura, alerts_ext.TWD_URL_HTML: basura})
    with patch.object(alerts_ext.httpx, "AsyncClient", factory):
        assert asyncio.run(alerts_ext.get_sistemas_sinopticos()) is None
