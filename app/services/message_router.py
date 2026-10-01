"""Enruta mensajes entrantes de WhatsApp: clasifica intención y responde.

Intenciones cubiertas (keyword matching — ponytail: suficiente para el MVP,
subir a NLU/IA real si el volumen de mensajes no reconocidos crece):
saludo, consulta de condición, suscripción/baja de alertas, reporte de
captura. Todo lo demás cae al AIProvider (stub hasta que se conecte uno real).
"""

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.messaging import CatchReport, Conversation, User
from app.services import whatsapp_service
from app.services.ai_context import (
    SEGURIDAD_PROMPT,
    alerta_ideam_prompt,
    build_ai_context,
    camaron_moonrise_corto,
    camaron_moonrise_hint,
)
from app.services.ai_service import get_ai_provider
from app.services.condicion_message import _COBERTURA_MINIMA, _mensaje_condicion
from app.services.ingestion.ideam_comunicados import get_alerta_ideam
from app.services.ingestion.weather import get_convective_forecast
from app.services.points_service import get_points
from app.services.signals import vendaval_risk
from app.services.snapshot_service import read_persisted

logger = logging.getLogger(__name__)

# Palabra clave (subcadena, así también cubre plurales: "jaibas", "camarones") -> etiqueta.
_ESPECIES = {
    "camarón": "camarón", "camaron": "camarón", "lisa": "lisa", "mojarra": "mojarra",
    "róbalo": "róbalo", "robalo": "róbalo", "jaiba": "jaiba", "ostra": "ostra",
    "chivo": "chivo", "lebranche": "lebranche", "sábalo": "sábalo", "sabalo": "sábalo",
    "bocachico": "bocachico",
}  # fmt: skip

_SALUDO = (
    "¡Hola! Soy CienaRed 🐟, uniendo la información científica de los sensores con "
    "el saber ancestral de los pescadores de la ciénaga. Puedo contarte cómo está "
    "el agua hoy, dónde pescar, suscribirte a alertas, o recibir tu reporte de pesca.\n\n"
    "{alerta}"
    "Escribe *condición*, *dónde pesco*, *alertas* o cuéntame qué pescaste."
)
_NO_ENTENDI = (
    "No entendí tu mensaje. Escribe *condición* para saber cómo está el agua, "
    "*dónde pesco* para ver las mejores zonas, o *alertas* para suscribirte."
)
_DE_NADA = "¡Con gusto, compa! 🐟 Cuando quieras escribe *condición*, *dónde pesco* o *alertas*."
# Las responde webhook.py: un error o un audio no deben dejar al pescador en visto.
FALLA = "Uy, compa, se me enredó la red 🎣. Inténtalo de nuevo en un momento."
SOLO_TEXTO = "Por ahora solo leo mensajes de texto ✍️. Escríbeme *condición*, *dónde pesco* o *alertas*."

# Gemini cobra por token: un mensaje de 2000 caracteres no es una pregunta de pesca.
_MAX_TEXTO_IA = 1000

# Primera palabra de un mensaje corto que es solo saludo o pedido de menú.
_SALUDOS = {
    "hola", "holi", "buenas", "buenos", "buen", "hi", "hello", "start", "epa", "quiubo",
    "menu", "menú", "ayuda", "opciones", "inicio",
}  # fmt: skip
_CORTESIAS = {"gracias", "ok", "okey", "okay", "listo", "dale", "vale", "perfecto", "chévere", "chevere", "bueno"}

# Todo con \b: "no" suelto, no el "no" de "noche"; "qué" suelto, no el de "pesqué".
_PREGUNTA_RE = re.compile(
    r"[?¿]|\b(dónde|donde|cuándo|cuando|cómo|qué|cuál|cuáles|cuánto|cuánta|cuántos|cuántas|"
    r"hay|estará|estarán|estaran|va a|van a|puedo|debo)\b|^\s*(como|que|cual)\b"
)
_BAJA_RE = re.compile(r"\b(no|desactiv\w*|baja|cancel\w*|quita\w*|parar|stop)\b")
_NEGACION_RE = re.compile(r"\b(no|nada|ni)\b")
_AGUA_RE = re.compile(r"\bagua\b")  # no "aguacero" ni "aguaje"
# Pasado o futuro: "condición" es la foto de hoy; el resto lo responde la IA (con tools).
_NO_ES_HOY_RE = re.compile(r"\b(ayer|mañana|pasad[oa]s?|estuvo|estaba|estará|anterior|hist[oó]ric[oa])\b")


