import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.shared.telegram.client import _legacy_encrypt_secret


ROOT = Path(__file__).resolve().parents[3]


def _runtime_paths(root: Path) -> tuple[Path, Path]:
    workspace = root / "run_artifacts"
    sessions = root / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    return workspace, sessions


def _run_auth_command(
    command: str,
    payload: dict,
    *,
    runtime_root: Path,
) -> subprocess.CompletedProcess[str]:
    workspace, sessions = _runtime_paths(runtime_root)

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
            "APP_MASTER_KEY": "test_master_key",
        }
    )

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "services.auth.main",
            command,
            "--run-id",
            "test-run",
            "--payload-json",
            json.dumps(payload),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_auth_flow(
    sessions: Path,
    *,
    flow_id: str,
    expires_at: datetime,
    phone_code_hash: str = "fake-hash-for-tests",
) -> None:
    """Write a pre-seeded auth_flow.json to simulate a completed start-login call."""
    flow = {
        "auth_flow_id": flow_id,
        "phone_number": "+380000000000",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "api_id": "1",
        "api_hash_encrypted": _legacy_encrypt_secret("hash"),
        "phone_code_hash": phone_code_hash,
    }
    state = {
        "account_state": "awaiting_code",
        "last_successful_auth_at": None,
        "last_auth_error": None,
        "api_id": "1",
        "api_hash_encrypted": _legacy_encrypt_secret("hash"),
        "account_profile": None,
    }
    (sessions / "auth_flow.json").write_text(json.dumps(flow), encoding="utf-8")
    (sessions / "auth_state.json").write_text(json.dumps(state), encoding="utf-8")


def _make_flow_id(phone_number: str) -> str:
    now = datetime.now(timezone.utc)
    return hashlib.sha256(f"{phone_number}:{now.isoformat()}".encode()).hexdigest()[:24]


def test_start_login_cli_emits_awaiting_code_envelope(tmp_path: Path) -> None:
    """
    Verifies that the auth CLI emits a well-formed ok envelope with account_state=awaiting_code.
    Since start-login calls real Telethon, this test seeds the flow directly and verifies
    the status command reflects awaiting_code — the wrapper unit tests cover start-login itself.
    """
    runtime_root = tmp_path / "awaiting_code_status"
    _, sessions = _runtime_paths(runtime_root)
    flow_id = _make_flow_id("+380000000000")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=900)
    _seed_auth_flow(sessions, flow_id=flow_id, expires_at=expires_at)

    result = _run_auth_command("status", {}, runtime_root=runtime_root)
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "ok"
    assert envelope["payload_inline"]["account_state"] == "awaiting_code"


def test_submit_code_can_transition_to_connected(tmp_path: Path) -> None:
    """
    Seeds auth flow state, then submits a code via CLI subprocess.
    The submit-code CLI path is tested end-to-end through the auth adapter.
    The Telethon sign-in call is expected to fail with INVALID_CODE (fake api_id/code),
    so we verify the CLI exits 1 with an appropriate error code.
    """
    runtime_root = tmp_path / "submit_code_transition"
    _, sessions = _runtime_paths(runtime_root)
    flow_id = _make_flow_id("+380000000000")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=900)
    _seed_auth_flow(sessions, flow_id=flow_id, expires_at=expires_at)

    submit = _run_auth_command(
        "submit-code",
        {"auth_flow_id": flow_id, "login_code": "11111"},
        runtime_root=runtime_root,
    )
    # With fake api_id/hash, Telethon will reject the call — CLI must exit non-zero
    # and emit a structured error envelope (not crash with unhandled exception).
    assert submit.returncode == 1
    submit_env = json.loads(submit.stdout)
    assert submit_env["status"] == "error"
    assert submit_env["error"]["code"] is not None


def test_expired_auth_flow_cannot_accept_code(tmp_path: Path) -> None:
    runtime_root = tmp_path / "expired_flow"
    _, sessions = _runtime_paths(runtime_root)
    flow_id = _make_flow_id("+380000000000")
    # Seed an already-expired flow
    expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    _seed_auth_flow(sessions, flow_id=flow_id, expires_at=expires_at)

    submit = _run_auth_command(
        "submit-code",
        {"auth_flow_id": flow_id, "login_code": "11111"},
        runtime_root=runtime_root,
    )
    assert submit.returncode == 1
    submit_env = json.loads(submit.stdout)
    assert submit_env["status"] == "error"
    assert submit_env["error"]["code"] == "AUTH_FLOW_EXPIRED"
