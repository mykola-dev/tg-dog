from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from services.shared.telegram.errors import TelegramAuthError


def _session_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name / "telegram_sessions"
    d.mkdir(parents=True)
    return d


class FakeClient:
    """Minimal fake TelegramClientWrapper for wizard unit tests."""

    def __init__(self, session_root: Path, *, need_2fa: bool = False) -> None:
        self.session_root = session_root
        self.need_2fa = need_2fa
        self.started = False
        self.code_submitted = False
        self.twofa_submitted = False

    def status(self) -> dict:
        if self.code_submitted and not self.need_2fa:
            return {"account_state": "connected", "account_profile": {"display_name": "Test User"}}
        if self.twofa_submitted:
            return {"account_state": "connected", "account_profile": {"display_name": "Test User"}}
        return {"account_state": "disconnected", "account_profile": None}

    def start_login(self, *, api_id: str, api_hash: str, phone_number: str, ttl_seconds: int = 900) -> dict:
        self.started = True
        return {
            "auth_flow_id": "flow-123",
            "account_state": "awaiting_code",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "masked_phone_number": "+380*****567",
        }

    def submit_code(self, *, auth_flow_id: str, login_code: str) -> dict:
        if login_code == "99999":
            raise TelegramAuthError(code="INVALID_CODE", message="Invalid code")
        self.code_submitted = True
        if self.need_2fa:
            return {"account_state": "awaiting_2fa", "account_profile": None}
        return {"account_state": "connected", "account_profile": {"display_name": "Test User"}}

    def submit_2fa(self, *, auth_flow_id: str, two_factor_password: str) -> dict:
        if two_factor_password == "wrongpass":
            raise TelegramAuthError(code="INVALID_2FA", message="Invalid 2FA")
        self.twofa_submitted = True
        return {"account_state": "connected", "account_profile": {"display_name": "Test User"}}


def test_wizard_happy_path_no_2fa(tmp_path: Path) -> None:
    session_dir = _session_dir(tmp_path, "happy")
    client = FakeClient(session_dir)

    user_inputs = iter(["12345", "abcdef1234", "+380501234567", "77777"])

    from services.onboarding.wizard import run_wizard

    with patch("builtins.input", side_effect=user_inputs), \
         patch("services.onboarding.wizard.TelegramClientWrapper", return_value=client):
        result = run_wizard(session_path=session_dir)

    assert result is True
    assert client.started
    assert client.code_submitted


def test_wizard_happy_path_with_2fa(tmp_path: Path) -> None:
    session_dir = _session_dir(tmp_path, "2fa")
    client = FakeClient(session_dir, need_2fa=True)

    user_inputs = iter(["12345", "abcdef1234", "+380501234567", "77777"])

    from services.onboarding.wizard import run_wizard

    with patch("builtins.input", side_effect=user_inputs), \
         patch("getpass.getpass", return_value="correct_pass"), \
         patch("services.onboarding.wizard.TelegramClientWrapper", return_value=client):
        result = run_wizard(session_path=session_dir)

    assert result is True
    assert client.twofa_submitted


def test_wizard_retries_on_invalid_code(tmp_path: Path) -> None:
    session_dir = _session_dir(tmp_path, "retry_code")
    client = FakeClient(session_dir)

    # First attempt: bad code "99999", second attempt: good code "77777"
    user_inputs = iter(["12345", "abcdef1234", "+380501234567", "99999", "77777"])

    from services.onboarding.wizard import run_wizard

    with patch("builtins.input", side_effect=user_inputs), \
         patch("services.onboarding.wizard.TelegramClientWrapper", return_value=client):
        result = run_wizard(session_path=session_dir)

    assert result is True
    assert client.code_submitted


def test_wizard_retries_on_invalid_2fa(tmp_path: Path) -> None:
    session_dir = _session_dir(tmp_path, "retry_2fa")
    client = FakeClient(session_dir, need_2fa=True)

    user_inputs = iter(["12345", "abcdef1234", "+380501234567", "77777"])

    from services.onboarding.wizard import run_wizard

    with patch("builtins.input", side_effect=user_inputs), \
         patch("getpass.getpass", side_effect=["wrongpass", "correct_pass"]), \
         patch("services.onboarding.wizard.TelegramClientWrapper", return_value=client):
        result = run_wizard(session_path=session_dir)

    assert result is True
    assert client.twofa_submitted


class ExpiringClient(FakeClient):
    """First start_login succeeds but submit_code raises TimeoutError. Second attempt works."""

    def __init__(self, session_root: Path) -> None:
        super().__init__(session_root)
        self._code_call_count = 0

    def submit_code(self, *, auth_flow_id: str, login_code: str) -> dict:
        self._code_call_count += 1
        if self._code_call_count == 1:
            raise TimeoutError("AUTH_FLOW_EXPIRED")
        return super().submit_code(auth_flow_id=auth_flow_id, login_code=login_code)


def test_wizard_restarts_on_expired_flow(tmp_path: Path) -> None:
    session_dir = _session_dir(tmp_path, "expired")
    client = ExpiringClient(session_dir)

    # First round: credentials + code (expires) -> second round: credentials + code (succeeds)
    user_inputs = iter([
        "12345", "abcdef1234", "+380501234567", "77777",
        "12345", "abcdef1234", "+380501234567", "77777",
    ])

    from services.onboarding.wizard import run_wizard

    with patch("builtins.input", side_effect=user_inputs), \
         patch("services.onboarding.wizard.TelegramClientWrapper", return_value=client):
        result = run_wizard(session_path=session_dir)

    assert result is True


def test_prompt_prints_label_before_reading_input() -> None:
    from services.onboarding.wizard import _prompt

    with patch("builtins.input", return_value="12345"), patch("builtins.print") as print_mock:
        result = _prompt("Telegram API ID")

    assert result == "12345"
    print_mock.assert_any_call("Telegram API ID:", flush=True)
