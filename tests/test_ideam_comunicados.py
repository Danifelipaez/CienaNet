import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.ingestion import ideam_comunicados

_TEXTO_CARIBE = (
    "14/09/2026 \nCOMUNICADO ESPECIAL No. 102 \nPRONÓSTICO DEL ESTADO DEL TIEMPO PARA LA \n"
    "SEMANA DEL 14 AL 18 DE SEPTIEMBRE DE 2026 \n \nHacia el final de la semana se prevé el "
    "tránsito de la onda tropical 49 ... En el centro y oriente del mar Caribe colombiano se "
    "mantendrá la alerta para la navegación menor."
)
_TEXTO_BOGOTA = "COMUNICADO ESPECIAL No. 103 \nLLUVIAS EN BOGOTÁ \n \nSolo Cundinamarca."


def _item(file_id: int, fecha: datetime) -> str:
    return (
        f'<li><a href="/file-download/download/public/{file_id}" type="application/pdf">x.pdf</a>'
        f'<time datetime="{fecha.strftime("%Y-%m-%dT12:00:00Z")}" class="datetime">x</time></li>'
    )


def _run(
    listado: str,
    ai_reply: str | None = "Lluvias fuertes y oleaje de 2 a 3 m en el Caribe el jueves y viernes",
):
    pdfs = {b"102": _TEXTO_CARIBE, b"103": _TEXTO_BOGOTA}

    def handler(request: httpx.Request) -> httpx.Response:
        if "Comunicados-Especiales" in str(request.url):
            return httpx.Response(200, text=listado)
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
        patch.object(ideam_comunicados, "_pdf_texto", side_effect=lambda b: pdfs[b]),
        patch("app.services.ai_service.get_ai_provider", return_value=provider),
    ):
        return asyncio.run(ideam_comunicados.get_alerta_ideam())


def test_comunicado_vigente_de_la_zona():
    hoy = datetime.now(UTC)
    listado = _item(102, hoy) + _item(103, hoy) + _item(101, hoy - timedelta(days=4))
    alerta = _run(listado)
    assert alerta["resumen"] == "Lluvias fuertes y oleaje de 2 a 3 m en el Caribe el jueves y viernes"
    assert "onda tropical 49" in alerta["detalle"]
    assert "BOGOTÁ" not in alerta["detalle"]  # comunicado sin mención de la zona, descartado
    assert alerta["urls"] == ["https://www.ideam.gov.co/file-download/download/public/102"]


def test_sin_ia_cae_al_titulo():
    alerta = _run(_item(102, datetime.now(UTC)), ai_reply=None)
    assert alerta["resumen"] == (
        "Comunicado especial No. 102: Pronóstico del estado del tiempo para la semana del 14 al 18 "
        "de septiembre de 2026"
    )


def test_ia_dice_que_no_aplica_a_la_zona():
    assert _run(_item(102, datetime.now(UTC)), ai_reply="NINGUNO") is None


def test_comunicado_vencido():
    assert _run(_item(102, datetime.now(UTC) - timedelta(days=6))) is None


def test_fuente_caida_sirve_ultimo_dato_bueno():
    ideam_comunicados._cache.update(
        data={"fecha": datetime.now(UTC).date().isoformat(), "resumen": "r", "detalle": "d", "urls": []},
        ts=1.0,
    )
    with patch.object(ideam_comunicados, "_fetch", side_effect=httpx.ConnectTimeout("caído")):
        assert asyncio.run(ideam_comunicados.get_alerta_ideam())["resumen"] == "r"