async def _get_or_create_user(wa_id: str, nombre: str | None, db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.wa_id == wa_id))).scalar_one_or_none()
    if user:
        user.last_message_at = datetime.now(UTC)
        if nombre and not user.nombre:
            user.nombre = nombre
    else:
        user = User(wa_id=wa_id, nombre=nombre, last_message_at=datetime.now(UTC))
        db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _log_message(
    user_id, direction: str, body: str, db: AsyncSession, wa_message_id: str | None = None
) -> None:
    db.add(Conversation(user_id=user_id, direction=direction, body=body, wa_message_id=wa_message_id))
    await db.commit()


def _linea_alerta(alerta: dict | None) -> str:
    """'⚠️ Alerta IDEAM: ...' con salto de párrafo, o vacío si no hay comunicado vigente."""
    return f"⚠️ Alerta IDEAM: {alerta['resumen']}.\n\n" if alerta else ""


async def _linea_alerta_ideam() -> str:
    return _linea_alerta(await get_alerta_ideam())


def _es_condicion(text_lower: str) -> bool:
    return bool("condici" in text_lower or _AGUA_RE.search(text_lower)) and not _NO_ES_HOY_RE.search(text_lower)


def _es_saludo(palabras: list[str]) -> bool:
    return len(palabras) <= 3 and bool(palabras) and palabras[0] in _SALUDOS


def _es_cortesia(palabras: list[str]) -> bool:
    """'gracias', 'ok', 'listo'... o solo emojis (👍) — sin palabras."""
    return not palabras or (len(palabras) <= 4 and palabras[0] in _CORTESIAS)


def _formato_whatsapp(texto: str) -> str:
    """Gemini a veces responde en Markdown, que WhatsApp muestra literal (**, ###)."""
    texto = texto.replace("**", "*")
    texto = re.sub(r"^#+\s*", "", texto, flags=re.M)
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


async def _condicion_actual(db: AsyncSession) -> str:
    estado = await read_persisted(db)
    alerta = await get_alerta_ideam()
    return f"{_mensaje_condicion(estado, alerta is not None)}\n\n{_linea_alerta(alerta)}".rstrip()


_DONDE_MARKERS = (
    "dónde pesc", "donde pesc", "dónde hay", "donde hay", "a dónde", "a donde",
    "qué zona", "que zona", "mejor zona", "dónde tiro", "donde tiro",
)
_SIN_ZONAS = "Todavía no tengo suficientes datos para recomendarte una zona. Escribe *condición* para ver cómo está el agua."


def _es_donde_pesco(text_lower: str) -> bool:
    return any(m in text_lower for m in _DONDE_MARKERS)


async def _donde_pesco(db: AsyncSession, text_lower: str) -> str:
    """Top 3 puntos de pesca por IPP. Nombres de punto ('Boquerón', 'La Ahuyama'),
    no de zona ('Suroccidente') — es el vocabulario que los pescadores ya usan.
    Sin fishing_points sembrados, cae a las 6 zonas del ranking IPP.

    Si se nombra una especie, filtra por fishing_points.especies (saber
    comunitario sembrado). Con cobertura de sensores baja el IPP empata en todos
    los puntos (sale en orden alfabético) — en vez de presentar eso como "las
    mejores zonas", se dice la verdad, igual que "condición" (_frase_donde).
    """
    especie = _detect_especie(text_lower)
    puntos = await get_points(db)
    if puntos:
        con_especie = [p for p in puntos if especie in (p.get("especies") or [])] if especie else []
        candidatos = con_especie or puntos  # nadie la lista -> se ignora el filtro
        cobertura = candidatos[0].get("cobertura", 1.0)
        nombres = [p["nombre"] for p in candidatos[:3]]
    else:
        ranking = (await read_persisted(db)).get("ipp_ranking") or []
        con_especie = []
        cobertura = ranking[0].get("cobertura", 1.0) if ranking else 1.0
        nombres = [z["zone"] for z in ranking[:3]]

    if not nombres:
        return _SIN_ZONAS

    if cobertura >= _COBERTURA_MINIMA:
        para = f" para {especie}" if con_especie else ""
        reply = f"Las mejores zonas hoy{para} son: {', '.join(nombres)}."
    elif con_especie:
        reply = (
            "Hoy los sensores del agua no están reportando, así que no puedo comparar zonas "
            f"con datos. Según los pescadores, donde se suele sacar {especie} es en: {', '.join(nombres)}."
        )
    else:
        reply = (
            "Hoy los sensores del agua no están reportando, así que no puedo decirte con datos "
            "qué zona está mejor. Pregúntame por una especie (ej. *dónde hay lisa*) y te digo "
            "dónde se suele sacar."
        )
    if especie == "camarón":
        reply += f"\n\n{camaron_moonrise_corto()}"
    return reply


