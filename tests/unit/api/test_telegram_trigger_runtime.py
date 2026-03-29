from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from api.telegram_trigger_runtime import TelegramTriggerRuntime, TriggerSubscription


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    calls: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict):
        self.calls.append((url, json))
        return _FakeResponse()


def _subscription(**overrides) -> TriggerSubscription:
    payload = {
        "id": "sub-1",
        "workflow_id": "workflow-1",
        "node_id": "node-1",
        "webhook_mode": "production",
        "dialog_id": "12345",
        "dialog_name": "Alice",
        "webhook_url": "http://n8n/webhook/test",
        "only_incoming": True,
        "ignore_self": True,
        "ignore_service_messages": True,
        "include_media": True,
    }
    payload.update(overrides)
    return TriggerSubscription(**payload)


def _event(*, out: bool = False, action=None, chat_id: int = 12345):
    chat = SimpleNamespace(id=chat_id)
    message = SimpleNamespace(out=out, action=action, id=99)

    async def get_chat():
        return chat

    return SimpleNamespace(chat_id=chat_id, message=message, get_chat=get_chat)


import pytest


@pytest.mark.parametrize(
    ("subscription_kwargs", "event_kwargs", "should_deliver"),
    [
        ({"only_incoming": True}, {"out": True}, False),
        ({"only_incoming": False, "ignore_self": True}, {"out": True}, False),
        ({"only_incoming": False, "ignore_self": False}, {"out": True}, True),
        ({"ignore_service_messages": True}, {"action": object()}, False),
        ({"ignore_service_messages": False}, {"action": object()}, True),
    ],
)
def test_handle_new_message_applies_subscription_filters(monkeypatch, tmp_path: Path, subscription_kwargs, event_kwargs, should_deliver):
    runtime = TelegramTriggerRuntime()
    subscription = _subscription(**subscription_kwargs)
    runtime._subscriptions = {subscription.id: subscription}

    wrapper = MagicMock()

    async def fake_build_canonical_message(**kwargs):
        return {
            "schema_version": "v1",
            "source_kind": "contact",
            "source_id": subscription.dialog_id,
            "source_title": "Alice",
            "message_id": "99",
            "message_timestamp": "2026-03-26T00:00:00+00:00",
            "author_id": "1",
            "author_title": None,
            "text": "hello",
            "reply_to_message_id": None,
            "forwarded_from_source_id": None,
            "is_outbound": bool(event_kwargs.get("out", False)),
            "is_from_self": bool(event_kwargs.get("out", False)),
            "is_service_message": bool(event_kwargs.get("action") is not None),
            "media_items": [
                {
                    "media_kind": "image",
                    "file_ref": "/tmp/example.png",
                    "ocr_status": "pending",
                }
            ],
            "ingestion_meta": {"telegram_peer_ref": subscription.dialog_id},
        }

    wrapper._async_build_canonical_message.side_effect = fake_build_canonical_message
    monkeypatch.setattr("api.telegram_trigger_runtime.load_config", lambda: SimpleNamespace(workspace_path=tmp_path))
    monkeypatch.setattr("api.telegram_trigger_runtime.httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = []

    asyncio.run(runtime._handle_new_message(wrapper, MagicMock(), _event(**event_kwargs)))

    if should_deliver:
        assert len(_FakeAsyncClient.calls) == 1
        assert _FakeAsyncClient.calls[0][0] == subscription.webhook_url
    else:
        assert _FakeAsyncClient.calls == []


def test_handle_new_message_strips_media_when_disabled(monkeypatch, tmp_path: Path):
    runtime = TelegramTriggerRuntime()
    subscription = _subscription(include_media=False)
    runtime._subscriptions = {subscription.id: subscription}

    wrapper = MagicMock()

    async def fake_build_canonical_message(**kwargs):
        return {
            "schema_version": "v1",
            "source_kind": "contact",
            "source_id": subscription.dialog_id,
            "source_title": "Alice",
            "message_id": "99",
            "message_timestamp": "2026-03-26T00:00:00+00:00",
            "author_id": "1",
            "author_title": None,
            "text": "hello",
            "reply_to_message_id": None,
            "forwarded_from_source_id": None,
            "is_outbound": False,
            "is_from_self": False,
            "is_service_message": False,
            "media_items": [{"media_kind": "image", "file_ref": "/tmp/example.png", "ocr_status": "pending"}],
            "ingestion_meta": {"telegram_peer_ref": subscription.dialog_id},
        }

    wrapper._async_build_canonical_message.side_effect = fake_build_canonical_message
    monkeypatch.setattr("api.telegram_trigger_runtime.load_config", lambda: SimpleNamespace(workspace_path=tmp_path))
    monkeypatch.setattr("api.telegram_trigger_runtime.httpx.AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = []

    asyncio.run(runtime._handle_new_message(wrapper, MagicMock(), _event()))

    assert len(_FakeAsyncClient.calls) == 1
    assert _FakeAsyncClient.calls[0][1]["media_items"] == []


def test_event_dialog_id_prefers_event_chat_id():
    runtime = TelegramTriggerRuntime()
    event = SimpleNamespace(chat_id=-100123)
    chat = SimpleNamespace(id=123)
    assert runtime._event_dialog_id(event, chat) == "-100123"


def test_upsert_subscription_starts_runtime(monkeypatch):
    runtime = TelegramTriggerRuntime()
    started = {"value": 0}

    def fake_start():
        started["value"] += 1

    monkeypatch.setattr(runtime, "start", fake_start)

    class _FakeDb:
        def execute(self, *args, **kwargs):
            return None

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("api.telegram_trigger_runtime.get_session_factory", lambda: lambda: _FakeDb())

    runtime.upsert_subscription(_subscription())

    assert started["value"] == 1


def test_upsert_keeps_separate_test_and_production_subscriptions(monkeypatch):
    runtime = TelegramTriggerRuntime()
    monkeypatch.setattr(runtime, "start", lambda: None)

    executed_params = []

    class _FakeDb:
        def execute(self, *args, **kwargs):
            executed_params.append(kwargs)
            return None

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("api.telegram_trigger_runtime.get_session_factory", lambda: lambda: _FakeDb())

    runtime.upsert_subscription(_subscription(id="sub-prod", webhook_mode="production", webhook_url="http://n8n/webhook/live"))
    runtime.upsert_subscription(_subscription(id="sub-test", webhook_mode="test", webhook_url="http://n8n/webhook-test/live"))

    assert len(runtime._subscriptions) == 2
    assert {item.webhook_mode for item in runtime._subscriptions.values()} == {"production", "test"}
