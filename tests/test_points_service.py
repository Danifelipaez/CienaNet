"""Tests de app/services/points_service.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.points_service import get_points


def _make_db():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result
    return db


def test_sin_semaphore_persistido_asume_verde():
    """Sin DailySemaphore persistido, la vista Mapa necesita un color por punto para
    pintarse — se asume 'green' en vez de propagar el None de read_persisted."""
    db = _make_db()
    estado = {"semaphore": {"color": None}, "water": {}, "satellite": {}, "weather": {}}
    with (
        patch("app.services.points_service.read_persisted", new_callable=AsyncMock, return_value=estado),
        patch("app.services.points_service.rank_points", return_value=[]) as mock_rank,
    ):
        asyncio.run(get_points(db))
    assert mock_rank.call_args.args[3] == "green"


def test_propaga_el_color_del_semaforo_persistido():
    db = _make_db()
    estado = {"semaphore": {"color": "red"}, "water": {}, "satellite": {}, "weather": {}}
    with (
        patch("app.services.points_service.read_persisted", new_callable=AsyncMock, return_value=estado),
        patch("app.services.points_service.rank_points", return_value=[]) as mock_rank,
    ):
        asyncio.run(get_points(db))
    assert mock_rank.call_args.args[3] == "red"
