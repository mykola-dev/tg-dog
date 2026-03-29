from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.shared.telegram.client import _legacy_encrypt_secret


ROOT = Path(__file__).resolve().parents[2]


def _runtime_paths(test_name: str) -> tuple[Path, Path]:
    root = ROOT / ".pytest_runtime" / test_name
    workspace = root / "run_artifacts"
    sessions = root / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    return workspace, sessions


def _run_auth(
    command: str,
    payload: dict,
    *,
    test_name: str,
    include_master_key: bool = True,
) -> subprocess.CompletedProcess[str]:
    workspace, sessions = _runtime_paths(test_name)
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "telegram_digest",
            "POSTGRES_USER": "telegram_digest",
            "POSTGRES_PASSWORD": "telegram_digest",
            "WORKSPACE_PATH": str(workspace),
            "TELEGRAM_SESSION_PATH": str(sessions),
            "APP_TIMEZONE": "UTC",
        }
    )
    if include_master_key:
        env["APP_MASTER_KEY"] = "test_master_key"
    elif "APP_MASTER_KEY" in env:
        del env["APP_MASTER_KEY"]

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "services.auth.main",
            command,
            "--run-id",
            "integration-run",
            "--payload-json",
            json.dumps(payload),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_connected_state(sessions: Path) -> None:
    """Write connected auth_state.json directly, bypassing real Telethon calls."""
    state = {
        "account_state": "connected",
        "last_successful_auth_at": "2026-01-01T00:00:00+00:00",
        "last_auth_error": None,
        "api_id": "1",
        "api_hash_encrypted": _legacy_encrypt_secret("hash"),
        "account_profile": {"display_name": "Test User"},
    }
    flow_id = hashlib.sha256(b"test-flow").hexdigest()[:24]
    flow = {
        "auth_flow_id": flow_id,
        "phone_number": "+380000000000",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=900)).isoformat(),
        "api_id": "1",
        "api_hash_encrypted": _legacy_encrypt_secret("hash"),
        "phone_code_hash": "fake-hash-for-tests",
    }
    (sessions / "auth_state.json").write_text(json.dumps(state), encoding="utf-8")
    (sessions / "auth_flow.json").write_text(json.dumps(flow), encoding="utf-8")


def test_auth_operations_fail_when_master_key_missing() -> None:
    result = _run_auth(
        "start-login",
        {
            "api_id": "1",
            "api_hash": "hash",
            "phone_number": "+380000000000",
            "display_timezone": "UTC",
        },
        test_name="missing_master_key",
        include_master_key=False,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "AUTH_CONFIG_ERROR"


def test_digest_actions_blocked_in_disconnected_or_reauth_required() -> None:
    from services.auth.main import _is_digest_action_allowed

    assert _is_digest_action_allowed("disconnected") is False
    assert _is_digest_action_allowed("reauth_required") is False
    assert _is_digest_action_allowed("connected") is True


def test_full_account_reset_clears_runtime_state() -> None:
    test_name = "full_reset"
    workspace, sessions = _runtime_paths(test_name)
    _seed_connected_state(sessions)

    (workspace / "dummy_runtime.json").write_text("{}", encoding="utf-8")

    reset = _run_auth("reset-account", {}, test_name=test_name)
    assert reset.returncode == 0

    assert not (sessions / "auth_state.json").exists()
    assert not (sessions / "auth_flow.json").exists()
    assert not (workspace / "dummy_runtime.json").exists()
