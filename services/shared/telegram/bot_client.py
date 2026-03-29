from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from services.shared.telegram.errors import TelegramDeliveryError


@dataclass(slots=True)
class TelegramBotClient:
    token: str
    base_url: str = "https://api.telegram.org"

    def __post_init__(self) -> None:
        if not self.token or ":" not in self.token:
            raise TelegramDeliveryError(
                code="BOT_TOKEN_INVALID",
                message="Telegram bot token is invalid or malformed",
                retryable=False,
            )

    def _api_url(self, method: str) -> str:
        return f"{self.base_url}/bot{self.token}/{method}"

    def _parse_bot_api_result_ref(self, response: httpx.Response, body: dict, *, target_id: str) -> dict[str, str]:
        if not response.is_success or not body.get("ok"):
            description = str(body.get("description") or f"HTTP {response.status_code}")
            code = "BOT_DELIVERY_FAILED"
            if response.status_code == 404 and description == "Not Found":
                code = "BOT_TOKEN_INVALID"
                description = "Telegram bot token is invalid or rejected by Bot API"
            raise TelegramDeliveryError(
                code=code,
                message=description,
                retryable=response.status_code >= 500,
            )

        result = body.get("result") or {}
        chat = result.get("chat") or {}
        return {
            "chat_id": str(chat.get("id", target_id)),
            "message_id": str(result.get("message_id", "")),
        }

    def send_text_chunk(self, *, target_id: str, chunk_text: str, parse_mode: str = "plain_text") -> dict[str, str]:
        payload: dict[str, object] = {
            "chat_id": target_id,
            "text": chunk_text,
        }
        if parse_mode == "markdown_v2":
            payload["parse_mode"] = "MarkdownV2"

        try:
            response = httpx.post(self._api_url("sendMessage"), json=payload, timeout=30)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_REQUEST_FAILED",
                message=f"Telegram Bot API request failed: {exc}",
                retryable=True,
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_INVALID_RESPONSE",
                message=f"Telegram Bot API returned invalid JSON (status {response.status_code})",
                retryable=True,
            ) from exc

        return self._parse_bot_api_result_ref(response, body, target_id=target_id)

    def send_media_chunk(
        self,
        *,
        target_id: str,
        media_file_ref: str,
        media_kind: str | None = None,
        caption_text: str = "",
        parse_mode: str = "plain_text",
    ) -> dict[str, str]:
        payload: dict[str, object] = {
            "chat_id": target_id,
        }
        if caption_text:
            payload["caption"] = caption_text
        if parse_mode == "markdown_v2":
            payload["parse_mode"] = "MarkdownV2"

        endpoint = "sendDocument"
        file_name = Path(media_file_ref).name or "attachment.bin"
        if media_kind == "image":
            endpoint = "sendPhoto"
            files = {"photo": (file_name, open(media_file_ref, "rb"))}
        else:
            files = {"document": (file_name, open(media_file_ref, "rb"))}

        try:
            response = httpx.post(self._api_url(endpoint), data=payload, files=files, timeout=30)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_REQUEST_FAILED",
                message=f"Telegram Bot API request failed: {exc}",
                retryable=True,
            ) from exc
        finally:
            for _, file_info in files.items():
                file_info[1].close()

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_INVALID_RESPONSE",
                message=f"Telegram Bot API returned invalid JSON (status {response.status_code})",
                retryable=True,
            ) from exc

        return self._parse_bot_api_result_ref(response, body, target_id=target_id)

    def forward_message(
        self,
        *,
        target_id: str,
        source_id: str,
        source_message_id: str,
    ) -> dict[str, str]:
        payload = {
            "chat_id": target_id,
            "from_chat_id": source_id,
            "message_id": int(source_message_id),
        }

        try:
            response = httpx.post(self._api_url("forwardMessage"), json=payload, timeout=30)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_REQUEST_FAILED",
                message=f"Telegram Bot API request failed: {exc}",
                retryable=True,
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_INVALID_RESPONSE",
                message=f"Telegram Bot API returned invalid JSON (status {response.status_code})",
                retryable=True,
            ) from exc

        return self._parse_bot_api_result_ref(response, body, target_id=target_id)

    def copy_message(
        self,
        *,
        target_id: str,
        source_id: str,
        source_message_id: str,
    ) -> dict[str, str]:
        payload = {
            "chat_id": target_id,
            "from_chat_id": source_id,
            "message_id": int(source_message_id),
        }

        try:
            response = httpx.post(self._api_url("copyMessage"), json=payload, timeout=30)
        except httpx.HTTPError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_REQUEST_FAILED",
                message=f"Telegram Bot API request failed: {exc}",
                retryable=True,
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError(
                code="BOT_API_INVALID_RESPONSE",
                message=f"Telegram Bot API returned invalid JSON (status {response.status_code})",
                retryable=True,
            ) from exc

        if not response.is_success or not body.get("ok"):
            description = str(body.get("description") or f"HTTP {response.status_code}")
            code = "BOT_DELIVERY_FAILED"
            if response.status_code == 404 and description == "Not Found":
                code = "BOT_TOKEN_INVALID"
                description = "Telegram bot token is invalid or rejected by Bot API"
            raise TelegramDeliveryError(
                code=code,
                message=description,
                retryable=response.status_code >= 500,
            )

        return {
            "chat_id": str(target_id),
            "message_id": str(body.get("result", {}).get("message_id", "")),
        }
