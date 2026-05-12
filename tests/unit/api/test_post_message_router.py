from unittest.mock import MagicMock, patch


def test_post_message_router_returns_sent_receipt(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.send_text_chunk.return_value = {"chat_id": "123", "message_id": "456"}
        MockWrapper.return_value = instance
        resp = stateless_api_client.post(
            "/post/message",
            json={"sender_mode": "user", "target_id": "self", "text": "Hello", "parse_mode": "plain_text"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["delivery_status"] == "sent"
    assert payload["sent_message_refs"][0]["message_id"] == "456"
    instance.send_text_chunk.assert_called_once_with(
        target_id="self",
        chunk_text="Hello",
        parse_mode="plain_text",
    )


def test_post_message_router_accepts_html_for_user_mode(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.send_text_chunk.return_value = {"chat_id": "123", "message_id": "456"}
        MockWrapper.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={"sender_mode": "user", "target_id": "self", "text": "<b>Hello</b>", "parse_mode": "html"},
        )

    assert resp.status_code == 200
    instance.send_text_chunk.assert_called_once_with(
        target_id="self",
        chunk_text="<b>Hello</b>",
        parse_mode="html",
    )


def test_post_message_router_resplits_html_text_safely(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper, patch(
        "api.routers.post_message.split_html_chunks",
        return_value=["<i>Hello</i>", "<i>world</i>"],
    ) as mocked_split:
        instance = MagicMock()
        instance.send_text_chunk.side_effect = [
            {"chat_id": "123", "message_id": "1"},
            {"chat_id": "123", "message_id": "2"},
        ]
        MockWrapper.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={"sender_mode": "user", "target_id": "self", "text": "<i>Hello world</i>", "parse_mode": "html"},
        )

    assert resp.status_code == 200
    mocked_split.assert_called_once_with("<i>Hello world</i>")
    assert [call.kwargs["chunk_text"] for call in instance.send_text_chunk.call_args_list] == ["<i>Hello</i>", "<i>world</i>"]


def test_post_message_router_resplits_existing_html_delivery_chunks_safely(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper, patch(
        "api.routers.post_message.split_html_chunks",
        return_value=["<i>Hello</i>", "<i>world</i>"],
    ) as mocked_split:
        instance = MagicMock()
        instance.send_text_chunk.side_effect = [
            {"chat_id": "123", "message_id": "1"},
            {"chat_id": "123", "message_id": "2"},
        ]
        MockWrapper.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={
                "sender_mode": "user",
                "target_id": "self",
                "text": "ignored",
                "parse_mode": "html",
                "delivery_chunks": ["<i>Hello", "world</i>"],
            },
        )

    assert resp.status_code == 200
    mocked_split.assert_called_once_with("<i>Hello\n\nworld</i>")
    assert [call.kwargs["chunk_text"] for call in instance.send_text_chunk.call_args_list] == ["<i>Hello</i>", "<i>world</i>"]


def test_post_message_router_rejects_unknown_parse_mode(stateless_api_client):
    resp = stateless_api_client.post(
        "/post/message",
        json={"sender_mode": "user", "target_id": "self", "text": "Hello", "parse_mode": "bbcode"},
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "POST_PARSE_MODE_UNSUPPORTED"


def test_post_message_router_rejects_legacy_markdown_parse_mode(stateless_api_client):
    resp = stateless_api_client.post(
        "/post/message",
        json={"sender_mode": "bot", "target_id": "-100123", "text": "Hello", "parse_mode": "markdown"},
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "POST_PARSE_MODE_UNSUPPORTED"


def test_post_message_router_sends_delivery_chunks_without_resplitting(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.send_text_chunk.side_effect = [
            {"chat_id": "123", "message_id": "1"},
            {"chat_id": "123", "message_id": "2"},
        ]
        MockWrapper.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={
                "sender_mode": "user",
                "target_id": "self",
                "text": "ignored because chunks are present",
                "parse_mode": "plain_text",
                "delivery_chunks": ["chunk one", "chunk two"],
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert [entry["message_id"] for entry in payload["sent_message_refs"]] == ["1", "2"]
    assert instance.send_text_chunk.call_count == 2
    for call in instance.send_text_chunk.call_args_list:
        assert call.kwargs["target_id"] == "self"
        assert call.kwargs["parse_mode"] == "plain_text"
        assert "media_file_ref" not in call.kwargs
        assert "media_mime_type" not in call.kwargs
        assert "media_kind" not in call.kwargs
    assert [call.kwargs["chunk_text"] for call in instance.send_text_chunk.call_args_list] == ["chunk one", "chunk two"]


def test_post_message_router_uses_bot_client_for_bot_mode(stateless_api_client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test-token")

    with patch("api.routers.post_message.TelegramBotClient") as MockBotClient:
        instance = MagicMock()
        instance.send_text_chunk.return_value = {"chat_id": "-100123", "message_id": "999"}
        MockBotClient.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={"sender_mode": "bot", "target_id": "-100123", "text": "Hello from bot", "parse_mode": "plain_text"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["sent_message_refs"][0]["message_id"] == "999"
    MockBotClient.assert_called_once_with("123:test-token")


def test_post_message_router_rejects_markdown_v2_alias(stateless_api_client):
    resp = stateless_api_client.post(
        "/post/message",
        json={"sender_mode": "user", "target_id": "self", "text": "Hello", "parse_mode": "markdown_v2"},
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "POST_PARSE_MODE_UNSUPPORTED"


def test_post_message_router_accepts_html_for_bot_mode(stateless_api_client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test-token")

    with patch("api.routers.post_message.TelegramBotClient") as MockBotClient:
        instance = MagicMock()
        instance.send_text_chunk.return_value = {"chat_id": "-100123", "message_id": "999"}
        MockBotClient.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={"sender_mode": "bot", "target_id": "-100123", "text": "<b>Hello from bot</b>", "parse_mode": "html"},
        )

    assert resp.status_code == 200
    instance.send_text_chunk.assert_called_once_with(
        target_id="-100123",
        chunk_text="<b>Hello from bot</b>",
        parse_mode="html",
    )


def test_post_message_router_reports_missing_bot_token(stateless_api_client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    resp = stateless_api_client.post(
        "/post/message",
        json={"sender_mode": "bot", "target_id": "-100123", "text": "Hello from bot", "parse_mode": "plain_text"},
    )

    assert resp.status_code == 503
    assert resp.json()["code"] == "BOT_TOKEN_NOT_CONFIGURED"


def test_post_message_router_sends_media_when_file_ref_present(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.send_text_chunk.return_value = {"chat_id": "123", "message_id": "456"}
        MockWrapper.return_value = instance
        resp = stateless_api_client.post(
            "/post/message",
            json={
                "sender_mode": "user",
                "target_id": "self",
                "text": "caption",
                "parse_mode": "plain_text",
                "media_file_ref": "/tmp/example.gif",
                "media_kind": "gif",
            },
        )

    assert resp.status_code == 200
    instance.send_text_chunk.assert_called_once_with(
        target_id="self",
        chunk_text="caption",
        parse_mode="plain_text",
        media_file_ref="/tmp/example.gif",
        media_mime_type=None,
        media_kind="gif",
    )


def test_post_message_router_forwards_user_message_when_requested(stateless_api_client):
    with patch("api.routers.post_message.TelegramClientWrapper") as MockWrapper:
        instance = MagicMock()
        instance.repost_message.return_value = {"chat_id": "123", "message_id": "456"}
        MockWrapper.return_value = instance
        resp = stateless_api_client.post(
            "/post/message",
            json={
                "sender_mode": "user",
                "delivery_mode": "forward",
                "target_id": "self",
                "text": "ignored",
                "parse_mode": "plain_text",
                "source_id": "-100123",
                "source_message_id": "42",
            },
        )

    assert resp.status_code == 200
    instance.repost_message.assert_called_once_with(
        target_id="self",
        source_id="-100123",
        source_message_id="42",
        mode="forward",
    )


def test_post_message_router_forwards_bot_message_in_auto_mode(stateless_api_client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test-token")

    with patch("api.routers.post_message.TelegramBotClient") as MockBotClient:
        instance = MagicMock()
        instance.forward_message.return_value = {"chat_id": "-100123", "message_id": "999"}
        MockBotClient.return_value = instance

        resp = stateless_api_client.post(
            "/post/message",
            json={
                "sender_mode": "bot",
                "delivery_mode": "auto",
                "target_id": "-100123",
                "text": "Hello from bot",
                "parse_mode": "plain_text",
                "source_id": "-100321",
                "source_message_id": "55",
            },
        )

    assert resp.status_code == 200
    instance.forward_message.assert_called_once_with(
        target_id="-100123",
        source_id="-100321",
        source_message_id="55",
    )


def test_post_message_router_rejects_forward_without_source_message(stateless_api_client):
    resp = stateless_api_client.post(
        "/post/message",
        json={
            "sender_mode": "user",
            "delivery_mode": "forward",
            "target_id": "self",
            "text": "Hello",
            "parse_mode": "plain_text",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "POST_SOURCE_MESSAGE_REQUIRED"
