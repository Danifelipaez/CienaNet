"""Dependencias compartidas para los routers de la API v1."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_sensor_api_key
from app.models.environmental import Sensor


async def get_current_sensor(
    x_api_key: str = Header(..., description="API key del sensor ESP32"),
    db: AsyncSession = Depends(get_db),
) -> Sensor:
    """Autentica el sensor por API key. Retorna el ORM del sensor o 403."""
    sensor = await verify_sensor_api_key(x_api_key, db)
    if not sensor:
        raise HTTPException(status_code=403, detail="API key inválida")
    return sensor


def require_admin(x_admin_key: str = Header(...)) -> None:
    """Autentica endpoints internos (admin + dashboard) por X-Admin-Key."""
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Admin key inválida")


def get_dashboard_user(x_user_id: str = Header(...)) -> str:
    """Identidad blanda del usuario del dashboard (UUID de localStorage del cliente).

    Sirve para aislar hilo e historial de IA por usuario, no para autorizar — el
    control de acceso es require_admin. Si más adelante se agrega login real, este
    valor se deriva del subject del token sin tocar los endpoints.
    """
    uid = x_user_id.strip()
    if not uid:
        raise HTTPException(status_code=422, detail="X-User-Id requerido")
    return uid
