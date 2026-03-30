from __future__ import annotations

import os
import shutil
import subprocess
import time
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


def _base_env() -> dict[str, str]:
    return {
        "POSTGRES_DB": "telegram_digest",
        "POSTGRES_USER": "telegram_digest",
        "POSTGRES_PASSWORD": "telegram_digest",
        "POSTGRES_PORT": "0",
        "APP_MASTER_KEY": "test_master_key_1234567890",
        "APP_TIMEZONE": "UTC",
        "WORKSPACE_PATH": "/workspace/run_artifacts",
        "TELEGRAM_SESSION_PATH": "/workspace/telegram_sessions",
        "N8N_PORT": "0",
        "API_PORT": "0",
        "WEB_PORT": "0",
        "COMPOSE_PROJECT_NAME": f"tgdigest_{uuid.uuid4().hex[:8]}",
    }


def _compose_cmd(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "compose", *args]
    merged_env = dict(os.environ)
    merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def _wait_for_postgres(env: dict[str, str], timeout_seconds: int = 45) -> subprocess.CompletedProcess[str]:
    deadline = time.time() + timeout_seconds
    last_result: subprocess.CompletedProcess[str] | None = None

    while time.time() < deadline:
        last_result = _compose_cmd(
            env,
            "exec",
            "-T",
            "postgres",
            "pg_isready",
            "-U",
            env["POSTGRES_USER"],
            "-d",
            env["POSTGRES_DB"],
        )
        if last_result.returncode == 0:
            return last_result
        time.sleep(2)

    assert last_result is not None
    return last_result


def _wait_for_n8n_health(env: dict[str, str], timeout_seconds: int = 120) -> subprocess.CompletedProcess[str]:
    deadline = time.time() + timeout_seconds
    last_result: subprocess.CompletedProcess[str] | None = None

    script = (
        "import urllib.request; "
        "response = urllib.request.urlopen('http://n8n:5678/healthz', timeout=20); "
        "print(response.status); print(response.read().decode('utf-8'))"
    )

    while time.time() < deadline:
        last_result = _compose_cmd(env, "exec", "-T", "api", "python", "-c", script)
        if last_result.returncode == 0:
            return last_result
        time.sleep(2)

    assert last_result is not None
    return last_result


def test_stack_boot() -> None:
    if not _docker_available():
        pytest.skip("Docker Compose is not available")

    env = _base_env()

    up = _compose_cmd(env, "up", "-d", "--build")
    assert up.returncode == 0, up.stderr

    try:
        ready = _wait_for_postgres(env)
        assert ready.returncode == 0, ready.stderr

        ps = _compose_cmd(env, "ps", "--format", "json")
        assert ps.returncode == 0, ps.stderr
        ps_text = ps.stdout.lower()
        assert "postgres" in ps_text
        assert "api" in ps_text
        assert "n8n" in ps_text

        n8n_health = _wait_for_n8n_health(env)
        assert n8n_health.returncode == 0, n8n_health.stderr
        assert "200" in n8n_health.stdout

        trivial = _compose_cmd(
            env,
            "run",
            "--rm",
            "api",
            "python",
            "-c",
            "from services.shared.cli import build_success_envelope; print(build_success_envelope(node_name='test', run_id='run').status)",
        )
        assert trivial.returncode == 0, trivial.stderr
        assert "ok" in trivial.stdout

        migrate = _compose_cmd(
            env,
            "run",
            "--rm",
            "api",
            "python",
            "-m",
            "services.shared.db.migrations.apply",
        )
        assert migrate.returncode == 0, migrate.stderr

        manifest = _compose_cmd(
            env,
            "run",
            "--rm",
            "api",
            "python",
            "-m",
            "services.shared.runtime.manifest",
            "--run-id",
            "stack-boot-test",
            "--trigger-type",
            "manual",
        )
        assert manifest.returncode == 0, manifest.stderr

        verify_manifest = _compose_cmd(
            env,
            "run",
            "--rm",
            "api",
            "python",
            "-c",
            "from pathlib import Path; p=Path('/workspace/run_artifacts/runs/stack-boot-test/manifest.json'); print(p.exists());",
        )
        assert verify_manifest.returncode == 0, verify_manifest.stderr
        assert "True" in verify_manifest.stdout
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")
