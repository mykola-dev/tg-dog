import json
from pathlib import Path

from services.shared.telegram.client import TelegramClientWrapper, _legacy_encrypt_secret


def _seed_connected_state(sessions: Path) -> None:
    state = {
        "account_state": "connected",
        "last_successful_auth_at": "2026-01-01T00:00:00+00:00",
        "last_auth_error": None,
        "api_id": "1",
        "api_hash_encrypted": _legacy_encrypt_secret("hash"),
        "account_profile": {"display_name": "Test User"},
    }
    (sessions / "auth_state.json").write_text(json.dumps(state), encoding="utf-8")


def test_send_text_chunk_requires_connected_auth(tmp_path: Path) -> None:
    sessions = tmp_path / "telegram_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _seed_connected_state(sessions)
    wrapper = TelegramClientWrapper(sessions)

    assert wrapper._load_connected_auth() == ("1", "hash")
