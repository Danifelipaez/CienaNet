"""Endpoints del dashboard ambiental (V-06).

GET /data/latest  — snapshot actual completo
GET /data/history — serie de tiempo (default 30 días)
GET /data/zones   — IPP por zona (ranking actual)
GET /data/alerts  — alertas activas (ciclones + semáforo rojo)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.environmental import DailySemaphore
from app.schemas.environmental import DashboardSnapshot, HistoryResponse
from app.services.dashboard_history import get_history
from app.services.dashboard_service import get_latest_snapshot
from app.services.ingestion.alerts_ext import get_cyclone_alerts

router = APIRouter(prefix="/data", tags=["dashboard"])


@router.get("/latest", response_model=DashboardSnapshot)
async def latest_conditions(db: AsyncSession = Depends(get_db)) -> DashboardSnapshot:
    """Snapshot ambiental actual: semáforo, meteorología, satélite, sensores e IPP."""
    return await get_latest_snapshot(db)


@router.get("/history", response_model=HistoryResponse)
async def data_history(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    """Serie de tiempo de los últimos N días (meteorología, semáforo, satélite)."""
    return await get_history(db, days)


@router.get("/zones")
async def zones_ipp(db: AsyncSession = Depends(get_db)) -> dict:
    """IPP actual por zona, tomado del semáforo diario más reciente."""
    row = (
        await db.execute(
            select(DailySemaphore).order_by(desc(DailySemaphore.date)).limit(1)
        )
    ).scalar_one_or_none()

    if not row or not row.ipp_ranking:
        return {"ipp_ranking": [], "date": None}

    return {"ipp_ranking": row.ipp_ranking, "date": row.date.isoformat()}


@router.get("/alerts")
async def active_alerts(db: AsyncSession = Depends(get_db)) -> dict:
    """Alertas activas: ciclones NOAA + color del semáforo actual."""
    cyclones = await get_cyclone_alerts()

    semaphore = (
        await db.execute(
            select(DailySemaphore).order_by(desc(DailySemaphore.date)).limit(1)
        )
    ).scalar_one_or_none()

    return {
        "cyclones": cyclones,
        "semaphore_color": semaphore.color if semaphore else None,
    }
