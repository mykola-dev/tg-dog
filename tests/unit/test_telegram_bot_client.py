from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.shared.telegram.bot_client import TelegramBotClient
from services.shared.telegram.errors import TelegramDeliveryError


def test_bot_client_sends_plain_text_message() -> None:
    client = TelegramBotClient("123:test-token")

    response = MagicMock()
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "message_id": 42,
            "chat": {"id": -100123},
        },
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response) as mocked_post:
        receipt = client.send_text_chunk(target_id="-100123", chunk_text="Hello", parse_mode="plain_text")

    assert receipt == {"chat_id": "-100123", "message_id": "42"}
    mocked_post.assert_called_once_with(
        "https://api.telegram.org/bot123:test-token/sendMessage",
        json={"chat_id": "-100123", "text": "Hello"},
        timeout=30,
    )


def test_bot_client_sends_markdown_v2_message() -> None:
    client = TelegramBotClient("123:test-token")

    response = MagicMock()
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "message_id": 77,
            "chat": {"id": -100123},
        },
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response) as mocked_post:
        client.send_text_chunk(target_id="-100123", chunk_text="*Hello*", parse_mode="markdown_v2")

    assert mocked_post.call_args.kwargs["json"]["parse_mode"] == "MarkdownV2"


def test_bot_client_surfaces_bot_api_error_description() -> None:
    client = TelegramBotClient("123:test-token")

    response = MagicMock()
    response.is_success = False
    response.status_code = 403
    response.json.return_value = {
        "ok": False,
        "description": "Forbidden: bot is not a member of the channel chat",
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response):
        with pytest.raises(TelegramDeliveryError) as exc_info:
            client.send_text_chunk(target_id="-100123", chunk_text="Hello")

    assert exc_info.value.code == "BOT_DELIVERY_FAILED"
    assert "not a member" in exc_info.value.message


def test_bot_client_wraps_transport_errors() -> None:
    client = TelegramBotClient("123:test-token")

    with patch("services.shared.telegram.bot_client.httpx.post", side_effect=httpx.ConnectError("boom")):
        with pytest.raises(TelegramDeliveryError) as exc_info:
            client.send_text_chunk(target_id="-100123", chunk_text="Hello")

    assert exc_info.value.code == "BOT_API_REQUEST_FAILED"


def test_bot_client_rejects_malformed_token() -> None:
    with pytest.raises(TelegramDeliveryError) as exc_info:
        TelegramBotClient("not-a-real-token")

    assert exc_info.value.code == "BOT_TOKEN_INVALID"


def test_bot_client_maps_not_found_to_invalid_token() -> None:
    client = TelegramBotClient("123:test-token")

    response = MagicMock()
    response.is_success = False
    response.status_code = 404
    response.json.return_value = {
        "ok": False,
        "description": "Not Found",
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response):
        with pytest.raises(TelegramDeliveryError) as exc_info:
            client.send_text_chunk(target_id="-100123", chunk_text="Hello")

    assert exc_info.value.code == "BOT_TOKEN_INVALID"
    assert "invalid" in exc_info.value.message.lower()


def test_bot_client_sends_gif_as_document(tmp_path) -> None:
    client = TelegramBotClient("123:test-token")
    gif_path = tmp_path / "sample.gif"
    gif_path.write_bytes(b"GIF89a")

    response = MagicMock()
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "message_id": 88,
            "chat": {"id": -100123},
        },
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response) as mocked_post:
        receipt = client.send_media_chunk(
            target_id="-100123",
            media_file_ref=str(gif_path),
            media_kind="gif",
            caption_text="Hello gif",
        )

    assert receipt == {"chat_id": "-100123", "message_id": "88"}
    assert mocked_post.call_args.args[0] == "https://api.telegram.org/bot123:test-token/sendDocument"
    assert mocked_post.call_args.kwargs["data"]["caption"] == "Hello gif"


def test_bot_client_forwards_message() -> None:
    client = TelegramBotClient("123:test-token")

    response = MagicMock()
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "message_id": 101,
            "chat": {"id": -100999},
        },
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response) as mocked_post:
        receipt = client.forward_message(target_id="-100999", source_id="-100123", source_message_id="42")

    assert receipt == {"chat_id": "-100999", "message_id": "101"}
    mocked_post.assert_called_once_with(
        "https://api.telegram.org/bot123:test-token/forwardMessage",
        json={"chat_id": "-100999", "from_chat_id": "-100123", "message_id": 42},
        timeout=30,
    )


def test_bot_client_copies_message() -> None:
    client = TelegramBotClient("123:test-token")

    response = MagicMock()
    response.is_success = True
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "result": {
            "message_id": 202,
        },
    }

    with patch("services.shared.telegram.bot_client.httpx.post", return_value=response) as mocked_post:
        receipt = client.copy_message(target_id="-100999", source_id="-100123", source_message_id="42")

    assert receipt == {"chat_id": "-100999", "message_id": "202"}
    mocked_post.assert_called_once_with(
        "https://api.telegram.org/bot123:test-token/copyMessage",
        json={"chat_id": "-100999", "from_chat_id": "-100123", "message_id": 42},
        timeout=30,
    )
