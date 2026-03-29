import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.shared.telegram.client import TelegramClientWrapper, _legacy_encrypt_secret
from services.shared.telegram.errors import TelegramOperationalError


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


def test_fetch_messages_requires_real_telethon_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = tmp_path / "telegram_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _seed_connected_state(sessions)
    workspace = tmp_path / "run_artifacts"
    workspace.mkdir(parents=True, exist_ok=True)

    wrapper = TelegramClientWrapper(sessions)
    monkeypatch.setattr("services.shared.telegram.client.TelegramClient", None)

    with pytest.raises(TelegramOperationalError) as exc_info:
        wrapper.fetch_messages(
            source_refs=["-100123"],
            limit_per_source=100,
            time_window_start=None,
            time_window_end=None,
            workspace_path=workspace,
            run_id="fetch-run",
        )

    assert exc_info.value.code == "TELETHON_NOT_INSTALLED"


def test_async_fetch_messages_stops_after_time_window_expires(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = tmp_path / "telegram_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _seed_connected_state(sessions)

    wrapper = TelegramClientWrapper(sessions)
    now = datetime.now(timezone.utc)

    class _Message:
        def __init__(self, message_id: int, date: datetime) -> None:
            self.id = message_id
            self.date = date

    class _FakeClient:
        def __init__(self) -> None:
            self.yielded = 0

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def get_entity(self, entity_ref):
            return {"id": entity_ref}

        async def iter_messages(self, entity, limit: int):
            messages = [
                _Message(1, now - timedelta(hours=1)),
                _Message(2, now - timedelta(hours=25)),
                _Message(3, now - timedelta(hours=26)),
            ]
            for message in messages:
                self.yielded += 1
                yield message

    fake_client = _FakeClient()

    def _fake_build_client(api_id: str, api_hash: str, *, purpose: str | None = None):
        return fake_client

    async def _fake_build_canonical_message(**kwargs):
        message = kwargs["message"]
        return {"message_id": str(message.id)}

    monkeypatch.setattr(wrapper, "_build_client", _fake_build_client)
    monkeypatch.setattr(wrapper, "_async_build_canonical_message", _fake_build_canonical_message)

    results = asyncio.run(
        wrapper._async_fetch_messages(
            api_id="1",
            api_hash="hash",
            source_refs=["-100123"],
            limit_per_source=500,
            time_window_start=now - timedelta(hours=24),
            time_window_end=now,
            workspace_path=tmp_path,
            run_id="fetch-run",
            include_media=True,
        )
    )

    assert results == [{"message_id": "1"}]
    assert fake_client.yielded == 2
