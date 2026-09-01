"""Envía alertas proactivas por WhatsApp: cambio de color del semáforo y
tormenta acercándose (nowcast por rayos, ver docs/ALERTAS_VENDAVAL.md).

maybe_send_alert() se llama tras cada refresco horario (app/main.py::_hourly_refresh);
maybe_send_storm_alert() tras cada ciclo de nowcast de 10 min
(app/main.py::_nowcast_refresh). Ambas comparten `alert_log` como bitácora,
pero cada una deduplica solo contra sus propias filas (`alert_type`,
migración 013) — si compartieran el "último registro sin filtrar", una
alerta de tormenta intercalada haría pensar a maybe_send_alert() que el color
cambió (o viceversa) y reenviaría sin que la condición real haya cambiado.
"""

import logging
from datetime import UTC, datetime, timedelta

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
_STORM_ALERT_TEMPLATE = "alerta_tormenta"
_STORM_EMOJI = "⚡"

_STORM_ALERT_LOCK_KEY = "cienanet_bot:alert_service:maybe_send_storm_alert"
# Dos avisos del mismo sistema en movimiento no deben reenviarse solo porque el
# ETA cambió de 80 a 70 min entre ciclos — comparar por ventana de tiempo
# (mismo sistema si el ciclo anterior fue hace menos de esto), no por ETA exacto.
_STORM_DEDUP_WINDOW = timedelta(hours=2)


async def maybe_send_storm_alert(tormenta: dict | None, db: AsyncSession) -> None:
    """Si hay una tormenta real acercándose (nowcast por rayos), notifica a
    suscritos. `tormenta` es el resultado ya calculado de
    signals.tormenta_aproximandose() (mismo patrón que maybe_send_alert recibe
    el semáforo ya evaluado, no recalcula).

    Dedup por ventana de tiempo, no por ETA exacto: el ETA cambia cada ciclo
    de 10 min aunque sea el mismo sistema acercándose — comparar el valor
    exacto reenviaría con cada refresco.
    """
    if tormenta is None:
        return  # nada que evaluar — ni siquiera vale la pena el advisory lock

    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _STORM_ALERT_LOCK_KEY})

    last = (
        await db.execute(
            select(AlertLog)
            .where(AlertLog.alert_type == "tormenta")
            .order_by(desc(AlertLog.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if last and last.created_at and now - last.created_at < _STORM_DEDUP_WINDOW:
        await db.commit()  # libera el lock; ya se avisó de este mismo sistema recientemente
        return

    eta = tormenta["eta_min"]
    mensaje = (
        f"Tormenta fuerte acercándose desde el {tormenta['rumbo']}, llega en ~{eta} min. "
        "No salgas a pescar ahora y asegura tu embarcación."
    )
    texto = f"{_STORM_EMOJI} {mensaje}"

    recipients = (
        await db.execute(select(User).where(User.alertas_activas.is_(True)))
    ).scalars().all()

    sent_count = 0
    for user in recipients:
        result = await whatsapp_service.send_template_message(
            user.wa_id, _STORM_ALERT_TEMPLATE, params=[mensaje]
        )
        if result:
            sent_count += 1

    db.add(
        ExternalAlert(
            source="goes19-glm",
            alert_type="tormenta",
            title=f"Tormenta acercándose — ETA {eta} min",
            description=mensaje,
        )
    )
    db.add(
        AlertLog(
            alert_type="tormenta",
            color="tormenta",
            zonas=f"eta={eta}min,rumbo={tormenta['rumbo']}",
            canal="whatsapp",
            texto=texto,
            destinatarios_count=sent_count,
        )
    )
    await db.commit()  # libera el lock
    logger.info("Alerta de tormenta (ETA %d min, %s) enviada a %d destinatarios", eta, tormenta["rumbo"], sent_count)
