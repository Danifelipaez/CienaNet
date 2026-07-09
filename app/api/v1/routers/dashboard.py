"""Endpoints del dashboard interno CienRayas (vistas Mapa / Pregunta IA / Sistema).

GET  /dashboard/points         — puntos de pesca con condición/IPP actual
GET  /dashboard/species        — catálogo de especies (estático, ver ponytail abajo)
GET  /dashboard/sedimentation  — zonas de sedimentación (capa del mapa)
POST /dashboard/ai/ask         — pregunta libre al AIProvider configurado
GET  /dashboard/ai/history     — historial agrupado en conversaciones (un hilo = tarjeta)
DELETE /dashboard/ai/history/{conversation_id} — borra una conversación entera del usuario
GET  /dashboard/system-status  — estado de APIs externas + métricas del bot
"""

import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_dashboard_user, require_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.dashboard import AIConversation
from app.schemas.dashboard import (
    AIConversationItem,
    AITurn,
    AskRequest,
    AskResponse,
)
from app.services.ai_service import get_ai_provider
from app.services.dashboard_service import build_ai_context, get_latest_snapshot
from app.services.points_service import get_points
from app.services.sedimentation_service import get_sedimentation_zones
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


@router.get("/sedimentation")
async def sedimentation(db: AsyncSession = Depends(get_db)) -> dict:
    """Zonas de sedimentación (polígonos) para la capa del mapa."""
    return {"zonas": await get_sedimentation_zones(db)}


def _parrafos_to_text(parrafos: list | None, sugerencia: str | None) -> str:
    """Aplana una respuesta guardada (JSONB de parrafos) a texto plano para reenviarla
    a Gemini como turno 'model' del hilo. La memoria no necesita el markup del diseño."""
    parts: list[str] = []
    for p in parrafos or []:
        if p.get("titulo"):
            parts.append(str(p["titulo"]))
        if p.get("html"):
            parts.append(str(p["html"]))
        for it in p.get("items") or []:
            parts.append(f"{it.get('v', '')} {it.get('d', '')} ({it.get('fuente', '')})")
    if sugerencia:
        parts.append(f"Sugerencia: {sugerencia}")
    return "\n".join(parts) or "(respuesta previa)"


async def _load_thread(
    user_id: str, conversation_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    """Últimos turnos de ESTA conversación como contexto para Gemini (cronológico).

    Cada fila aporta dos turnos: pregunta (user) + respuesta aplanada (model).
    Acotado por settings.ai_history_turns para no inflar el costo de tokens. La
    memoria es por conversación: un hilo nuevo arranca sin arrastrar los anteriores.
    """
    rows = (
        await db.execute(
            select(AIConversation.pregunta, AIConversation.respuesta, AIConversation.sugerencia)
            .where(
                AIConversation.user_id == user_id,
                AIConversation.conversation_id == conversation_id,
            )
            .order_by(desc(AIConversation.created_at))
            .limit(settings.ai_history_turns)
        )
    ).all()
    history: list[dict] = []
    for pregunta, respuesta, sugerencia in reversed(rows):
        history.append({"role": "user", "parts": [{"text": pregunta}]})
        history.append({"role": "model", "parts": [{"text": _parrafos_to_text(respuesta, sugerencia)}]})
    return history


@router.post("/ai/ask", response_model=AskResponse)
async def ask_ai(
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_dashboard_user),
    _: None = Depends(require_admin),
) -> AskResponse:
    """Pregunta libre al proveedor de IA, con memoria del hilo del usuario.

    El hilo (preguntas/respuestas previas de ESTE usuario) se reenvía a Gemini como
    contexto, así los seguimientos tienen continuidad. Cada usuario tiene su propio
    hilo aislado, seguro ante peticiones simultáneas de varios usuarios.
    """
    snapshot = await get_latest_snapshot(db)
    system = (
        "Eres el asistente técnico-científico de CienRayas para el equipo de "
        "monitoreo de la Ciénaga Grande de Santa Marta. Contexto ambiental actual: "
        f"{build_ai_context(snapshot)} "
        "Responde en español, usando solo los datos de este contexto (no inventes "
        "valores). Cuando cites un dato puntual (temperatura, humedad, viento, "
        "precipitación, nivel de río, clorofila, etc.), agrégalo también como un "
        "párrafo tipo 'datos' con un item por dato — 'v' el valor con su unidad, "
        "'d' una descripción corta, y 'fuente' la estación/fuente exacta de este "
        "contexto (ej. 'Open-Meteo — Tasajera', 'IDEAM — Media Luna'), así el "
        "dashboard lo muestra como ficha, no como texto suelto."
    )
    if body.contexto:
        system += (
            "\nEl usuario tiene seleccionado este contexto en el mapa: "
            f"{json.dumps(body.contexto, ensure_ascii=False)}."
        )

    # Hilo existente o conversación nueva: si el cliente no manda conversation_id,
    # minteamos uno y lo devolvemos para que fije el turno actual al mismo hilo.
    conversation_id = body.conversation_id or uuid.uuid4()

    history = await _load_thread(user_id, conversation_id, db)
    result = await get_ai_provider().answer_structured(
        system=system, user=body.pregunta, history=history
    )

    db.add(
        AIConversation(
            user_id=user_id,
            conversation_id=conversation_id,
            pregunta=body.pregunta,
            respuesta=result["parrafos"],
            sugerencia=result.get("sugerencia"),
            contexto=body.contexto,
        )
    )
    await db.commit()

    return AskResponse(
        parrafos=result["parrafos"],
        sugerencia=result.get("sugerencia"),
        conversation_id=str(conversation_id),
    )


