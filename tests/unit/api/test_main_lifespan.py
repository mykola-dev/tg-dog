from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def _set_required_env() -> None:
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "telegram_digest")
    os.environ.setdefault("POSTGRES_USER", "telegram_digest")
    os.environ.setdefault("POSTGRES_PASSWORD", "telegram_digest")
    os.environ.setdefault("WORKSPACE_PATH", "/tmp/api_test_workspace")
    os.environ.setdefault("TELEGRAM_SESSION_PATH", "/tmp/api_test_sessions")
    os.environ.setdefault("APP_TIMEZONE", "UTC")


def test_app_lifespan_loads_and_starts_telegram_trigger_runtime():
    _set_required_env()
    with patch("api.main.telegram_trigger_runtime") as runtime, patch("api.main.telegram_bot_command_runtime") as bot_runtime, patch(
        "services.shared.db.migrations.apply.apply_migrations", return_value=None
    ):
        from fastapi.testclient import TestClient
        from api.main import create_app

        app = create_app()
        with TestClient(app, raise_server_exceptions=True):
            pass

    runtime.load_from_db.assert_called_once()
    runtime.start.assert_called_once()
    bot_runtime.load_from_db.assert_called_once()
    bot_runtime.refresh_webhooks.assert_called_once()


def test_app_lifespan_stops_telegram_trigger_runtime_on_shutdown(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "telegram_digest")
    monkeypatch.setenv("POSTGRES_USER", "telegram_digest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "telegram_digest")
    monkeypatch.setenv("WORKSPACE_PATH", "/tmp/api_test_workspace")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/api_test_sessions")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")

    with patch("api.main.telegram_trigger_runtime") as runtime, patch("api.main.telegram_bot_command_runtime") as bot_runtime, patch(
        "services.shared.db.migrations.apply.apply_migrations", return_value=None
    ):
        from fastapi.testclient import TestClient
        from api.main import create_app

        app = create_app()
        with TestClient(app, raise_server_exceptions=True):
            pass

    runtime.stop.assert_called_once()
    bot_runtime.stop.assert_called_once()


def test_health_endpoint_reports_ok(stateless_api_client):
    response = stateless_api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_lifespan_logs_bot_runtime_startup_failure(caplog, monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "telegram_digest")
    monkeypatch.setenv("POSTGRES_USER", "telegram_digest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "telegram_digest")
    monkeypatch.setenv("WORKSPACE_PATH", "/tmp/api_test_workspace")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/api_test_sessions")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")

    with patch("api.main.telegram_trigger_runtime") as runtime, patch("api.main.telegram_bot_command_runtime") as bot_runtime, patch(
        "services.shared.db.migrations.apply.apply_migrations", return_value=None
    ):
        bot_runtime.refresh_webhooks.side_effect = RuntimeError("boom")
        from fastapi.testclient import TestClient
        from api.main import create_app

        caplog.set_level("ERROR")
        app = create_app()
        with TestClient(app, raise_server_exceptions=True):
            pass

    assert runtime.load_from_db.called
    assert "Telegram bot command runtime startup failed" in caplog.text
