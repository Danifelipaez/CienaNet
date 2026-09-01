"""App FastAPI de CienaNet Bot."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routers import admin, dashboard, data, sensors, webhook
from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _hourly_refresh() -> None:
    # ponytail: loop solo tiene sentido en un proceso persistente (uvicorn
    # local o el servidor universitario, ver settings.run_scheduler).
    from app.services.alert_service import maybe_send_alert
    from app.services.dashboard_service import get_latest_snapshot

    while True:
        try:
            async with AsyncSessionLocal() as db:
                snapshot = await get_latest_snapshot(db)
                await maybe_send_alert(snapshot["semaphore"], db)
            logger.info("Snapshot ambiental actualizado")
        except Exception as exc:
            logger.error("Error en refresco horario: %s", exc)
        await asyncio.sleep(3600)


async def _nowcast_refresh() -> None:
    """Nowcast de tormenta por rayos GOES-19 GLM (docs/ALERTAS_VENDAVAL.md) —
    cadencia propia de 10 min, distinta de _hourly_refresh: el cálculo de
    velocidad de tormenta_aproximandose() necesita instantáneas cercanas en el
    tiempo, no una por hora.

    `anterior` vive en esta misma función (variable de closure del while, como
    ya hace este archivo) — ponytail: en memoria de proceso, un reinicio
    pierde un ciclo; el siguiente (10 min después) la repone sin intervención.
    """
    from app.core.config import settings
    from app.services.alert_service import maybe_send_storm_alert
    from app.services.ingestion.lightning import get_lightning_flashes, set_ultimo_nowcast
    from app.services.signals import tormenta_aproximandose

    anterior: dict | None = None
    while True:
        try:
            actual = await get_lightning_flashes()
            resultado = tormenta_aproximandose(
                anterior, actual, settings.cienaga_lat, settings.cienaga_lon, settings.nowcast_eta_max_min
            )
            set_ultimo_nowcast(resultado)
            async with AsyncSessionLocal() as db:
                await maybe_send_storm_alert(resultado, db)
            anterior = actual
        except Exception as exc:
            logger.error("Error en refresco de nowcast: %s", exc)
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # run_scheduler debe estar en true en un único deployment a la vez (ver
    # app/core/config.py). El advisory lock en maybe_send_alert ya protege
    # contra duplicados si dos instancias lo activaran al mismo tiempo, pero
    # este gate evita de entrada llamadas redundantes a APIs externas.
    if settings.run_scheduler:
        # Referencia fuerte obligatoria: el event loop solo retiene una referencia
        # débil a la task, así que sin guardarla el GC puede recolectarla y el
        # scheduler se detiene en silencio (sin log, sin error).
        app.state.refresh_task = asyncio.create_task(_hourly_refresh())
        app.state.nowcast_task = asyncio.create_task(_nowcast_refresh())
    yield


app = FastAPI(title="CienaNet Bot", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Vacío por defecto — ver settings.cors_allowed_origins. Ningún fetch de
    # navegador es legítimo hoy (server-to-server vía BACKEND_URL).
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router, prefix="/api/v1")
app.include_router(data.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(webhook.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0", "deploy": "2026-06-30"}
