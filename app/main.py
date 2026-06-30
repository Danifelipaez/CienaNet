"""App FastAPI de CienaNet Bot."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routers import admin, data, sensors
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _hourly_refresh() -> None:
    # ponytail: loop solo funciona con uvicorn (local dev).
    # En Vercel serverless usar Vercel Cron apuntando a GET /data/latest.
    from app.services.dashboard_service import get_latest_snapshot

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await get_latest_snapshot(db)
            logger.info("Snapshot ambiental actualizado")
        except Exception as exc:
            logger.error("Error en refresco horario: %s", exc)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_hourly_refresh())
    yield


app = FastAPI(title="CienaNet Bot", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # ponytail: abierto para el MVP; restringir al dominio del dashboard antes de prod
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router, prefix="/api/v1")
app.include_router(data.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
