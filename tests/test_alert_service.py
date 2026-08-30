"""Tests de app/services/alert_service.py — dedup por color/hora y el advisory
lock que serializa llamadas concurrentes (ver docs/DEPLOYMENT.md).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.alert_service import maybe_send_alert, maybe_send_wind_alert


def _result(scalar=None, scalars_all=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


def _make_db(last_alert_color, recipients):
    """1ª llamada a execute() = advisory lock, 2ª = último AlertLog, 3ª = recipients."""
    last = MagicMock(color=last_alert_color) if last_alert_color else None
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(), _result(scalar=last), _result(scalars_all=recipients)]
    )
    db.add = MagicMock()
    return db


def test_maybe_send_alert_adquiere_advisory_lock_primero():
    """El lock debe pedirse ANTES de leer el último AlertLog (serializa el check-then-act)."""
    db = _make_db(last_alert_color="red", recipients=[])

    asyncio.run(maybe_send_alert({"color": "red", "reason": "x"}, db))

    first_call_sql = str(db.execute.call_args_list[0].args[0])
    assert "pg_advisory_xact_lock" in first_call_sql


def test_mismo_color_no_reenvia():
    db = _make_db(last_alert_color="red", recipients=[])

    asyncio.run(maybe_send_alert({"color": "red", "reason": "x"}, db))

    db.add.assert_not_called()
    db.commit.assert_awaited_once()  # libera el lock igual, aunque no haya nada que insertar


def test_verde_a_verde_no_avisa():
    db = _make_db(last_alert_color=None, recipients=[])  # sin alertas previas

    asyncio.run(maybe_send_alert({"color": "green", "reason": "x"}, db))

    db.add.assert_not_called()


def test_cambio_de_color_envia_y_registra():
    user = MagicMock(wa_id="+570000000")
    db = _make_db(last_alert_color="green", recipients=[user])

    with patch(
        "app.services.whatsapp_service.send_template_message",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        asyncio.run(maybe_send_alert({"color": "red", "reason": "Marea roja detectada"}, db))

    mock_send.assert_awaited_once()
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.color == "red"
    assert added.destinatarios_count == 1
    db.commit.assert_awaited_once()


def test_maybe_send_alert_filtra_dedup_por_alert_type_semaforo():
    """Sin este filtro, una fila de alert_log tipo 'vendaval' intercalada haría
    pensar que el color cambió (o al revés) y reenviaría sin motivo real."""
    db = _make_db(last_alert_color="red", recipients=[])

    asyncio.run(maybe_send_alert({"color": "red", "reason": "x"}, db))

    last_alert_query_sql = str(db.execute.call_args_list[1].args[0])
    assert "alert_type" in last_alert_query_sql


_VENDAVAL = {"timestamp": "2026-08-30T14:00", "wind_gust_kmh": 65.0, "umbral_kmh": 62.0, "origen": "medido"}


def _make_wind_db(last_alert_hora, recipients):
    """1ª llamada a execute() = advisory lock, 2ª = último AlertLog tipo vendaval,
    3ª = recipients (mismo orden que _make_db, para maybe_send_wind_alert)."""
    last = MagicMock(zonas=last_alert_hora) if last_alert_hora else None
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(), _result(scalar=last), _result(scalars_all=recipients)]
    )
    db.add = MagicMock()
    return db


def test_vendaval_none_no_consulta_ni_bloquea():
    db = AsyncMock()
    db.execute = AsyncMock()

    asyncio.run(maybe_send_wind_alert(None, db))

    db.execute.assert_not_awaited()


def test_vendaval_misma_hora_no_reenvia():
    db = _make_wind_db(last_alert_hora="2026-08-30T14:00", recipients=[])

    asyncio.run(maybe_send_wind_alert(_VENDAVAL, db))

    db.add.assert_not_called()
    db.commit.assert_awaited_once()


def test_vendaval_hora_nueva_envia_y_registra():
    user = MagicMock(wa_id="+570000000")
    db = _make_wind_db(last_alert_hora="2026-08-30T08:00", recipients=[user])

    with patch(
        "app.services.whatsapp_service.send_template_message",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        asyncio.run(maybe_send_wind_alert(_VENDAVAL, db))

    mock_send.assert_awaited_once()
    assert db.add.call_count == 2  # ExternalAlert + AlertLog

    external_alert, alert_log = (call.args[0] for call in db.add.call_args_list)
    assert external_alert.alert_type == "vendaval"
    assert external_alert.source == "open-meteo"
    assert alert_log.alert_type == "vendaval"
    assert alert_log.zonas == "2026-08-30T14:00"
    assert alert_log.destinatarios_count == 1
    db.commit.assert_awaited_once()


def test_vendaval_sin_alerta_previa_envia():
    user = MagicMock(wa_id="+570000000")
    db = _make_wind_db(last_alert_hora=None, recipients=[user])

    with patch(
        "app.services.whatsapp_service.send_template_message",
        new_callable=AsyncMock,
        return_value=True,
    ):
        asyncio.run(maybe_send_wind_alert(_VENDAVAL, db))

    assert db.add.call_count == 2
