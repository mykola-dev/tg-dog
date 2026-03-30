from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services.shared.telegram.client import _legacy_encrypt_secret


def _session_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name / "telegram_sessions"
    d.mkdir(parents=True)
    return d


def _seed_connected(session_dir: Path) -> None:
    state = {
        "account_state": "connected",
        "api_id": "12345",
        "api_hash_encrypted": _legacy_encrypt_secret("abcdef1234"),
        "account_profile": {"display_name": "Test User"},
    }
    (session_dir / "auth_state.json").write_text(json.dumps(state))


def test_startup_skips_wizard_when_connected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_dir = _session_dir(tmp_path, "connected")
    _seed_connected(session_dir)

    from services.onboarding.startup import check_and_onboard

    fake_client = MagicMock()
    fake_client.status.return_value = {
        "account_state": "connected",
        "account_profile": {"display_name": "Test User"},
    }

    with patch("services.onboarding.startup.TelegramClientWrapper", return_value=fake_client), \
         patch("services.onboarding.startup.load_config") as mock_config:
        mock_config.return_value = MagicMock(telegram_session_path=session_dir)
        result = check_and_onboard()

    assert result is True
    output = capsys.readouterr().out
    assert "Skipping setup" in output


def test_startup_runs_wizard_when_disconnected(tmp_path: Path) -> None:
    session_dir = _session_dir(tmp_path, "disconnected")

    from services.onboarding.startup import check_and_onboard

    fake_client = MagicMock()
    fake_client.status.return_value = {
        "account_state": "disconnected",
        "account_profile": None,
    }

    with patch("services.onboarding.startup.TelegramClientWrapper", return_value=fake_client), \
         patch("services.onboarding.startup.load_config") as mock_config, \
         patch("services.onboarding.startup.run_wizard", return_value=True) as mock_wizard, \
         patch("services.onboarding.startup._is_tty", return_value=True):
        mock_config.return_value = MagicMock(telegram_session_path=session_dir)
        result = check_and_onboard()

    assert result is True
    mock_wizard.assert_called_once_with(
        session_path=session_dir,
        reason="No connected Telegram account found.",
    )


def test_startup_prints_advice_when_no_tty_and_disconnected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_dir = _session_dir(tmp_path, "notty")

    from services.onboarding.startup import check_and_onboard

    fake_client = MagicMock()
    fake_client.status.return_value = {
        "account_state": "disconnected",
        "account_profile": None,
    }

    with patch("services.onboarding.startup.TelegramClientWrapper", return_value=fake_client), \
         patch("services.onboarding.startup.load_config") as mock_config, \
         patch("services.onboarding.startup._is_tty", return_value=False):
        mock_config.return_value = MagicMock(telegram_session_path=session_dir)
        result = check_and_onboard()

    assert result is False
    output = capsys.readouterr().out
    assert "make connect-telegram" in output
