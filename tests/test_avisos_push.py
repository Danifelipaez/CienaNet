"""Tests de app/services/avisos_push.py — lock, dedup por clave, un mensaje por
pescador aunque haya varios avisos, y reintento si todos los envíos fallan."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.avisos_push import maybe_send_avisos


def _aviso(tipo="viento_fuerte", clave="2026-11-02", push=True):
    return {"tipo": tipo, "clave": clave, "push": push, "mensaje": f"msg {tipo}", "titulo": tipo, "fuente": "f"}


def _result(scalar=None, scalars_all=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    if scalars_all is not None:
        r.scalars.return_value.all.return_value = scalars_all
    return r


def _db(ya_enviados: list, recipients: list):
    """execute(): lock, un SELECT de dedup por aviso pendiente, y recipients (si hay nuevos)."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[MagicMock(), *[_result(scalar=x) for x in ya_enviados], _result(scalars_all=recipients)]
    )
    db.add = MagicMock()
    return db


def _send(ok=True):
    return patch(
        "app.services.whatsapp_service.send_template_message", new_callable=AsyncMock, return_value=ok
    )


def test_sin_avisos_push_no_toca_la_db():
    db = AsyncMock()
    assert asyncio.run(maybe_send_avisos({"vigentes": [_aviso(push=False)]}, db)) == 0
    assert asyncio.run(maybe_send_avisos(None, db)) == 0
    db.execute.assert_not_called()


def test_lock_primero_y_un_solo_mensaje_por_pescador():
    users = [MagicMock(wa_id="+571"), MagicMock(wa_id="+572")]
    db = _db([None, None], users)
    with _send() as send:
        n = asyncio.run(maybe_send_avisos({"vigentes": [_aviso(), _aviso("oleaje")]}, db))
    assert n == 2
    assert "pg_advisory_xact_lock" in str(db.execute.call_args_list[0].args[0])
    assert send.await_count == 2  # uno por pescador, no uno por aviso
    texto = send.await_args.kwargs["params"][0]
    assert "msg viento_fuerte" in texto and "msg oleaje" in texto and "\n" not in texto
    logs = [c.args[0] for c in db.add.call_args_list if c.args[0].__class__.__name__ == "AlertLog"]
    assert {(log.alert_type, log.zonas, log.destinatarios_count) for log in logs} == {
        ("viento_fuerte", "2026-11-02", 2), ("oleaje", "2026-11-02", 2)
    }
    db.commit.assert_awaited_once()


def test_ya_enviado_no_se_repite():
    db = _db(["id-previo"], [])
    with _send() as send:
        assert asyncio.run(maybe_send_avisos({"vigentes": [_aviso()]}, db)) == 0
    send.assert_not_awaited()
    db.add.assert_not_called()
    db.commit.assert_awaited_once()  # libera el lock igual


def test_dedup_de_ideam_mira_el_mismo_evento():
    db = _db([None], [])
    asyncio.run(maybe_send_avisos({"vigentes": [_aviso("ideam_mar", "Tiempo lluvioso:2026-11-02")]}, db))
    sql = str(db.execute.call_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "Tiempo lluvioso:" in sql  # guarda de 12 h solo contra el mismo evento IDEAM


def test_si_todos_los_envios_fallan_no_registra_y_reintenta():
    db = _db([None], [MagicMock(wa_id="+571")])
    with _send(ok=None):
        assert asyncio.run(maybe_send_avisos({"vigentes": [_aviso()]}, db)) == 0
    db.add.assert_not_called()
    db.commit.assert_awaited_once()
