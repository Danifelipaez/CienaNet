"""Puntos de pesca con condición/IPP actual, para la vista Mapa del dashboard.

Lee el último estado ya persistido (snapshot_service.read_persisted) — no vuelve
a llamar APIs externas en cada request.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fishing_points import FishingPoint
from app.services.ipp import rank_points
from app.services.snapshot_service import read_persisted


async def get_points(db: AsyncSession) -> list[dict]:
    estado = await read_persisted(db)
    points = (await db.execute(select(FishingPoint).order_by(FishingPoint.nombre))).scalars().all()
    # Sin DailySemaphore persistido, se asume "green" (comportamiento previo) en
    # vez de propagar el "sin dato" honesto de read_persisted — la vista Mapa
    # necesita un color por punto para pintarse, no un tercer estado "gris".
    semaphore_color = estado["semaphore"].get("color") or "green"
    return rank_points(estado["water"], estado["satellite"], estado["weather"], semaphore_color, points)
