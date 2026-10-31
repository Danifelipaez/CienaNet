"""Alertas oficiales del IDEAM en formato CAP 1.2 (registradas ante la OMM,
docs/AVISOS_CLIMA.md): índice Atom en https://alertascap.ideam.gov.co/ospa/xml y un
XML CAP por alerta. Licencia CC BY 4.0, sin autenticación, `max-age=300`.

Solo interesan las alertas cuya área nombra la zona de la CGSM: el área marina
"Caribe central" (el polígono es el mar, la ciénaga queda ~14 km por fuera, así que
se filtra por nombre y no por punto-en-polígono) y las zonas hidrográficas que
drenan a la ciénaga. Deslizamientos e incendios (terrestres) se descartan.
"""

import logging
import xml.etree.ElementTree as ET

import feedparser

from app.services.ingestion.avisos_ext import _con_cache, _get

logger = logging.getLogger(__name__)

FEED_URL = "https://alertascap.ideam.gov.co/ospa/xml"
_CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

# (texto en el título del índice, en minúsculas -> (tipo, nombre para el pescador))
ZONAS = (
    ("caribbean central", ("ideam_mar", "el mar Caribe frente a la Ciénaga")),
    ("cga. grande de santa marta", ("ideam_cuenca", "la Ciénaga Grande de Santa Marta")),
    ("ciénaga grande de santa marta", ("ideam_cuenca", "la Ciénaga Grande de Santa Marta")),
    ("río aracataca", ("ideam_cuenca", "el río Aracataca")),
    ("río fundación", ("ideam_cuenca", "el río Fundación")),
    ("río sevilla", ("ideam_cuenca", "el río Sevilla")),
    ("directos al bajo magdalena entre calamar y desembocadura", ("ideam_cuenca", "los caños del bajo Magdalena")),
)
_DESCARTE = ("landslide", "forest fire")


def zona_de(texto: str) -> tuple[str, str] | None:
    bajo = texto.lower()
    if any(bajo.startswith(d) for d in _DESCARTE):
        return None
    return next((z for clave, z in ZONAS if clave in bajo), None)


def parse_cap(xml: str) -> dict:
    """Bloque es-CO (o el primero) de un CAP 1.2: evento, severidad, inicio y fin."""
    raiz = ET.fromstring(xml)
    infos = raiz.findall("cap:info", _CAP_NS)
    if not infos:
        raise ValueError("CAP sin <info>")
    info = next((i for i in infos if (i.findtext("cap:language", "", _CAP_NS) or "").startswith("es")), infos[0])
    return {
        "id": raiz.findtext("cap:identifier", "", _CAP_NS),
        "evento": info.findtext("cap:event", "", _CAP_NS),
        "severidad": info.findtext("cap:severity", "", _CAP_NS),
        "inicio": info.findtext("cap:onset", None, _CAP_NS) or info.findtext("cap:effective", None, _CAP_NS),
        "expira": info.findtext("cap:expires", None, _CAP_NS),
    }


async def get_alertas_ideam() -> tuple[list[dict] | None, str]:
    """Alertas IDEAM vigentes que tocan la CGSM. Lista vacía = el feed respondió y no
    hay ninguna para la zona (no es lo mismo que None = no se pudo revisar)."""

    async def fetch() -> list[dict]:
        feed = feedparser.parse((await _get(FEED_URL)).text)
        if feed.bozo and not feed.entries:
            raise ValueError("índice CAP del IDEAM ilegible")
        alertas = []
        for e in feed.entries:
            zona = zona_de(f"{e.get('title', '')} {e.get('summary', '')}")
            href = next((lk.get("href") for lk in e.get("links", []) if lk.get("type") == "application/cap+xml"), None)
            if zona is None or not href:
                continue
            cap = parse_cap((await _get(href)).text)
            alertas.append({**cap, "tipo": zona[0], "zona": zona[1]})
        return alertas

    return await _con_cache("ideam_cap", 900.0, 6 * 3600.0, fetch)
