"""Envío por WhatsApp de los avisos del tiempo (app/services/avisos.py,
docs/AVISOS_CLIMA.md). Separado de alert_service.py por el límite de tamaño de
docs/GUARDRAILS.md; mismo patrón: advisory lock, dedup contra `alert_log` por tipo,
rastro en `external_alerts`.

Dedup por (`alert_type`, `zonas` = clave del aviso): la clave es el día local del
evento (viento/lluvia/oleaje), la semana (frente frío), el ciclón + su categoría
(sube de tormenta a huracán -> se reenvía) o la temporada + año. Un pronóstico que
aparece, desaparece y vuelve en el mismo día no se reenvía. Para los diarios
(pronóstico e IDEAM) además hay una guarda de 12 h por tipo + prefijo de la clave
(el evento IDEAM, o nada en los de pronóstico): un evento que cruza la medianoche
cambia de clave (día) y sin la guarda se reenviaría a las pocas horas.

Varios avisos nuevos en el mismo ciclo van en UN solo mensaje por pescador.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environmental import ExternalAlert
from app.models.messaging import AlertLog, User
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

# ponytail: template genérico de un parámetro, igual que los de alert_service.py —
# crear y aprobar `aviso_clima` en Meta Business Manager antes de usar provider "meta".
_TEMPLATE = "aviso_clima"
_LOCK_KEY = "cienanet_bot:avisos_push:maybe_send_avisos"
_DEDUP = timedelta(days=4)
_DEDUP_TEMPORADA = timedelta(days=60)
_GUARDA = timedelta(hours=12)
_TIPOS_DIARIOS = ("viento_fuerte", "lluvia_fuerte", "oleaje", "ideam_mar", "ideam_cuenca")
# ponytail: pescadores a los que les falló el envío de un aviso ya registrado (wa_id ->
# [(cuándo falló, texto)]). Se reintenta una vez por ciclo hasta _REINTENTO_MAX: después
# el aviso ya es viejo ("viento hoy en la madrugada" leído al día siguiente engaña).
# En memoria de proceso, un reinicio los pierde.
_reintentos: dict[str, list[tuple[datetime, str]]] = {}
_REINTENTO_MAX = timedelta(hours=6)
# Meta limita el cuerpo del template a 1024 caracteres (texto fijo + parámetro).
_MAX_TEXTO = 900
_CORTE = " … Escribe *avisos* para ver el resto."


def _acotar(texto: str) -> str:
    return texto if len(texto) <= _MAX_TEXTO else texto[: _MAX_TEXTO - len(_CORTE)].rstrip() + _CORTE


async def _reintentar_fallidos(db: AsyncSession) -> None:
    limite = datetime.now(UTC) - _REINTENTO_MAX
    for wa_id in list(_reintentos):
        _reintentos[wa_id] = [(t, x) for t, x in _reintentos[wa_id] if t >= limite]
        if not _reintentos[wa_id]:
            del _reintentos[wa_id]
    if not _reintentos:
        return
    # Quien se dio de baja entre ciclos ya no recibe el reintento.
    activos = set(
        (
            await db.execute(
                select(User.wa_id).where(User.wa_id.in_(list(_reintentos)), User.alertas_activas.is_(True))
            )
        ).scalars().all()
    )
    for wa_id, pendientes in list(_reintentos.items()):
        texto = _acotar(" ".join(x for _, x in pendientes))
        if wa_id not in activos or await whatsapp_service.send_template_message(wa_id, _TEMPLATE, params=[texto]):
            del _reintentos[wa_id]


async def maybe_send_avisos(avisos: dict | None, db: AsyncSession) -> int:
    """Empuja los avisos `push` que no se hayan enviado ya. Devuelve cuántos avisos
    nuevos salieron. Si TODOS los envíos fallan no se registra nada: el próximo
    refresco horario lo reintenta mientras el aviso siga vigente."""
    await _reintentar_fallidos(db)
    pendientes = [a for a in (avisos or {}).get("vigentes", []) if a.get("push")]
    if not pendientes:
        return 0  # ni siquiera vale la pena el advisory lock

    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _LOCK_KEY})
    ahora = datetime.now(UTC)
    nuevos = []
    for a in pendientes:
        ventana = _DEDUP_TEMPORADA if a["tipo"] == "temporada" else _DEDUP
        misma = (AlertLog.zonas == a["clave"]) & (AlertLog.created_at >= ahora - ventana)
        if a["tipo"] in _TIPOS_DIARIOS:
            # "Tiempo lluvioso:2026-10-31" -> "Tiempo lluvioso:"; "2026-10-31" -> "" (todo el tipo).
            prefijo = a["clave"].rpartition(":")[0] + ":" if ":" in a["clave"] else ""
            reciente = AlertLog.created_at >= ahora - _GUARDA
            misma = misma | (reciente & AlertLog.zonas.startswith(prefijo, autoescape=True) if prefijo else reciente)
        ya = (
            await db.execute(select(AlertLog.id).where(AlertLog.alert_type == a["tipo"], misma).limit(1))
        ).scalar_one_or_none()
        if ya is None:
            nuevos.append(a)
    if not nuevos:
        await db.commit()  # libera el lock
        return 0

    # Espacio, no salto de línea: Meta rechaza parámetros de template con saltos de línea.
    texto = _acotar(" ".join(a["mensaje"] for a in nuevos))
    recipients = (await db.execute(select(User).where(User.alertas_activas.is_(True)))).scalars().all()
    sent_count = 0
    fallidos = []
    for user in recipients:
        if await whatsapp_service.send_template_message(user.wa_id, _TEMPLATE, params=[texto]):
            sent_count += 1
        else:
            fallidos.append(user.wa_id)

    if recipients and sent_count == 0:
        await db.commit()  # libera el lock sin registrar: se reintenta el próximo ciclo
        logger.error(
            "Avisos del tiempo (%s): 0 de %d envíos de WhatsApp OK — se reintenta en el próximo refresco",
            ", ".join(a["tipo"] for a in nuevos),
            len(recipients),
        )
        return 0
    # Envío parcial: el aviso queda registrado (los que sí lo recibieron no deben recibirlo
    # dos veces) y a los que fallaron se les reintenta en los próximos ciclos.
    for wa_id in fallidos:
        _reintentos.setdefault(wa_id, []).append((ahora, texto))

    for a in nuevos:
        db.add(ExternalAlert(source=a["fuente"][:50], alert_type=a["tipo"], title=a["titulo"], description=a["mensaje"]))
        db.add(
            AlertLog(
                alert_type=a["tipo"],
                color="aviso",
                zonas=a["clave"],
                canal="whatsapp",
                texto=a["mensaje"],
                destinatarios_count=sent_count,
            )
        )
    await db.commit()  # libera el lock
    logger.info(
        "Avisos del tiempo (%s) enviados a %d de %d destinatarios",
        ", ".join(a["tipo"] for a in nuevos),
        sent_count,
        len(recipients),
    )
    return len(nuevos)
