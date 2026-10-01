import asyncio
from datetime import date, timedelta
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.ai_context import _MESES
from app.services.ingestion import ideam_comunicados

_RESUMEN_IA = "Lluvias y oleaje de 2 a 3 m en el Caribe el viernes 2 de octubre"


def _fecha(d: date) -> str:
    return f"{d.day:02d} de {_MESES[d.month - 1]}"


def _caribe(numero: int, hasta: date) -> str:
    return (
        f"COMUNICADO ESPECIAL No. {numero} \nPRONÓSTICO DEL ESTADO DEL TIEMPO \n \n"
        f"Viernes {_fecha(hasta)} \nLluvias fuertes en el mar Caribe colombiano y el Magdalena."
    )


def _item(file_id: int, publicado: date) -> str:
    return (
        f'<li><a href="/file-download/download/public/{file_id}" type="application/pdf">x.pdf</a>'
        f'<time datetime="{publicado.isoformat()}T12:00:00Z" class="datetime">x</time></li>'
    )


def _run(items: list[tuple[int, date]], pdfs: dict[int, str], ai_reply: str | None = _RESUMEN_IA):
    def handler(request: httpx.Request) -> httpx.Response:
        if "Comunicados-Especiales" in str(request.url):
            return httpx.Response(200, text="".join(_item(i, d) for i, d in items))
        return httpx.Response(200, content=request.url.path.rsplit("/", 1)[-1].encode())

    provider = MagicMock()
    provider.reply_text = AsyncMock(return_value=ai_reply)
    ideam_comunicados._cache.update(data=None, ts=0.0)
    with (
        patch.object(
            ideam_comunicados.httpx,
            "AsyncClient",
            partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
        ),
        patch.object(ideam_comunicados, "_pdf_texto", side_effect=lambda b: pdfs[int(b)]),
        patch("app.services.ai_service.get_ai_provider", return_value=provider),
    ):
        return asyncio.run(ideam_comunicados.get_alerta_ideam())


HOY = ideam_comunicados._hoy()


def test_comunicado_vigente_de_la_zona():
    pdfs = {
        102: _caribe(102, HOY + timedelta(days=1)),
        103: "COMUNICADO ESPECIAL No. 103 \nLLUVIAS EN BOGOTÁ",
    }
    alerta = _run([(102, HOY), (103, HOY)], pdfs)
    assert alerta["resumen"] == _RESUMEN_IA
    assert alerta["hasta"] == (HOY + timedelta(days=1)).isoformat()
    assert "BOGOTÁ" not in alerta["detalle"]  # comunicado sin mención de la zona, descartado
    assert alerta["urls"] == ["https://www.ideam.gov.co/file-download/download/public/102"]


def test_ia_no_decide_si_hay_alerta():
    """Regresión 01-oct-2026: flash-lite respondía NINGUNO al azar con un comunicado
    vigente y el bot decía que no había alerta. La vigencia ya no depende de la IA."""
    pdfs = {102: _caribe(102, HOY + timedelta(days=1))}
    for respuesta_ia in ("NINGUNO", None, ""):
        alerta = _run([(102, HOY)], pdfs, ai_reply=respuesta_ia)
        assert alerta["resumen"] == "Comunicado especial No. 102: Pronóstico del estado del tiempo"


def test_vencido_por_las_fechas_del_texto():
    publicado = HOY - timedelta(days=3)
    assert _run([(102, publicado)], {102: _caribe(102, HOY - timedelta(days=1))}) is None


def test_nuevo_sin_zona_no_tapa_al_anterior_vigente():
    pdfs = {
        103: "COMUNICADO ESPECIAL No. 103 \nLLUVIAS EN BOGOTÁ",
        102: _caribe(102, HOY + timedelta(days=2)),
    }
    alerta = _run([(103, HOY), (102, HOY - timedelta(days=2))], pdfs)
    assert alerta["urls"] == ["https://www.ideam.gov.co/file-download/download/public/102"]


def test_vigente_hasta():
    pub = date(2026, 12, 28)
    # Diciembre que nombra enero -> año siguiente.
    assert ideam_comunicados._vigente_hasta("Sábado 02 de enero", pub) == date(2027, 1, 2)
    # Sin fechas -> _VIGENCIA_DIAS desde la publicación.
    assert ideam_comunicados._vigente_hasta("Alerta por incendios", pub) == date(2027, 1, 1)
    # Fecha lejana (boletín de El Niño) -> tope de _MAX_DIAS.
    assert ideam_comunicados._vigente_hasta("hasta el 15 de marzo", pub) == date(2027, 1, 4)
    # Solo fechas pasadas (repaso de lo que llovió) -> vence ya.
    assert ideam_comunicados._vigente_hasta("el 20 de diciembre llovió", pub) == pub


def test_fuente_caida_sirve_ultimo_dato_bueno():
    ideam_comunicados._cache.update(
        data={"fecha": HOY.isoformat(), "hasta": HOY.isoformat(), "resumen": "r", "detalle": "d", "urls": []},
        ts=1.0,
    )
    with patch.object(ideam_comunicados, "_fetch", side_effect=httpx.ConnectTimeout("caído")):
        assert asyncio.run(ideam_comunicados.get_alerta_ideam())["resumen"] == "r"


def test_dato_en_cache_vencido_no_se_sirve():
    ayer = (HOY - timedelta(days=1)).isoformat()
    ideam_comunicados._cache.update(
        data={"fecha": ayer, "hasta": ayer, "resumen": "r", "detalle": "d", "urls": []}, ts=1e18
    )
    assert asyncio.run(ideam_comunicados.get_alerta_ideam()) is None
