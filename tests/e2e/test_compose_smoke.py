from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _env() -> dict[str, str]:
    return {
        "POSTGRES_DB": "telegram_digest",
        "POSTGRES_USER": "telegram_digest",
        "POSTGRES_PASSWORD": "telegram_digest",
        "POSTGRES_PORT": "0",
        "N8N_PASSWORD": "BootstrapPassword123",
        "N8N_PORT": "0",
        "APP_MASTER_KEY": "test_master_key_1234567890",
        "APP_TIMEZONE": "UTC",
        "WORKSPACE_PATH": "/workspace/run_artifacts",
        "TELEGRAM_SESSION_PATH": "/workspace/telegram_sessions",
        "API_PORT": "0",
        "WEB_PORT": "0",
        "COMPOSE_PROJECT_NAME": f"compose_smoke_{uuid.uuid4().hex[:8]}",
    }


def _compose(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    merged.update(env)
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_stack_boots_and_exposes_required_services() -> None:
    if not _docker_available():
        pytest.skip("Docker Compose is not available")

    env = _env()
    up = _compose(env, "up", "-d", "--build")
    assert up.returncode == 0, up.stderr

    try:
        ps = _compose(env, "ps", "--format", "json")
        assert ps.returncode == 0, ps.stderr
        text = ps.stdout.lower()
        assert "postgres" in text
        assert "app" in text
        assert "n8n" in text
    finally:
        _compose(env, "down", "-v", "--remove-orphans")
