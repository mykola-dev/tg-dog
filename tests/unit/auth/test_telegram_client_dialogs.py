from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.shared.telegram.client import TelegramClientWrapper, _legacy_encrypt_secret


def _write_connected_state(sessions: Path) -> None:
    (sessions / "auth_state.json").write_text(
        json.dumps({
            "account_state": "connected",
            "api_id": "123",
            "api_hash_encrypted": _legacy_encrypt_secret("hash"),
            "last_successful_auth_at": "2026-01-01T00:00:00+00:00",
            "last_auth_error": None,
            "account_profile": {"display_name": "Test"},
        }),
        encoding="utf-8",
    )


def test_list_dialogs_returns_dialog_list(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    _write_connected_state(sessions)
    wrapper = TelegramClientWrapper(sessions)

    mock_entity = MagicMock()
    mock_entity.title = "Test Channel"
    mock_entity.username = "testchannel"
    mock_entity.broadcast = True
    mock_entity.megagroup = False
    mock_entity.bot = False
    mock_entity.is_self = False

    mock_dialog = MagicMock()
    mock_dialog.id = -1001234567890
    mock_dialog.entity = mock_entity
    mock_dialog.date = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)

    async def mock_iter_dialogs():
        yield mock_dialog

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.iter_dialogs = mock_iter_dialogs

    with patch.object(wrapper, "_build_client", return_value=mock_client):
        result = wrapper.list_dialogs()

    assert len(result) == 1
    assert result[0]["id"] == "-1001234567890"
    assert result[0]["name"] == "Test Channel"
    assert result[0]["kind"] == "channel"
    assert result[0]["username"] == "testchannel"
    assert result[0]["last_message_date"] == "2026-03-20T12:00:00+00:00"


def test_list_dialogs_labels_saved_messages(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    _write_connected_state(sessions)
    wrapper = TelegramClientWrapper(sessions)

    mock_entity = MagicMock()
    mock_entity.title = None
    mock_entity.username = ""
    mock_entity.broadcast = False
    mock_entity.megagroup = False
    mock_entity.bot = False
    mock_entity.is_self = True

    mock_dialog = MagicMock()
    mock_dialog.id = 123456789
    mock_dialog.entity = mock_entity
    mock_dialog.date = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)

    async def mock_iter_dialogs():
        yield mock_dialog

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.iter_dialogs = mock_iter_dialogs

    with patch.object(wrapper, "_build_client", return_value=mock_client):
        result = wrapper.list_dialogs()

    assert result[0]["name"] == "Saved Messages"


def test_list_dialogs_raises_when_not_connected(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    wrapper = TelegramClientWrapper(sessions)
    # no auth_state.json → not connected
    from services.shared.telegram.errors import TelegramAuthError
    with pytest.raises(TelegramAuthError):
        wrapper.list_dialogs()