_CANTIDAD_RE = re.compile(r"\b(\d{1,4})\b")  # ponytail: primer número del mensaje;
# no distingue unidad (libras/kg/unidades) ni descarta números que no son cantidad
# ("pesqué en el caño 3"). Sube a botones con rangos si el ruido molesta — además
# normalizaría la unidad, que hoy nadie declara.


def _cantidad_reportada(text: str) -> float | None:
    match = _CANTIDAD_RE.search(text)
    return float(match.group(1)) if match else None


async def _recent_history(user_id, db: AsyncSession) -> list[dict]:
    """Últimos mensajes de la conversación como contexto para Gemini (orden cronológico).

    Mapea direction 'in'→'user', 'out'→'model' (roles de la API de Gemini).
    Excluye el mensaje actual, que el caller ya agrega aparte.
    """
    rows = (
        await db.execute(
            select(Conversation.direction, Conversation.body)
            .where(Conversation.user_id == user_id, Conversation.body.isnot(None))
            .order_by(desc(Conversation.created_at))
            .limit(settings.ai_history_turns + 1)
        )
    ).all()
    history = [
        {"role": "user" if d == "in" else "model", "parts": [{"text": b}]}
        for d, b in reversed(rows)
    ]
    return history[:-1]  # quita el mensaje actual (el más reciente)


def _detect_especie(text_lower: str) -> str | None:
    for keyword, label in _ESPECIES.items():
        if keyword in text_lower:
            return label
    return None


def _es_pregunta(text_lower: str) -> bool:
    """Distingue una pregunta ('¿dónde hay camarón?', 'cómo está la pesca de
    camarón') de un reporte de captura ('hoy pesqué camarón') — ambos matchean
    _detect_especie por igual."""
    return bool(_PREGUNTA_RE.search(text_lower))


def _intencion(text_lower: str) -> str:
    """Clasifica el mensaje: 'saludo' | 'condicion' | 'baja' | 'suscribe' | 'donde'
    | 'cortesia' | 'captura' | 'ia'. Pura, para poder probar el enrutamiento sin DB.

    Orden: intenciones concretas primero, saludo/cortesía después — así "hola,
    ¿dónde pesco?" va a dónde pesco y no al menú.
    """
    palabras = re.findall(r"\w+", text_lower)
    es_pregunta = _es_pregunta(text_lower)
    # Preguntas ('¿hay alguna alerta del IDEAM?', '¿no hay alertas?') van a la IA:
    # antes suscribían o daban de baja a quien solo estaba preguntando.
    comando_alerta = "alerta" in text_lower and not es_pregunta

    if not text_lower:
        return "saludo"
    if _es_condicion(text_lower):
        return "condicion"
    if comando_alerta:
        return "baja" if _BAJA_RE.search(text_lower) else "suscribe"
    if _es_donde_pesco(text_lower):
        return "donde"
    if _es_saludo(palabras):
        return "saludo"
    if _es_cortesia(palabras):
        return "cortesia"
    # "hoy no saqué nada de camarón" no es captura
    if _detect_especie(text_lower) and not es_pregunta and not _NEGACION_RE.search(text_lower):
        return "captura"
    return "ia"


