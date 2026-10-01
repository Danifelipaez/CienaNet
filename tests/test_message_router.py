"""Tests de message_router.py — el cerebro del bot de WhatsApp (antes sin tests)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.messaging import CatchReport, User
from app.services.message_router import _intencion, handle_incoming_text


def _estado(**overrides):
    base = {
        "semaphore": {"color": "green", "reason": "Condiciones favorables"},
        "weather": {"wind_speed_kmh": 10, "wind_gust_kmh": 15, "precipitation_mm": 0},
        "water": {"salinity_psu": 18, "ph": 7.6},
        "ipp_ranking": [
            {"zone": "Tasajera/Puebloviejo", "ipp": 90.0, "cobertura": 1.0},
            {"zone": "Nueva Venecia", "ipp": 70.0, "cobertura": 1.0},
        ],
        "edad_horas": {"weather": 0.5, "satellite": 48.0, "water": 1.0},
    }
    base.update(overrides)
    return base


# ── enrutamiento: DB y whatsapp_service mockeados ───────────────────────────────


def _make_db():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # siempre crea usuario nuevo
    result.all.return_value = []  # _recent_history usa execute(...).all() directo
    result.scalars.return_value.all.return_value = []  # get_latest_readings / FishingPoint query
    db = AsyncMock()
    db.execute.return_value = result
    db.add = MagicMock()
    return db


def test_saludo():
    db = _make_db()
    with patch(
        "app.services.message_router.whatsapp_service.send_text_message",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_send:
        asyncio.run(handle_incoming_text("+570000000", "Ana", "hola", "wamid.in", db))
    reply = mock_send.call_args.args[1]
    assert "CienaRed" in reply


def test_condicion_no_llama_get_latest_snapshot():
    """Anti-regresión: la rama 'condición' debe leer lo persistido (read_persisted),
    no volver a disparar get_latest_snapshot() (APIs externas + 4 escrituras)."""
    db = _make_db()
    estado = _estado()
    with (
        patch(
            "app.services.message_router.read_persisted", new_callable=AsyncMock, return_value=estado
        ) as mock_read,
        patch(
            "app.services.message_router.whatsapp_service.send_text_message",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "cómo está el agua", "wamid.in", db))

    mock_read.assert_awaited_once()
    assert db.execute.call_count == 1  # solo _get_or_create_user — nada de I/O de snapshot
    reply = mock_send.call_args.args[1]
    assert estado["semaphore"]["reason"] in reply


def test_alertas_baja_desactiva():
    db = _make_db()
    with patch(
        "app.services.message_router.whatsapp_service.send_text_message",
        new_callable=AsyncMock,
        return_value=None,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "alertas no", "wamid.in", db))
    user_added = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], User))
    assert user_added.alertas_activas is False


def test_alertas_suscribe():
    db = _make_db()
    with patch(
        "app.services.message_router.whatsapp_service.send_text_message",
        new_callable=AsyncMock,
        return_value=None,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "alertas", "wamid.in", db))
    user_added = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], User))
    assert user_added.alertas_activas is True


def test_pregunta_por_alertas_va_a_la_ia_sin_tocar_suscripcion():
    """Anti-regresión: '¿hay alguna alerta del IDEAM?' suscribía al usuario y
    '¿no hay alertas?' lo daba de baja, en vez de responderle."""
    for pregunta in ("¿Hay alguna alerta del IDEAM?", "¿no hay alertas?"):
        db = _make_db()
        provider = MagicMock()
        provider.reply_text = AsyncMock(return_value="respuesta IA")
        with (
            patch("app.services.message_router.read_persisted", new_callable=AsyncMock, return_value=_estado()),
            patch("app.services.message_router.build_ai_context", return_value=""),
            patch("app.services.message_router.get_convective_forecast", new_callable=AsyncMock, return_value={}),
            patch("app.services.message_router.get_ai_provider", return_value=provider),
            patch(
                "app.services.message_router.whatsapp_service.send_text_message",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_send,
        ):
            asyncio.run(handle_incoming_text("+570000000", "Ana", pregunta, "wamid.in", db))
        user_added = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], User))
        assert user_added.alertas_activas is None  # sin tocar
        assert mock_send.call_args.args[1] == "respuesta IA"


def test_reporte_captura_guarda():
    db = _make_db()
    with patch(
        "app.services.message_router.whatsapp_service.send_text_message",
        new_callable=AsyncMock,
        return_value=None,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "hoy pesqué camarón", "wamid.in", db))
    reporte = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], CatchReport))
    assert reporte.especie == "camarón"
    assert reporte.cantidad_indice is None  # sin número en el texto, no se inventa


def test_donde_pesco_devuelve_puntos_ordenados_por_ipp():
    db = _make_db()
    puntos = [
        {"nombre": "Boquerón", "ipp": 91.0},
        {"nombre": "La Ahuyama", "ipp": 85.0},
        {"nombre": "Santa Rosa", "ipp": 40.0},
        {"nombre": "Flamenquito", "ipp": 20.0},
    ]
    with (
        patch("app.services.message_router.get_points", new_callable=AsyncMock, return_value=puntos),
        patch(
            "app.services.message_router.whatsapp_service.send_text_message",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "¿dónde pesco hoy?", "wamid.in", db))
    reply = mock_send.call_args.args[1]
    assert "Boquerón" in reply and "La Ahuyama" in reply and "Santa Rosa" in reply
    assert "Flamenquito" not in reply  # solo top 3


def test_donde_hay_camaron_enruta_a_donde_pesco_no_a_captura():
    """Regresión de orden de ramas: '¿dónde hay camarón?' matchea _detect_especie
    a la vez que es claramente una pregunta — debe ir a la recomendación de zonas
    (con el conocimiento tradicional de luna anexado), nunca registrarse como
    reporte de captura."""
    db = _make_db()
    puntos = [{"nombre": "Boquerón", "ipp": 91.0}]
    with (
        patch("app.services.message_router.get_points", new_callable=AsyncMock, return_value=puntos),
        patch(
            "app.services.message_router.whatsapp_service.send_text_message",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "¿dónde hay camarón?", "wamid.in", db))
    assert not any(isinstance(c.args[0], CatchReport) for c in db.add.call_args_list)
    reply = mock_send.call_args.args[1]
    assert "Boquerón" in reply
    assert "luna" in reply.lower()


def test_reporte_con_cantidad_guarda_indice():
    db = _make_db()
    with patch(
        "app.services.message_router.whatsapp_service.send_text_message",
        new_callable=AsyncMock,
        return_value=None,
    ):
        asyncio.run(
            handle_incoming_text("+570000000", "Ana", "hoy pesqué 15 libras de lisa", "wamid.in", db)
        )
    reporte = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], CatchReport))
    assert reporte.cantidad_indice == 15.0


# ── clasificación de intención: casos reales que fallaron en la prueba de la demo ──


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("quiero alertas en la noche", "suscribe"),  # "noche" contiene "no"
        ("alertas no", "baja"),
        ("desactivar alertas", "baja"),
        ("quiero alertas para la noche", "suscribe"),  # "para" no es "parar"
        ("¿no hay alertas?", "ia"),
        ("¿va a caer aguacero?", "ia"),  # "aguacero" contiene "agua"
        ("¿cómo estuvo el agua la semana pasada?", "ia"),  # histórico -> IA con tools
        ("¿cómo está el agua?", "condicion"),
        ("Hola, ¿cómo está el agua hoy?", "condicion"),
        ("hoy no pesqué nada de camarón", "ia"),  # negación: no es captura
        ("cómo está la pesca de camarón", "ia"),  # pregunta sin "?"
        ("como esta la pesca de lisa", "ia"),
        ("hoy pesqué 15 libras de lisa", "captura"),
        ("saqué lisa como 20 libras", "captura"),  # "como" en medio no es pregunta
        ("saqué 30 jaibas", "captura"),
        ("Hola!", "saludo"),
        ("Buenos días", "saludo"),
        ("hola compa", "saludo"),
        ("Hola 👋", "saludo"),
        ("menú", "saludo"),
        ("   ", "saludo"),
        ("hola, ¿dónde pesco?", "donde"),
        ("gracias compa", "cortesia"),
        ("👍", "cortesia"),
    ],
)
def test_intencion(texto, esperado):
    assert _intencion(texto.strip().lower()) == esperado


def test_donde_pesco_sin_sensores_no_inventa_ranking():
    """Con cobertura baja todos los puntos empatan en IPP (orden alfabético):
    no presentarlo como 'las mejores zonas'; con especie, usar el saber comunitario."""
    db = _make_db()
    puntos = [
        {"nombre": "Boca del Pájaro", "ipp": 100.0, "cobertura": 0.23, "especies": ["camarón"]},
        {"nombre": "Boquerón", "ipp": 100.0, "cobertura": 0.23, "especies": ["lisa"]},
    ]
    with (
        patch("app.services.message_router.get_points", new_callable=AsyncMock, return_value=puntos),
        patch(
            "app.services.message_router.whatsapp_service.send_text_message",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_send,
    ):
        asyncio.run(handle_incoming_text("+570000000", "Ana", "dónde pesco", "wamid.in", db))
        general = mock_send.call_args.args[1]
        asyncio.run(handle_incoming_text("+570000000", "Ana", "¿dónde hay camarón?", "wamid.in2", db))
        camaron = mock_send.call_args.args[1]
    assert "mejores zonas" not in general and "sensores" in general
    assert "Boca del Pájaro" in camaron and "Boquerón" not in camaron
