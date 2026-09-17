"""Catálogo de consultas generales que el AIProvider puede invocar (function
calling) para responder con datos reales — actuales o históricos — en vez de
inventarlos o quedarse solo con el snapshot resumido de ai_context.py.

Cada Tool envuelve un service ya existente: cero SQL nuevo salvo
alert_service.get_alert_status. Agregar un tool nuevo es agregar una entrada
a TOOLS, no tocar el loop de ai_service.py.
"""

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.alert_service import get_alert_status
from app.services.dashboard_history import get_history
from app.services.ingestion.invemar_calidad import VARIABLES
from app.services.points_service import get_points
from app.services.sedimentation_service import get_sedimentation_zones
from app.services.snapshot_service import get_calidad_agua_persistida, read_persisted


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema (subset OpenAPI) — formato de Gemini functionDeclarations
    handler: Callable[[AsyncSession, dict], Awaitable[dict]]


async def _condicion_actual(db: AsyncSession, args: dict) -> dict:
    return await read_persisted(db)


async def _historico_ambiental(db: AsyncSession, args: dict) -> dict:
    dias = max(1, min(int(args.get("dias", 7)), 365))
    return await get_history(db, dias)


async def _donde_pescar(db: AsyncSession, args: dict) -> dict:
    return {"puntos": await get_points(db)}


async def _zonas_sedimentacion(db: AsyncSession, args: dict) -> dict:
    return {"zonas": await get_sedimentation_zones(db)}


async def _alertas_activas(db: AsyncSession, args: dict) -> dict:
    return await get_alert_status(db)


async def _calidad_agua_estaciones(db: AsyncSession, args: dict) -> dict:
    variable = args.get("variable", "Oxigeno Disuelto")
    if variable not in VARIABLES:
        variable = "Oxigeno Disuelto"
    return {"estaciones": await get_calidad_agua_persistida(db, variable)}


TOOLS: list[Tool] = [
    Tool(
        "condicion_actual",
        "Estado ambiental actual completo: semáforo, clima, agua (pH, conductividad, "
        "nivel), satélite por zona, tendencias de 24h/7d. Úsalo para cualquier "
        "pregunta sobre el presente que el contexto ya dado no cubra (por ejemplo, "
        "un dato puntual de pH o conductividad).",
        {"type": "object", "properties": {}},
        _condicion_actual,
    ),
    Tool(
        "historico_ambiental",
        "Series de tiempo de los últimos N días: clima, agua, semáforo y capturas. "
        "Úsalo para preguntas sobre el pasado, como 'la semana pasada', 'este mes' "
        "o 'ha llovido mucho'.",
        {
            "type": "object",
            "properties": {"dias": {"type": "integer", "description": "Días hacia atrás, 1-365"}},
            "required": ["dias"],
        },
        _historico_ambiental,
    ),
    Tool(
        "donde_pescar",
        "Ranking de zonas o puntos de pesca según la condición actual (IPP).",
        {"type": "object", "properties": {}},
        _donde_pescar,
    ),
    Tool(
        "zonas_sedimentacion",
        "Zonas de la ciénaga con sedimentación reportada.",
        {"type": "object", "properties": {}},
        _zonas_sedimentacion,
    ),
    Tool(
        "alertas_activas",
        "Alertas vigentes: color del semáforo, ciclones NOAA y tormentas detectadas "
        "por rayos (GOES-19).",
        {"type": "object", "properties": {}},
        _alertas_activas,
    ),
    Tool(
        "calidad_agua_estaciones",
        "Calidad del agua por estación de monitoreo INVEMAR (REDCAM) en la Ciénaga "
        "Grande y ríos tributarios: oxígeno disuelto, salinidad, pH, temperatura o "
        "sólidos suspendidos totales, con su clase de calidad. Úsalo para preguntas "
        "sobre condiciones del agua en un punto o sector específico.",
        {
            "type": "object",
            "properties": {
                "variable": {
                    "type": "string",
                    "enum": list(VARIABLES),
                    "description": "Variable a consultar, por defecto Oxigeno Disuelto",
                }
            },
        },
        _calidad_agua_estaciones,
    ),
]

_BY_NAME = {t.name: t for t in TOOLS}


def as_gemini_declarations() -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in TOOLS]


def get_handler(name: str) -> Callable[[AsyncSession, dict], Awaitable[dict]] | None:
    tool = _BY_NAME.get(name)
    return tool.handler if tool else None