async def handle_incoming_text(
    wa_id: str, nombre: str | None, text: str, wa_message_id: str, db: AsyncSession
) -> None:
    """Procesa un mensaje de texto entrante y envía la respuesta correspondiente."""
    user = await _get_or_create_user(wa_id, nombre, db)
    await _log_message(user.id, "in", text, db, wa_message_id)

    text_lower = text.strip().lower()
    intencion = _intencion(text_lower)

    if intencion == "saludo":
        reply = _SALUDO.format(alerta=await _linea_alerta_ideam())
    elif intencion == "condicion":
        reply = await _condicion_actual(db)
    elif intencion == "baja":
        user.alertas_activas = False
        await db.commit()
        reply = "Listo, ya no recibirás alertas automáticas."
    elif intencion == "suscribe":
        user.alertas_activas = True
        await db.commit()
        reply = "Listo, quedaste suscrito a alertas. Escribe *alertas no* para darte de baja."
    elif intencion == "donde":
        reply = await _donde_pesco(db, text_lower)
    elif intencion == "cortesia":
        reply = _DE_NADA
    elif intencion == "captura":
        especie = _detect_especie(text_lower)
        cantidad = _cantidad_reportada(text)
        db.add(
            CatchReport(
                user_id=user.id, especie=especie, cantidad_indice=cantidad, timestamp=datetime.now(UTC)
            )
        )
        await db.commit()
        reply = f"Gracias por reportar tu pesca de {especie} 🎣. Esto ayuda a toda la comunidad."
    else:
        # ponytail: llamada a Gemini inline (Vercel serverless no tiene background
        # tasks confiables). Mover a cola solo si la latencia molesta.
        estado = await read_persisted(db)
        vendaval = vendaval_risk(await get_convective_forecast(), settings.vendaval_gust_threshold_kmh)
        system = (
            "Eres 'El Compa', el asistente de CienaRed para pescadores artesanales "
            "de la Ciénaga Grande de Santa Marta. Si preguntan qué es CienaRed o qué haces: "
            "CienaRed une datos de sensores de bajo costo en el agua (pH, salinidad, "
            "temperatura), satélites, el clima y los comunicados del IDEAM con el saber de "
            "los pescadores, y los entrega por WhatsApp porque es el canal que ya usan; "
            "puedes contar cómo está el agua hoy (*condición*), dónde se suele pescar cada "
            "especie (*dónde pesco*), avisar con *alertas* y recibir reportes de pesca "
            "('hoy saqué 15 libras de lisa'). Hablas como un pescador experimentado "
            "y respetado de la región Caribe: sabio, cercano, de trato fino y con la "
            "cadencia natural del habla costeña. Puedes usar términos del oficio cuando "
            "vengan al caso (faena, bajamar, caleta, mar picada, cardumen) y vocativos "
            "de respeto con moderación ('compa', 'compadre', 'mire', 'vea'). Nunca caigas "
            "en caricatura: sin deformaciones fonéticas forzadas (nunca 'ej que', 'pa' ni "
            "'pa'', escribe 'para') ni modismos urbanos o de otras regiones. Trata el "
            "oficio de la pesca con seriedad y dignidad, nunca de forma infantil o "
            "condescendiente — quien te escribe está en faena o alistándose para salir. "
            "Responde siempre en español (aunque te escriban en otro idioma), en máximo 4 "
            "oraciones y sin jerga técnica. Si hablan del tiempo, del agua o de salir a "
            "pescar, termina con una recomendación concreta que salga de estos datos; si es "
            "un saludo, un agradecimiento, una charla o un tema ajeno a la ciénaga, responde "
            "en 1 o 2 frases y ofrece lo que puedes hacer (*condición*, *dónde pesco*, "
            "*alertas*), sin inventar consejos. Las preguntas de ciencia de la ciénaga "
            "(clorofila, salinidad, pH, oxígeno, manglar, especies) SÍ son tu tema: "
            "explícalas sencillo, con el dato actual si lo tienes. No digas por tu cuenta "
            "que una zona está mejor o tiene 'buenas señales': para recomendar zonas remite "
            "a *dónde pesco*. Formato WhatsApp: texto plano, sin listas ni "
            "títulos; para resaltar usa un solo asterisco (*así*). Redondea los números a "
            "máximo un decimal con coma decimal (30,1 °C; 67,8 mg/m³). Usa estos datos del "
            "presente, no inventes valores: "
            f"{build_ai_context(estado, vendaval)} Si la pregunta es sobre el pasado (histórico) "
            "o necesitas un dato que no está aquí, usa las herramientas disponibles en "
            "vez de inventar."
            f"{alerta_ideam_prompt(await get_alerta_ideam())} Menciona la alerta solo si "
            "te preguntan por el estado de la ciénaga, el tiempo o las condiciones de "
            "los próximos días. Si preguntan por suscribirse o darse de baja de las "
            "alertas de CienaRed, diles que escriban *alertas* para suscribirse o "
            "*alertas no* para darse de baja (tú no puedes hacerlo por ellos)."
        )
        if "camar" in text_lower:
            system += f"\n{camaron_moonrise_hint()}"
        system += (
            f"{SEGURIDAD_PROMPT} En ese caso responde solo esas 2 frases, con la voz de "
            "El Compa, sin el formato de 2 a 4 oraciones ni la recomendación final."
        )
        ai_reply = await get_ai_provider().reply_text(
            system=system,
            user=text[:_MAX_TEXTO_IA],
            history=await _recent_history(user.id, db),
            db=db,
        )
        reply = _formato_whatsapp(ai_reply) if ai_reply else _NO_ENTENDI

    sent = await whatsapp_service.send_text_message(wa_id, reply)
    sent_id = (sent or {}).get("messages", [{}])[0].get("id") if sent else None
    await _log_message(user.id, "out", reply, db, wa_message_id=sent_id)
