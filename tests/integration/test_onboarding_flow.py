from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.shared.telegram.client import _legacy_encrypt_secret


ROOT = Path(__file__).resolve().parents[2]


def _runtime_paths(test_name: str) -> tuple[Path, Path]:
    root = ROOT / ".pytest_runtime" / test_name
    workspace = root / "run_artifacts"
    sessions = root / "telegram_sessions"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    return workspace, sessions


def _invoke_auth_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    command: str,
    payload: dict,
    test_name: str,
    client_cls: type | None = None,
) -> tuple[int, dict]:
    from services.auth import main as auth_main

    workspace, sessions = _runtime_paths(test_name)
    monkeypatch.setattr(
        auth_main,
        "parse_args",
        lambda: Namespace(command=command, run_id="integration-run", payload_json=json.dumps(payload)),
    )
    monkeypatch.setattr(
        auth_main,
        "load_config",
        lambda require_master_key=True: SimpleNamespace(
            telegram_session_path=sessions,
            workspace_path=workspace,
        ),
    )
    if client_cls is not None:
        monkeypatch.setattr(auth_main, "TelegramClientWrapper", client_cls)

    exit_code = 0
    try:
        auth_main.main()
    except SystemExit as exc:
        exit_code = int(exc.code)

    stdout = capsys.readouterr().out
    return exit_code, json.loads(stdout)


def _assert_ok(exit_code: int, envelope: dict) -> dict:
    assert exit_code == 0
    assert envelope["status"] == "ok"
    return envelope["payload_inline"]


def _assert_error(exit_code: int, envelope: dict, *, code: str, message: str) -> dict:
    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == code
    assert envelope["error"]["message"] == message
    return envelope["error"]


def _start_login_payload(*, auth_flow_ttl_seconds: int | None = None) -> dict:
    payload = {
        "api_id": "1",
        "api_hash": "hash",
        "phone_number": "+380000000000",
        "display_timezone": "UTC",
    }
    if auth_flow_ttl_seconds is not None:
        payload["auth_flow_ttl_seconds"] = auth_flow_ttl_seconds
    return payload


def _seed_auth_flow(test_name: str, *, auth_flow_id: str = "flow-123", ttl_seconds: int = 300) -> str:
    _, sessions = _runtime_paths(test_name)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)
    (sessions / "auth_flow.json").write_text(
        json.dumps(
            {
                "auth_flow_id": auth_flow_id,
                "phone_number": "+380000000000",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "api_id": "1",
                "api_hash_encrypted": _legacy_encrypt_secret("hash"),
                "phone_code_hash": "code-hash-123",
            }
        ),
        encoding="utf-8",
    )
    return auth_flow_id


class FakeTelegramBehaviorClient:
    def __init__(
        self,
        _session_root: Path,
        *,
        start_login_result: dict | None = None,
        submit_code_result: dict | Exception | None = None,
        submit_2fa_result: dict | Exception | None = None,
        status_result: dict | None = None,
    ) -> None:
        self._start_login_result = start_login_result or {
            "auth_flow_id": "flow-123",
            "account_state": "awaiting_code",
            "expires_at": "2030-01-01T00:00:00+00:00",
            "masked_phone_number": "+38***00",
        }
        self._submit_code_result = submit_code_result or {
            "account_state": "connected",
            "account_profile": {"display_name": "Connected User"},
        }
        self._submit_2fa_result = submit_2fa_result or {
            "account_state": "connected",
            "account_profile": {"display_name": "Connected User"},
        }
        self._status_result = status_result or {
            "account_state": "connected",
            "account_profile": {"display_name": "Connected User"},
            "last_successful_auth_at": None,
            "last_auth_error": None,
        }

    def start_login(self, *, api_id: str, api_hash: str, phone_number: str, ttl_seconds: int = 900) -> dict:
        return self._start_login_result

    def submit_code(self, *, auth_flow_id: str, login_code: str) -> dict:
        if isinstance(self._submit_code_result, Exception):
            raise self._submit_code_result
        return self._submit_code_result

    def submit_2fa(self, *, auth_flow_id: str, two_factor_password: str) -> dict:
        if isinstance(self._submit_2fa_result, Exception):
            raise self._submit_2fa_result
        return self._submit_2fa_result

    def status(self) -> dict:
        return self._status_result


def test_successful_login_path(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class Client(FakeTelegramBehaviorClient):
        pass

    start_payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="start-login",
            payload=_start_login_payload(),
            test_name="onboarding_success",
            client_cls=Client,
        )
    )
    assert start_payload["account_state"] == "awaiting_code"
    payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="submit-code",
            payload={"auth_flow_id": start_payload["auth_flow_id"], "login_code": "11111"},
            test_name="onboarding_success",
            client_cls=Client,
        )
    )
    assert payload["account_state"] == "connected"


def test_awaiting_2fa_path(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class Awaiting2FAClient(FakeTelegramBehaviorClient):
        def __init__(self, session_root: Path) -> None:
            super().__init__(
                session_root,
                submit_code_result={"account_state": "awaiting_2fa", "account_profile": None},
                submit_2fa_result={"account_state": "connected", "account_profile": {"display_name": "Connected User"}},
            )

    start_payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="start-login",
            payload=_start_login_payload(),
            test_name="onboarding_2fa",
            client_cls=Awaiting2FAClient,
        )
    )

    code_payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="submit-code",
            payload={"auth_flow_id": start_payload["auth_flow_id"], "login_code": "11111"},
            test_name="onboarding_2fa",
            client_cls=Awaiting2FAClient,
        )
    )
    assert code_payload["account_state"] == "awaiting_2fa"

    payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="submit-2fa",
            payload={
                "auth_flow_id": start_payload["auth_flow_id"],
                "two_factor_password": "password",
            },
            test_name="onboarding_2fa",
            client_cls=Awaiting2FAClient,
        )
    )
    assert payload["account_state"] == "connected"


