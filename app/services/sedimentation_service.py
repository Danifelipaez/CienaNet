"""Zonas de sedimentación para la capa del mapa del dashboard."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import SedimentationZone


async def get_sedimentation_zones(db: AsyncSession) -> list[dict]:
    zones = (
        await db.execute(select(SedimentationZone).order_by(SedimentationZone.nombre))
    ).scalars().all()
    return [
        {
            "id": str(z.id),
            "nombre": z.nombre,
            "polygon": z.polygon,
            "nivel": z.nivel,
            "observacion": z.observacion,
        }
        for z in zones
    ]
