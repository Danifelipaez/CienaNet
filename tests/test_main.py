"""Tests del gate de scheduler (RUN_SCHEDULER) en app.main.lifespan.

RUN_SCHEDULER controla si esta instancia agenda _hourly_refresh() (loop que
refresca el snapshot y evalúa/envía alertas). Debe quedar en False en todos
los deployments salvo el servidor universitario (ver docs/DEPLOYMENT.md).
"""

import asyncio
from unittest.mock import patch

import app.main as main_module


def _run_lifespan_once() -> None:
    async def _drive():
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(_drive())


def test_lifespan_no_agenda_refresh_si_run_scheduler_es_false(monkeypatch):
    monkeypatch.setattr(main_module.settings, "run_scheduler", False)
    with patch("app.main.asyncio.create_task") as mock_create_task:
        _run_lifespan_once()
    mock_create_task.assert_not_called()


def test_lifespan_agenda_refresh_si_run_scheduler_es_true(monkeypatch):
    monkeypatch.setattr(main_module.settings, "run_scheduler", True)
    with patch("app.main.asyncio.create_task") as mock_create_task:
        _run_lifespan_once()
    mock_create_task.assert_called_once()
