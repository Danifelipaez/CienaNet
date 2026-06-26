"""Validación de firmas Meta y hashing de API keys de sensores."""

import hashlib
import hmac

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.environmental import Sensor


def verify_hmac_meta(payload: bytes, signature_header: str) -> bool:
    """Valida la firma HMAC-SHA256 de un webhook de Meta.

    `signature_header` llega como 'sha256=<hex>'. Se compara en tiempo
    constante para evitar timing attacks. Llamar SIEMPRE antes de parsear
    el body del webhook.
    """
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def hash_api_key(raw_key: str) -> str:
    """Hashea la API key de un sensor con PBKDF2 antes de guardarla en DB."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        raw_key.encode(),
        settings.sensor_api_key_secret.encode(),
        100_000,
    ).hex()


async def verify_sensor_api_key(raw_key: str, db: AsyncSession) -> Sensor | None:
    """Devuelve el sensor cuyo api_key_hash coincide con la key, o None."""
    digest = hash_api_key(raw_key)
    result = await db.execute(select(Sensor).where(Sensor.api_key_hash == digest))
    return result.scalar_one_or_none()
