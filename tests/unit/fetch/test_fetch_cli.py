import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

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


def test_fetch_cli_emits_canonical_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = tmp_path / "telegram_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _seed_connected_state(sessions)

    workspace = tmp_path / "run_artifacts"
    workspace.mkdir(parents=True, exist_ok=True)

    wrapper = TelegramClientWrapper(sessions)

    fake_messages = [
        {
            "schema_version": "v1",
            "source_kind": "channel",
            "source_id": "c1",
            "message_id": "1001",
            "text": "News item",
            "timestamp": "2026-01-01T10:00:00+00:00",
            "reply_to_message_id": None,
            "forwarded_from_source_id": None,
            "is_outbound": False,
            "is_from_self": False,
            "is_service_message": False,
            "media_items": [],
            "ingestion_meta": {},
        },
        {
            "schema_version": "v1",
            "source_kind": "contact",
            "source_id": "bot1",
            "message_id": "2001",
            "text": "Bot message",
            "timestamp": "2026-01-01T10:05:00+00:00",
            "reply_to_message_id": None,
            "forwarded_from_source_id": None,
            "is_outbound": False,
            "is_from_self": False,
            "is_service_message": False,
            "media_items": [],
            "ingestion_meta": {},
        },
    ]

    async def fake_fetch(
        *,
        api_id: str,
        api_hash: str,
        source_refs: list[str],
        limit_per_source: int,
        time_window_start: datetime | None,
        time_window_end: datetime | None,
        workspace_path: Path,
        run_id: str,
        include_media: bool,
    ) -> list[dict]:
        return fake_messages

    monkeypatch.setattr(wrapper, "_async_fetch_messages", fake_fetch, raising=False)

    messages = wrapper.fetch_messages(
        source_refs=["c1", "bot1"],
        limit_per_source=100,
        time_window_start=None,
        time_window_end=None,
        workspace_path=workspace,
        run_id="fetch-run",
    )

    assert len(messages) == 2
    assert messages[0]["source_id"] == "c1"
    assert messages[0]["text"] == "News item"
    assert messages[1]["source_id"] == "bot1"
