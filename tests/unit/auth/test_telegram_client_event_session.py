from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from services.shared.telegram.client import TelegramClientWrapper


def test_prepare_event_session_copies_primary_session_file(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)
    primary_session = Path(f"{wrapper.session_file_base}.session")
    primary_journal = Path(f"{wrapper.session_file_base}.session-journal")
    primary_session.write_bytes(b"primary-session")
    primary_journal.write_bytes(b"primary-journal")

    target_base = wrapper.prepare_event_session(purpose="events")

    assert target_base == tmp_path / "telethon-events"
    assert Path(f"{target_base}.session").read_bytes() == b"primary-session"
    assert Path(f"{target_base}.session-journal").read_bytes() == b"primary-journal"


def test_async_open_event_client_uses_string_session(monkeypatch, tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path)

    source_client = MagicMock()
    source_client.session = MagicMock()

    async def source_connect():
        return None

    async def source_authorized():
        return True

    async def source_disconnect():
        return None

    source_client.connect.side_effect = source_connect
    source_client.is_user_authorized.side_effect = source_authorized
    source_client.disconnect.side_effect = source_disconnect

    event_client = MagicMock()

    async def event_connect():
        return None

    async def event_authorized():
        return True

    event_client.connect.side_effect = event_connect
    event_client.is_user_authorized.side_effect = event_authorized

    calls = []

    def fake_telegram_client(session, api_id, api_hash):
        calls.append((session, api_id, api_hash))
        if len(calls) == 1:
            return source_client
        return event_client

    class _FakeStringSession:
        def __init__(self, value=None):
            self.value = value or ""

        @staticmethod
        def save(session):
            return "encoded-session"

        def __str__(self):
            return f"string-session:{self.value}"

    monkeypatch.setattr("services.shared.telegram.client.TelegramClient", fake_telegram_client)
    monkeypatch.setattr("services.shared.telegram.client.StringSession", _FakeStringSession)

    client = asyncio.run(wrapper._async_open_event_client(api_id="1", api_hash="hash"))

    assert client is event_client
    assert calls[0][0] == str(wrapper.session_file_base)
    assert str(calls[1][0]) == "string-session:encoded-session"
