"""Envía alertas proactivas por WhatsApp: cambio de color del semáforo y
vendaval previsto (ver docs/ALERTAS_VENDAVAL.md).

Se llama después de cada refresco del snapshot ambiental (ver app/main.py).
Ambas alertas comparten `alert_log` como bitácora, pero cada una deduplica
solo contra sus propias filas (`alert_type`, migración 013) — si compartieran
el "último registro sin filtrar", una alerta de vendaval intercalada haría
pensar a maybe_send_alert() que el color cambió (o viceversa) y reenviaría
sin que la condición real haya cambiado.
"""

import logging

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import ExternalAlert
from app.models.messaging import AlertLog, User
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
# ponytail: un solo template genérico. Debe crearse y aprobarse en Meta Business
# Manager con este nombre antes de que el envío funcione en producción.
_ALERT_TEMPLATE = "alerta_condicion"

# Clave del advisory lock de maybe_send_alert(): serializa llamadas
# concurrentes (dos workers, Vercel + servidor universitario, etc.) para que
# no lean el mismo "último color" antes de que la primera confirme su AlertLog.
_ALERT_LOCK_KEY = "cienanet_bot:alert_service:maybe_send_alert"


async def maybe_send_alert(semaphore: dict, db: AsyncSession) -> None:
    """Si el color cambió desde la última alerta registrada, notifica a suscritos.

    pg_advisory_xact_lock serializa el check-then-act: sin esto, dos llamadas
    concurrentes podrían leer el mismo último color y duplicar el envío real
    de WhatsApp a los pescadores suscritos.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _ALERT_LOCK_KEY})

    last = (
        await db.execute(
            select(AlertLog)
            .where(AlertLog.alert_type == "semaforo")
            .order_by(desc(AlertLog.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    color = semaphore["color"]
    if last and last.color == color:
        await db.commit()  # libera el lock; nada que persistir
        return  # mismo estado que la última alerta, no repetir
    if color == "green" and (not last or last.color == "green"):
        await db.commit()
        return  # nada que avisar si ya estaba en verde

    recipients = (
        await db.execute(select(User).where(User.alertas_activas.is_(True)))
    ).scalars().all()

    texto = f"{_EMOJI.get(color, '')} {semaphore['reason']}"
    sent_count = 0
    for user in recipients:
        result = await whatsapp_service.send_template_message(
            user.wa_id, _ALERT_TEMPLATE, params=[semaphore["reason"]]
        )
        if result:
            sent_count += 1

    db.add(
        AlertLog(
            color=color,
            zonas="Todas",
            canal="whatsapp",
            texto=texto,
            destinatarios_count=sent_count,
        )
    )
    await db.commit()  # libera el lock
    logger.info("Alerta %s enviada a %d destinatarios", color, sent_count)


# ponytail: template propio, igual que _ALERT_TEMPLATE — debe crearse y
# aprobarse en Meta Business Manager con este nombre antes de funcionar en prod.
_WIND_ALERT_TEMPLATE = "alerta_vendaval"
_WIND_EMOJI = "⚠️"

_WIND_ALERT_LOCK_KEY = "cienanet_bot:alert_service:maybe_send_wind_alert"


def _format_hora(timestamp_iso: str) -> str:
    """Convierte '2026-08-30T14:00' (hora local America/Bogota, ver
    get_wind_gust_forecast) a '30/08 14:00'. Sin datetime.strptime ni locale:
    es solo texto de un mensaje corto de WhatsApp, no un valor que se vuelva
    a parsear."""
    try:
        fecha, hora = timestamp_iso.split("T")
        _anio, mes, dia = fecha.split("-")
        return f"{dia}/{mes} {hora}"
    except ValueError:
        return timestamp_iso


async def maybe_send_wind_alert(vendaval: dict | None, db: AsyncSession) -> None:
    """Si el pronóstico anticipa una ráfaga de vendaval, notifica a suscritos.

    `vendaval` es el resultado ya calculado de signals.vendaval_risk() (mismo
    patrón que maybe_send_alert recibe el semáforo ya evaluado, no recalcula).
    Dedup: compara la hora pronosticada contra la del último AlertLog tipo
    'vendaval' — si un refresco posterior sigue anticipando la MISMA hora, no
    reenvía; si el pronóstico se actualiza y cambia la hora (o ya pasó y hay
    una nueva), sí avisa de nuevo.
    """
    if vendaval is None:
        return  # nada que evaluar — ni siquiera vale la pena el advisory lock

    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _WIND_ALERT_LOCK_KEY})

    last = (
        await db.execute(
            select(AlertLog)
            .where(AlertLog.alert_type == "vendaval")
            .order_by(desc(AlertLog.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if last and last.zonas == vendaval["timestamp"]:
        await db.commit()  # libera el lock; ya se avisó de esta misma hora prevista
        return

    hora = _format_hora(vendaval["timestamp"])
    gust = round(vendaval["wind_gust_kmh"])
    mensaje = (
        f"Viento fuerte anunciado para el {hora}, con ráfagas de hasta {gust} km/h. "
        "Evita salir a pescar en ese horario y asegura bien tu embarcación."
    )
    texto = f"{_WIND_EMOJI} {mensaje}"

    recipients = (
        await db.execute(select(User).where(User.alertas_activas.is_(True)))
    ).scalars().all()

    sent_count = 0
    for user in recipients:
        result = await whatsapp_service.send_template_message(
            user.wa_id, _WIND_ALERT_TEMPLATE, params=[mensaje]
        )
        if result:
            sent_count += 1

    db.add(
        ExternalAlert(
            source="open-meteo",
            alert_type="vendaval",
            title=f"Vendaval previsto — ráfaga {gust} km/h",
            description=mensaje,
        )
    )
    db.add(
        AlertLog(
            alert_type="vendaval",
            color="viento",
            zonas=vendaval["timestamp"],
            canal="whatsapp",
            texto=texto,
            destinatarios_count=sent_count,
        )
    )
    await db.commit()  # libera el lock
    logger.info("Alerta de vendaval (%s, %d km/h) enviada a %d destinatarios", hora, gust, sent_count)
