from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _load_local_env_defaults() -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


_ENV_DEFAULTS = _load_local_env_defaults()


def _env_value(name: str, default: str) -> str:
    return os.getenv(name) or _ENV_DEFAULTS.get(name, default)


def _test_db_url() -> str:
    return (
        "postgresql+psycopg2://"
        f"{_env_value('POSTGRES_USER', 'telegram_digest')}:"
        f"{_env_value('POSTGRES_PASSWORD', 'telegram_digest')}"
        f"@{_env_value('POSTGRES_HOST', 'localhost')}:"
        f"{_env_value('POSTGRES_PORT', '5432')}/"
        f"{_env_value('POSTGRES_DB', 'telegram_digest')}"
    )


@pytest.fixture()
def db_session():
    engine = create_engine(_test_db_url())
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def api_client(db_session, monkeypatch):
    # Set required env vars
    monkeypatch.setenv("POSTGRES_HOST", _env_value("POSTGRES_HOST", "localhost"))
    monkeypatch.setenv("POSTGRES_PORT", _env_value("POSTGRES_PORT", "5432"))
    monkeypatch.setenv("POSTGRES_DB", _env_value("POSTGRES_DB", "telegram_digest"))
    monkeypatch.setenv("POSTGRES_USER", _env_value("POSTGRES_USER", "telegram_digest"))
    monkeypatch.setenv("POSTGRES_PASSWORD", _env_value("POSTGRES_PASSWORD", "telegram_digest"))
    monkeypatch.setenv("WORKSPACE_PATH", "/tmp/api_test_workspace")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/api_test_sessions")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")

    with pytest.MonkeyPatch.context() as _:
        from unittest.mock import patch

        with patch("services.shared.db.migrations.apply.apply_migrations", return_value=None):
            from api.main import create_app
            from api.db import get_db

            app = create_app()
            app.dependency_overrides[get_db] = lambda: db_session

            with TestClient(app, raise_server_exceptions=True) as client:
                yield client


@pytest.fixture()
def stateless_api_client(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", _env_value("POSTGRES_HOST", "localhost"))
    monkeypatch.setenv("POSTGRES_PORT", _env_value("POSTGRES_PORT", "5432"))
    monkeypatch.setenv("POSTGRES_DB", _env_value("POSTGRES_DB", "telegram_digest"))
    monkeypatch.setenv("POSTGRES_USER", _env_value("POSTGRES_USER", "telegram_digest"))
    monkeypatch.setenv("POSTGRES_PASSWORD", _env_value("POSTGRES_PASSWORD", "telegram_digest"))
    monkeypatch.setenv("WORKSPACE_PATH", "/tmp/api_test_workspace")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "/tmp/api_test_sessions")
    monkeypatch.setenv("APP_TIMEZONE", "UTC")

    with pytest.MonkeyPatch.context() as _:
        from unittest.mock import patch

        with patch("services.shared.db.migrations.apply.apply_migrations", return_value=None):
            from api.main import create_app

            app = create_app()
            with TestClient(app, raise_server_exceptions=True) as client:
                yield client