@router.get("/ai/history")
async def ai_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_dashboard_user),
    _: None = Depends(require_admin),
) -> dict:
    """Historial DEL USUARIO agrupado en conversaciones (un hilo = una tarjeta).

    Los turnos se agrupan por conversation_id como hacen las plataformas de chat:
    cada conversación es una tarjeta titulada por su primera pregunta, ordenadas
    por actividad más reciente. `limit` acota el número de conversaciones.
    """
    # Traemos turnos recientes (cap holgado) y agrupamos en memoria. En orden desc
    # el primer turno visto de cada hilo es el más reciente → hilos ordenados por
    # actividad. Dentro de cada hilo revertimos a orden cronológico.
    rows = (
        await db.execute(
            select(AIConversation)
            .where(AIConversation.user_id == user_id)
            .order_by(desc(AIConversation.created_at))
            .limit(max(limit, 1) * 30)
        )
    ).scalars().all()

    convos: dict[str, list[AIConversation]] = {}
    for r in rows:
        convos.setdefault(str(r.conversation_id), []).append(r)

    historial: list[AIConversationItem] = []
    for cid, turns in list(convos.items())[:limit]:
        turns_asc = list(reversed(turns))  # cronológico
        historial.append(
            AIConversationItem(
                id=cid,
                titulo=turns_asc[0].pregunta,
                created_at=turns_asc[0].created_at.isoformat(),
                updated_at=turns_asc[-1].created_at.isoformat(),
                turnos=[
                    AITurn(
                        id=str(t.id),
                        pregunta=t.pregunta,
                        respuesta=t.respuesta,
                        sugerencia=t.sugerencia,
                        created_at=t.created_at.isoformat(),
                    )
                    for t in turns_asc
                ],
            )
        )
    return {"historial": historial}


@router.delete("/ai/history/{conversation_id}")
async def delete_ai_history(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_dashboard_user),
    _: None = Depends(require_admin),
) -> dict:
    """Borra una conversación entera (todos sus turnos) del historial. Acotado al
    user_id: un usuario solo puede borrar lo suyo, aunque adivine el id de otro."""
    await db.execute(
        delete(AIConversation).where(
            AIConversation.conversation_id == conversation_id,
            AIConversation.user_id == user_id,
        )
    )
    await db.commit()
    return {"ok": True}


@router.get("/system-status")
async def system_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    """Estado de APIs externas, métricas del bot y log de alertas enviadas."""
    return await get_system_status(db)
