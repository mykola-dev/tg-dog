from unittest.mock import MagicMock, patch

from services.shared.telegram.errors import TelegramAuthError, TelegramOperationalError


def test_read_messages_returns_list(stateless_api_client):
    mock_messages = [
        {
            "schema_version": "v1",
            "source_kind": "channel",
            "source_id": "-100123",
            "source_title": "Tech News",
            "message_id": "42",
            "message_timestamp": "2026-03-25T12:00:00+00:00",
            "author_id": None,
            "author_title": None,
            "text": "Hello",
            "reply_to_message_id": None,
            "forwarded_from_source_id": None,
            "is_outbound": False,
            "is_from_self": False,
            "is_service_message": False,
            "media_items": [],
            "ingestion_meta": {"telegram_peer_ref": "-100123"},
        }
    ]
    with patch("api.routers.messages.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.fetch_messages.return_value = mock_messages
        MockWrapper.return_value = instance
        resp = stateless_api_client.post("/messages/read", json={"dialog_ids": ["-100123"], "lookback_hours": 24})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["message_id"] == "42"
    instance.fetch_messages.assert_called_once()
    assert instance.fetch_messages.call_args.kwargs["include_media"] is True


def test_read_messages_returns_503_when_not_connected(stateless_api_client):
    with patch("api.routers.messages.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.fetch_messages.side_effect = TelegramAuthError(code="NOT_CONNECTED")
        MockWrapper.return_value = instance
        resp = stateless_api_client.post("/messages/read", json={"dialog_ids": ["-100123"], "lookback_hours": 24})

    assert resp.status_code == 503
    assert "not connected" in resp.json()["error"].lower()


def test_read_messages_returns_503_on_operational_error(stateless_api_client):
    with patch("api.routers.messages.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.fetch_messages.side_effect = TelegramOperationalError(
            code="TELETHON_NOT_INSTALLED",
            message="Telethon is required for Telegram message reads but is not installed.",
        )
        MockWrapper.return_value = instance
        resp = stateless_api_client.post("/messages/read", json={"dialog_ids": ["-100123"], "lookback_hours": 24})

    assert resp.status_code == 503
    assert resp.json()["code"] == "TELETHON_NOT_INSTALLED"


def test_random_message_returns_item(stateless_api_client):
    mock_message = {
        "schema_version": "v1",
        "source_kind": "channel",
        "source_id": "-100123",
        "source_title": "Tech News",
        "message_id": "42",
        "message_timestamp": "2026-03-25T12:00:00+00:00",
        "author_id": None,
        "author_title": None,
        "text": "Hello",
        "reply_to_message_id": None,
        "forwarded_from_source_id": None,
        "is_outbound": False,
        "is_from_self": False,
        "is_service_message": False,
        "media_items": [],
        "ingestion_meta": {"telegram_peer_ref": "-100123"},
    }
    with patch("api.routers.messages.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.pick_random_message.return_value = mock_message
        MockWrapper.return_value = instance
        resp = stateless_api_client.post(
            "/messages/random",
            json={
                "dialog_id": "-100123",
                "skip_empty_text": True,
                "ignore_self": False,
                "ignore_service_messages": True,
            },
        )

    assert resp.status_code == 200
    assert resp.json()["message_id"] == "42"


def test_random_message_returns_404_when_no_match(stateless_api_client):
    with patch("api.routers.messages.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.pick_random_message.return_value = None
        MockWrapper.return_value = instance
        resp = stateless_api_client.post(
            "/messages/random",
            json={
                "dialog_id": "-100123",
                "skip_empty_text": True,
                "ignore_self": False,
                "ignore_service_messages": True,
            },
        )

    assert resp.status_code == 404
    assert resp.json()["code"] == "RANDOM_MESSAGE_NOT_FOUND"