def test_expired_flow_rejection(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from services.shared.telegram import client as telegram_client

    auth_flow_id = _seed_auth_flow("onboarding_expired", ttl_seconds=0)
    monkeypatch.setattr(telegram_client, "TelegramClient", object())
    _assert_error(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="submit-code",
            payload={"auth_flow_id": auth_flow_id, "login_code": "11111"},
            test_name="onboarding_expired",
        ),
        code="AUTH_FLOW_EXPIRED",
        message="Your login session expired. Start again from step 1.",
    )


def test_submit_2fa_rejects_expired_flow(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from services.shared.telegram import client as telegram_client

    auth_flow_id = _seed_auth_flow("onboarding_expired_2fa", ttl_seconds=0)
    monkeypatch.setattr(telegram_client, "TelegramClient", object())
    _assert_error(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="submit-2fa",
            payload={"auth_flow_id": auth_flow_id, "two_factor_password": "password"},
            test_name="onboarding_expired_2fa",
        ),
        code="AUTH_FLOW_EXPIRED",
        message="Your login session expired. Start again from step 1.",
    )


def test_invalid_code_returns_stable_user_facing_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from services.shared.telegram.errors import TelegramAuthError

    class FakeTelegramClientWrapper:
        def __init__(self, _session_root: Path) -> None:
            pass

        def submit_code(self, *, auth_flow_id: str, login_code: str) -> dict:
            raise TelegramAuthError(code="INVALID_CODE")

    exit_code, envelope = _invoke_auth_main(
        monkeypatch,
        capsys,
        command="submit-code",
        payload={"auth_flow_id": "flow-123", "login_code": "00000"},
        test_name="cli_submit-code",
        client_cls=FakeTelegramClientWrapper,
    )

    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "INVALID_CODE"
    assert envelope["error"]["message"] == "That login code was not accepted. Enter the latest code and try again."


def test_invalid_2fa_returns_stable_user_facing_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from services.shared.telegram.errors import TelegramAuthError

    class Invalid2FAClient(FakeTelegramBehaviorClient):
        def __init__(self, session_root: Path) -> None:
            super().__init__(session_root, submit_2fa_result=TelegramAuthError(code="INVALID_2FA"))

    start_payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="start-login",
            payload=_start_login_payload(),
            test_name="onboarding_invalid_2fa_real_path",
            client_cls=Invalid2FAClient,
        )
    )

    exit_code, envelope = _invoke_auth_main(
        monkeypatch,
        capsys,
        command="submit-2fa",
        payload={"auth_flow_id": start_payload["auth_flow_id"], "two_factor_password": "wrong-password"},
        test_name="onboarding_invalid_2fa_real_path",
        client_cls=Invalid2FAClient,
    )

    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "INVALID_2FA"
    assert envelope["error"]["message"] == "That 2FA password was not accepted. Try again."
def test_reconnect_required_after_simulated_revocation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    test_name = "onboarding_revoked"

    class RevokedStatusClient(FakeTelegramBehaviorClient):
        def __init__(self, session_root: Path) -> None:
            super().__init__(
                session_root,
                status_result={
                    "account_state": "reauth_required",
                    "account_profile": {"display_name": "Connected User"},
                    "last_successful_auth_at": None,
                    "last_auth_error": {
                        "code": "SESSION_REVOKED",
                        "message": "Session was revoked and re-auth is required",
                    },
                },
            )

    start_payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="start-login",
            payload=_start_login_payload(),
            test_name=test_name,
            client_cls=RevokedStatusClient,
        )
    )
    _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="submit-code",
            payload={"auth_flow_id": start_payload["auth_flow_id"], "login_code": "11111"},
            test_name=test_name,
            client_cls=RevokedStatusClient,
        )
    )

    payload = _assert_ok(
        *_invoke_auth_main(
            monkeypatch,
            capsys,
            command="status",
            payload={},
            test_name=test_name,
            client_cls=RevokedStatusClient,
        )
    )
    assert payload["account_state"] == "reauth_required"


def test_start_login_returns_operational_error_when_telethon_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from services.shared.telegram import client as telegram_client

    monkeypatch.setattr(telegram_client, "TelegramClient", None)

    exit_code, envelope = _invoke_auth_main(
        monkeypatch,
        capsys,
        command="start-login",
        payload=_start_login_payload(),
        test_name="onboarding_telethon_missing",
    )

    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "TELETHON_NOT_INSTALLED"
    assert envelope["error"]["message"] == "Telethon is required for Telegram authentication but is not installed."


def test_submit_code_returns_operational_error_when_telethon_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from services.shared.telegram import client as telegram_client

    auth_flow_id = _seed_auth_flow("onboarding_submit_code_telethon_missing")
    monkeypatch.setattr(telegram_client, "TelegramClient", None)

    exit_code, envelope = _invoke_auth_main(
        monkeypatch,
        capsys,
        command="submit-code",
        payload={"auth_flow_id": auth_flow_id, "login_code": "11111"},
        test_name="onboarding_submit_code_telethon_missing",
    )

    assert exit_code == 1
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "TELETHON_NOT_INSTALLED"
