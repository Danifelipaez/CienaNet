"""Router de ingesta de sensores ESP32: POST /sensors/ingest (V-04)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_sensor
from app.core.database import get_db
from app.models.environmental import Sensor
from app.schemas.sensor import SensorReadingIn
from app.services.sensor_service import SensorIdentityMismatchError, process_reading

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post("/ingest", status_code=201)
async def ingest(
    reading: SensorReadingIn,
    sensor: Sensor = Depends(get_current_sensor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recibe y persiste una lectura de sensor IoT. Requiere header X-Api-Key."""
    try:
        await process_reading(reading, sensor, db)
    except SensorIdentityMismatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}
