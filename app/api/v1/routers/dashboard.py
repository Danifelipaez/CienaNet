"""Endpoints del dashboard interno CienRayas (vistas Mapa / Pregunta IA / Sistema).

GET  /dashboard/points         — puntos de pesca con condición/IPP actual
GET  /dashboard/species        — catálogo de especies (estático, ver ponytail abajo)
POST /dashboard/ai/ask         — pregunta libre al AIProvider configurado
GET  /dashboard/system-status  — estado de APIs externas + métricas del bot
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_admin
from app.core.database import get_db
from app.schemas.dashboard import AskRequest, AskResponse
from app.services.ai_service import get_ai_provider
from app.services.dashboard_service import get_latest_snapshot
from app.services.points_service import get_points
from app.services.system_status_service import get_system_status

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ponytail: 4 valores fijos no justifican una tabla — agregar tabla `species`
# solo si esto necesita curarse desde un admin UI más adelante.
_ESPECIES = [
    {"id": "camaron", "label": "Camarón"},
    {"id": "lisa", "label": "Lisa"},
    {"id": "mojarra", "label": "Mojarra"},
    {"id": "robalo", "label": "Róbalo"},
]


@router.get("/points")
async def points(db: AsyncSession = Depends(get_db)) -> dict:
    """Puntos de pesca con condición de semáforo, IPP y observación comunitaria."""
    return {"puntos": await get_points(db)}


@router.get("/species")
async def species() -> dict:
    """Catálogo de especies para el filtro del mapa."""
    return {"especies": _ESPECIES}


@router.post("/ai/ask", response_model=AskResponse)
async def ask_ai(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> AskResponse:
    """Pregunta libre al proveedor de IA configurado (stub hasta que se conecte uno real)."""
    snapshot = await get_latest_snapshot(db)
    system = (
        "Eres el asistente técnico-científico de CienRayas para el equipo de "
        "monitoreo de la Ciénaga Grande de Santa Marta. Contexto ambiental actual: "
        f"{snapshot['semaphore']['reason']}, clorofila {snapshot['satellite'].get('chlorophyll_mgm3')} "
        f"mg/m³, temperatura superficial {snapshot['satellite'].get('sst_celsius')} °C. "
        "Responde en español, citando los datos disponibles."
    )
    respuesta = await get_ai_provider().complete(system=system, user=body.pregunta)
    return AskResponse(respuesta=respuesta)


@router.get("/system-status")
async def system_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    """Estado de APIs externas, métricas del bot y log de alertas enviadas."""
    return await get_system_status(db)
