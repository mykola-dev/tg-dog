import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

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


def test_pick_random_message_requires_real_telethon_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = tmp_path / "telegram_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _seed_connected_state(sessions)
    workspace = tmp_path / "run_artifacts"
    workspace.mkdir(parents=True, exist_ok=True)

    wrapper = TelegramClientWrapper(sessions)
    monkeypatch.setattr("services.shared.telegram.client.TelegramClient", None)

    with pytest.raises(TelegramOperationalError) as exc_info:
        wrapper.pick_random_message(
            source_ref="-100123",
            workspace_path=workspace,
            run_id="random-run",
            skip_empty_text=True,
            ignore_self=False,
            ignore_service_messages=True,
        )

    assert exc_info.value.code == "TELETHON_NOT_INSTALLED"


def test_collect_supported_media_items_preserves_gif_extension(tmp_path: Path) -> None:
    wrapper = TelegramClientWrapper(tmp_path / "telegram_sessions")
    workspace = tmp_path / "run_artifacts"
    workspace.mkdir(parents=True, exist_ok=True)

    class DocumentAttributeAnimated:
        pass

    document = SimpleNamespace(
        mime_type="image/gif",
        size=1234,
        attributes=[DocumentAttributeAnimated()],
    )
    message = SimpleNamespace(
        id=42,
        photo=None,
        media=SimpleNamespace(document=document),
    )

    class FakeClient:
        async def download_media(self, _message, file: str):
            path = Path(file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"GIF89a")
            return str(path)

    import asyncio

    media_items = asyncio.run(
        wrapper._async_collect_supported_media_items(
            client=FakeClient(),
            source_ref="-100123",
            message=message,
            workspace_path=workspace,
            run_id="random-run",
            include_gifs=True,
        )
    )

    assert len(media_items) == 1
    assert media_items[0]["media_kind"] == "gif"
    assert media_items[0]["mime_type"] == "image/gif"
    assert media_items[0]["file_ref"].endswith(".gif")


def test_async_pick_random_message_uses_runtime_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = tmp_path / "telegram_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _seed_connected_state(sessions)
    workspace = tmp_path / "run_artifacts"
    workspace.mkdir(parents=True, exist_ok=True)

    wrapper = TelegramClientWrapper(sessions)

    message = SimpleNamespace(
        id=42,
        date=SimpleNamespace(astimezone=lambda _tz: SimpleNamespace()),
        out=False,
        action=None,
    )

    class _HistoryProbe:
        total = 1

    class _FakeClient:
        async def disconnect(self) -> None:
            return None

        async def get_entity(self, entity_ref):
            return {"id": entity_ref}

        async def get_messages(self, entity, limit=None, add_offset=None):
            if limit == 0:
                return _HistoryProbe()
            return [message]

    fake_client = _FakeClient()

    async def _fake_open_runtime_client(*, api_id: str, api_hash: str):
        return fake_client

    async def _fake_build_canonical_message(**kwargs):
        assert kwargs["client"] is fake_client
        return {"message_id": "42", "text": "hello", "media_items": []}

    monkeypatch.setattr(wrapper, "_async_open_runtime_client", _fake_open_runtime_client)
    monkeypatch.setattr(wrapper, "_async_build_canonical_message", _fake_build_canonical_message)
    monkeypatch.setattr("services.shared.telegram.client.random.randint", lambda _a, _b: 0)

    result = asyncio.run(
        wrapper._async_pick_random_message(
            api_id="1",
            api_hash="hash",
            source_ref="-100123",
            workspace_path=workspace,
            run_id="random-run",
            skip_empty_text=True,
            ignore_self=False,
            ignore_service_messages=True,
        )
    )

    assert result == {"message_id": "42", "text": "hello", "media_items": []}
