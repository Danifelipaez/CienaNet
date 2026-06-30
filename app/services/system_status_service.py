"""Agrega estado de fuentes externas + métricas del bot para la vista Sistema.

ponytail: Open-Meteo y NASA/Copernicus se reportan como 2 fuentes (no 3) porque
SST y clorofila-a se persisten en la misma tabla `satellite_data` sin distinguir
cuál llamada falló — separarlas requeriría que ingestion/satellite.py registre
éxito/fallo por API, no solo el valor final. Tampoco se fabrica "latencia": no
se mide hoy, así que no se inventa un número.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import SatelliteData, WeatherSnapshot
from app.models.messaging import AlertLog, CatchReport, Conversation, User


def _weather_status(last: datetime | None) -> str:
    if last is None:
        return "caido"
    last_aware = last if last.tzinfo else last.replace(tzinfo=UTC)
    age = datetime.now(UTC) - last_aware
    if age <= timedelta(hours=1, minutes=30):
        return "ok"
    if age <= timedelta(hours=6):
        return "degradado"
    return "caido"


def _satellite_status(last: date | None) -> str:
    if last is None:
        return "caido"
    # ingestion/satellite.py espera un lag de ~2 días (jplMURSST41) — no es una falla.
    days_old = (date.today() - last).days
    if days_old <= 2:
        return "ok"
    if days_old <= 7:
        return "degradado"
    return "caido"


async def get_system_status(db: AsyncSession) -> dict:
    weather_row = (
        await db.execute(select(WeatherSnapshot).order_by(desc(WeatherSnapshot.timestamp)).limit(1))
    ).scalar_one_or_none()
    satellite_row = (
        await db.execute(select(SatelliteData).order_by(desc(SatelliteData.date)).limit(1))
    ).scalar_one_or_none()

    apis = [
        {
            "id": "openmeteo",
            "nombre": "Open-Meteo",
            "desc": "Viento, temperatura aire",
            "estado": _weather_status(weather_row.timestamp if weather_row else None),
            "actualizado": weather_row.timestamp.isoformat() if weather_row else None,
        },
        {
            "id": "satelite",
            "nombre": "NASA MODIS / Copernicus Marine",
            "desc": "Temp. superficial, clorofila-a",
            "estado": _satellite_status(satellite_row.date if satellite_row else None),
            "actualizado": satellite_row.date.isoformat() if satellite_row else None,
        },
    ]

    cutoff_30d = datetime.now(UTC) - timedelta(days=30)
    start_of_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    msgs_30d = (
        await db.execute(
            select(func.count()).select_from(Conversation).where(
                Conversation.direction == "out", Conversation.created_at >= cutoff_30d
            )
        )
    ).scalar_one()
    alertas_mes = (
        await db.execute(
            select(func.count()).select_from(AlertLog).where(AlertLog.created_at >= start_of_month)
        )
    ).scalar_one()
    comunidades_activas = (
        await db.execute(select(func.count(func.distinct(User.comunidad))).where(User.comunidad.is_not(None)))
    ).scalar_one()
    reportes_total = (await db.execute(select(func.count()).select_from(CatchReport))).scalar_one()

    bot_metricas = [
        {"id": "msgs", "label": "Mensajes enviados", "valor": msgs_30d, "sub": "últimos 30 días"},
        {"id": "alertas", "label": "Alertas activadas", "valor": alertas_mes, "sub": "este mes"},
        {"id": "comuni", "label": "Comunidades activas", "valor": comunidades_activas, "sub": "con pescadores registrados"},
        {"id": "reportes", "label": "Reportes comunitarios", "valor": reportes_total, "sub": "recibidos"},
    ]

    log_rows = (
        await db.execute(select(AlertLog).order_by(desc(AlertLog.created_at)).limit(20))
    ).scalars().all()
    log_alertas = [
        {
            "hora": r.created_at.isoformat(),
            "tipo": r.color,
            "canal": r.canal,
            "zonas": r.zonas,
            "texto": r.texto,
            "destinatarios": r.destinatarios_count,
        }
        for r in log_rows
    ]

    return {"apis": apis, "bot_metricas": bot_metricas, "log_alertas": log_alertas}
