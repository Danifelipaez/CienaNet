"""Endpoints de administración: registro y listado de sensores ESP32.

Protegidos con X-Admin-Key (env var ADMIN_API_KEY).
La API key raw se muestra UNA sola vez al registrar — no se puede recuperar después.
"""

import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_api_key
from app.models.environmental import Sensor

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(x_admin_key: str = Header(...)) -> None:
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Admin key inválida")


class SensorCreate(BaseModel):
    device_id: str
    location: str | None = None


class SensorCreated(BaseModel):
    sensor_id: str
    device_id: str
    location: str | None
    raw_api_key: str


class SensorInfo(BaseModel):
    sensor_id: str
    device_id: str
    location: str | None
    active: bool


@router.post("/sensors", response_model=SensorCreated, status_code=201)
async def register_sensor(
    body: SensorCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin),
) -> SensorCreated:
    """Registra un nuevo sensor ESP32. Retorna la API key en texto plano (solo esta vez)."""
    existing = (
        await db.execute(select(Sensor).where(Sensor.device_id == body.device_id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Sensor '{body.device_id}' ya existe")

    raw_key = secrets.token_urlsafe(32)
    sensor = Sensor(
        device_id=body.device_id,
        api_key_hash=hash_api_key(raw_key),
        location=body.location,
    )
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)

    return SensorCreated(
        sensor_id=str(sensor.id),
        device_id=sensor.device_id,
        location=sensor.location,
        raw_api_key=raw_key,
    )


@router.get("/sensors", response_model=list[SensorInfo])
async def list_sensors(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin),
) -> list[SensorInfo]:
    """Lista todos los sensores registrados (sin exponer hashes de API key)."""
    rows = (await db.execute(select(Sensor).order_by(Sensor.created_at))).scalars().all()
    return [
        SensorInfo(
            sensor_id=str(s.id),
            device_id=s.device_id,
            location=s.location,
            active=s.active,
        )
        for s in rows
    ]
