from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import text

from api.db import get_session_factory
from services.shared.config import load_config
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.bot_client import TelegramBotClient
from services.shared.telegram.errors import TelegramOperationalError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotCommandSubscription:
    id: str
    workflow_id: str
    node_id: str
    webhook_mode: str
    command: str
    require_private_chat: bool
    allow_connected_account_only: bool
    webhook_path: str
    updated_at: datetime | None = None

    def normalized_command(self) -> str:
        command = str(self.command or "").strip()
        if not command:
            return ""
        if not command.startswith("/"):
            command = f"/{command}"
        return command.lower()

class TelegramBotCommandRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: dict[str, BotCommandSubscription] = {}
        self._override_enabled = False
        self._webhook_base_url_override: str | None = None
        self._webhook_mode_override: str | None = None
        self._poll_thread: threading.Thread | None = None
        self._poll_stop_event = threading.Event()
        self._poll_offset: int | None = None
        self._poll_token: str | None = None
        self._poll_restart_token: str | None = None

    def load_from_db(self) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, workflow_id, node_id, webhook_mode, command, require_private_chat, allow_connected_account_only, webhook_path, updated_at
                    FROM telegram_bot_command_subscriptions
                    """
                )
            ).mappings().all()
            config_row = db.execute(
                text(
                    """
                    SELECT webhook_base_url
                         , webhook_mode
                         , override_enabled
                    FROM telegram_bot_command_config
                    WHERE id = 1
                    """
                )
            ).mappings().first()
        finally:
            db.close()

        subscriptions = [BotCommandSubscription(**dict(row)) for row in rows]
        with self._lock:
            self._subscriptions = {item.id: item for item in subscriptions}
            self._override_enabled = bool(config_row["override_enabled"]) if config_row else False
            self._webhook_base_url_override = self._normalize_base_url(
                config_row["webhook_base_url"] if config_row else None
            )
            self._webhook_mode_override = self._normalize_webhook_mode(
                config_row["webhook_mode"] if config_row else None
            )
        logger.info("Loaded %s Telegram bot command subscriptions from database", len(subscriptions))

    def stop(self) -> None:
        self._stop_polling()

    def upsert_subscription(self, subscription: BotCommandSubscription) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO telegram_bot_command_subscriptions (
                        id, workflow_id, node_id, webhook_mode, command, require_private_chat, allow_connected_account_only, webhook_path
                    ) VALUES (
                        :id, :workflow_id, :node_id, :webhook_mode, :command, :require_private_chat, :allow_connected_account_only, :webhook_path
                    )
                    ON CONFLICT (workflow_id, node_id, webhook_mode) DO UPDATE SET
                        id = EXCLUDED.id,
                        command = EXCLUDED.command,
                        require_private_chat = EXCLUDED.require_private_chat,
                        allow_connected_account_only = EXCLUDED.allow_connected_account_only,
                        webhook_path = EXCLUDED.webhook_path,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": subscription.id,
                    "workflow_id": subscription.workflow_id,
                    "node_id": subscription.node_id,
                    "webhook_mode": subscription.webhook_mode,
                    "command": subscription.command,
                    "require_private_chat": subscription.require_private_chat,
                    "allow_connected_account_only": subscription.allow_connected_account_only,
                    "webhook_path": subscription.webhook_path,
                },
            )
            db.commit()
        finally:
            db.close()

        with self._lock:
            existing = next(
                (
                    item_id
                    for item_id, item in self._subscriptions.items()
                    if item.workflow_id == subscription.workflow_id
                    and item.node_id == subscription.node_id
                    and item.webhook_mode == subscription.webhook_mode
                ),
                None,
            )
            if existing and existing != subscription.id:
                self._subscriptions.pop(existing, None)
            self._subscriptions[subscription.id] = subscription

        logger.info(
            "Upserted Telegram bot command subscription workflow=%s node=%s mode=%s command=%s",
            subscription.workflow_id,
            subscription.node_id,
            subscription.webhook_mode,
            subscription.command,
        )

    def delete_subscription(self, *, workflow_id: str, node_id: str, webhook_mode: str) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(
                text(
                    "DELETE FROM telegram_bot_command_subscriptions WHERE workflow_id = :workflow_id AND node_id = :node_id AND webhook_mode = :webhook_mode"
                ),
                {"workflow_id": workflow_id, "node_id": node_id, "webhook_mode": webhook_mode},
            )
            db.commit()
        finally:
            db.close()

        with self._lock:
            for subscription_id, item in list(self._subscriptions.items()):
                if item.workflow_id == workflow_id and item.node_id == node_id and item.webhook_mode == webhook_mode:
                    self._subscriptions.pop(subscription_id, None)

        logger.info(
            "Deleted Telegram bot command subscription workflow=%s node=%s mode=%s",
            workflow_id,
            node_id,
            webhook_mode,
        )

    def refresh_webhooks(self) -> None:
        config = load_config()
        token = config.telegram_bot_token
        if not token:
            self._stop_polling()
            logger.info("Telegram bot command runtime skipped webhook refresh because TELEGRAM_BOT_TOKEN is not configured")
            return

        with self._lock:
            subscriptions = list(self._subscriptions.values())

        if not subscriptions:
            self._stop_polling()
            self._delete_webhook(token)
            return

        webhook_base_url = self.get_effective_webhook_base_url()
        if self.get_ingress_mode() == "polling" or not webhook_base_url:
            self._delete_webhook(token, drop_pending_updates=False)
            self._start_polling(token)
            logger.info(
                "Telegram bot command runtime switched to Bot API polling subscriptions=%s",
                len(subscriptions),
            )
            return

        self._stop_polling()

        allowed_updates = ["message"]
        payload = {
            "url": f"{webhook_base_url}/telegram-bot-commands/webhook",
            "allowed_updates": allowed_updates,
            "secret_token": self._webhook_secret(token),
        }

        try:
            response = httpx.post(
                TelegramBotClient(token=token)._api_url("setWebhook"),
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise TelegramOperationalError(
                code="BOT_WEBHOOK_REQUEST_FAILED",
                message=f"Telegram Bot API webhook request failed: {exc}",
            ) from exc
        except ValueError as exc:
            raise TelegramOperationalError(
                code="BOT_WEBHOOK_INVALID_RESPONSE",
                message="Telegram Bot API returned invalid JSON while refreshing webhook",
            ) from exc

        if not body.get("ok"):
            raise TelegramOperationalError(
                code="BOT_WEBHOOK_REJECTED",
                message=str(body.get("description") or "Telegram Bot API rejected webhook registration"),
            )

        logger.info(
            "Telegram bot command webhook registered subscriptions=%s webhook=%s",
            len(subscriptions),
            payload["url"],
        )

    def handle_update(self, update: dict[str, Any], secret_token: str | None) -> dict[str, Any]:
        with self._lock:
            subscriptions = list(self._subscriptions.values())

        if not subscriptions:
            return {"delivered": 0, "matched": 0}

        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict):
            return {"delivered": 0, "matched": 0}

        text_value = str(message.get("text") or "").strip()
        if not text_value:
            return {"delivered": 0, "matched": 0}

        command = self._extract_command(text_value)
        if not command:
            return {"delivered": 0, "matched": 0}

        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_type = str(chat.get("type") or "")
        user_id = str(sender.get("id") or "")
        connected_user_id = self._connected_account_user_id()

        matched = 0
        delivered = 0
        expected_secret = self._webhook_secret(load_config().telegram_bot_token or "")
        if secret_token and secret_token != expected_secret:
            logger.warning("Telegram bot command ignored due to invalid secret token")
            return {"delivered": 0, "matched": 0}
        for subscription in subscriptions:
            if subscription.webhook_mode != "production":
                continue
            if subscription.normalized_command() != command:
                continue
            if subscription.allow_connected_account_only:
                if not connected_user_id or user_id != connected_user_id:
                    continue
            if subscription.require_private_chat and chat_type != "private":
                continue

            matched += 1
            payload = {
                "schema_version": "v1",
                "trigger_kind": "telegram_bot_command",
                "workflow_id": subscription.workflow_id,
                "node_id": subscription.node_id,
                "command": command,
                "command_text": text_value,
                "chat_id": str(chat.get("id") or ""),
                "chat_type": chat_type,
                "message_id": str(message.get("message_id") or ""),
                "message_timestamp": int(message.get("date") or 0),
                "user_id": user_id,
                "username": str(sender.get("username") or ""),
                "first_name": str(sender.get("first_name") or ""),
                "last_name": str(sender.get("last_name") or ""),
                "raw_update": update,
            }
            try:
                response = httpx.post(self._internal_webhook_url(subscription), json=payload, timeout=30)
                response.raise_for_status()
                delivered += 1
            except Exception as exc:
                logger.warning(
                    "Telegram bot command delivery failed workflow=%s node=%s command=%s: %s",
                    subscription.workflow_id,
                    subscription.node_id,
                    subscription.command,
                    exc,
                )

        if matched == 0:
            logger.warning(
                "Telegram bot command ignored command=%s user_id=%s connected_user_id=%s chat_id=%s chat_type=%s subscriptions=%s",
                command,
                user_id,
                connected_user_id,
                str(chat.get("id") or ""),
                chat_type,
                len(subscriptions),
            )
        elif delivered != matched:
            logger.warning(
                "Telegram bot command partially delivered command=%s matched=%s delivered=%s",
                command,
                matched,
                delivered,
            )

        return {"delivered": delivered, "matched": matched}

    def get_effective_webhook_base_url(self) -> str:
        with self._lock:
            override_enabled = self._override_enabled
            override = self._webhook_base_url_override
            mode_override = self._webhook_mode_override
        if not override_enabled:
            return self._normalize_base_url(load_config().telegram_bot_webhook_base_url)
        if mode_override == "polling":
            return ""
        if override:
            return override
        return self._normalize_base_url(load_config().telegram_bot_webhook_base_url)

    def get_ingress_mode(self) -> str:
        with self._lock:
            override_enabled = self._override_enabled
            mode_override = self._webhook_mode_override
        if not override_enabled:
            return "webhook" if self._normalize_base_url(load_config().telegram_bot_webhook_base_url) else "polling"
        if mode_override in {"webhook", "polling"}:
            return mode_override
        return "webhook" if self._normalize_base_url(load_config().telegram_bot_webhook_base_url) else "polling"

    def get_webhook_base_url_source(self) -> str:
        with self._lock:
            override_enabled = self._override_enabled
            override = self._webhook_base_url_override
            mode_override = self._webhook_mode_override
        if not override_enabled:
            if self._normalize_base_url(load_config().telegram_bot_webhook_base_url):
                return "env"
            return "unset"
        if mode_override == "polling":
            return "database"
        if override:
            return "database"
        if self._normalize_base_url(load_config().telegram_bot_webhook_base_url):
            return "env"
        return "unset"

    def is_override_active(self) -> bool:
        with self._lock:
            return self._override_enabled

    def set_webhook_override(self, *, webhook_base_url: str, ingress_mode: str = "") -> None:
        normalized = self._normalize_base_url(webhook_base_url)
        webhook_mode = self._normalize_webhook_mode(ingress_mode) or ("polling" if not normalized else "webhook")
        if webhook_mode == "webhook" and not normalized:
            raise TelegramOperationalError(
                code="BOT_WEBHOOK_BASE_URL_MISSING",
                message="webhook ingress_mode requires a non-empty webhook_base_url",
            )
        if webhook_mode == "polling":
            normalized = ""
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO telegram_bot_command_config (id, webhook_base_url, webhook_mode, override_enabled)
                    VALUES (1, :webhook_base_url, :webhook_mode, TRUE)
                    ON CONFLICT (id) DO UPDATE SET
                        webhook_base_url = EXCLUDED.webhook_base_url,
                        webhook_mode = EXCLUDED.webhook_mode,
                        override_enabled = EXCLUDED.override_enabled,
                        updated_at = NOW()
                    """
                ),
                {"webhook_base_url": normalized or None, "webhook_mode": webhook_mode},
            )
            db.commit()
        finally:
            db.close()

        with self._lock:
            self._override_enabled = True
            self._webhook_base_url_override = normalized or None
            self._webhook_mode_override = webhook_mode

    def clear_webhook_override(self) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO telegram_bot_command_config (id, webhook_base_url, webhook_mode, override_enabled)
                    VALUES (1, NULL, 'webhook', FALSE)
                    ON CONFLICT (id) DO UPDATE SET
                        override_enabled = FALSE,
                        updated_at = NOW()
                    """
                )
            )
            db.commit()
        finally:
            db.close()

        with self._lock:
            self._override_enabled = False
            self._webhook_base_url_override = None
            self._webhook_mode_override = None

    def _extract_command(self, text_value: str) -> str:
        token = text_value.split(None, 1)[0].strip().lower()
        if not token.startswith("/"):
            return ""
        if "@" in token:
            token = token.split("@", 1)[0]
        return token

    def _webhook_secret(self, token: str) -> str:
        return sha256(f"tgdog-bot-command:{token}".encode("utf-8")).hexdigest()

    def _delete_webhook(self, token: str, *, drop_pending_updates: bool = False) -> None:
        try:
            response = httpx.post(
                TelegramBotClient(token=token)._api_url("deleteWebhook"),
                json={"drop_pending_updates": drop_pending_updates},
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Telegram bot command webhook delete failed: %s", exc)

    def _normalize_base_url(self, value: str | None) -> str:
        return str(value or "").strip().rstrip("/")

    def _normalize_webhook_mode(self, value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        if normalized in {"webhook", "polling"}:
            return normalized
        return None

    def _internal_webhook_url(self, subscription: BotCommandSubscription) -> str:
        base = "http://n8n:5678"
        path = str(subscription.webhook_path or "").lstrip("/")
        # n8n stores webhookPath with literal %20 for node names containing spaces.
        # Quote the path once more so the HTTP request preserves those percent sequences.
        return f"{base}/webhook/{quote(path, safe='/')}"

    def _connected_account_user_id(self) -> str:
        try:
            config = load_config()
            wrapper = TelegramClientWrapper(config.telegram_session_path)
            state = wrapper._load_json(wrapper.state_file)
            account_profile = state.get("account_profile") if isinstance(state, dict) else None
            if not isinstance(account_profile, dict):
                return ""
            return str(account_profile.get("id") or "").strip()
        except Exception:
            return ""

    def _start_polling(self, token: str) -> None:
        with self._lock:
            thread = self._poll_thread
            if thread and thread.is_alive():
                if self._poll_token == token and not self._poll_stop_event.is_set():
                    return
                self._poll_restart_token = token
                self._poll_stop_event.set()
                return
            self._poll_stop_event = threading.Event()
            self._poll_token = token
            self._poll_restart_token = None
            self._poll_thread = threading.Thread(
                target=self._poll_updates_loop,
                args=(token, self._poll_stop_event),
                name="telegram-bot-command-poll",
                daemon=True,
            )
            self._poll_thread.start()

    def _stop_polling(self) -> None:
        with self._lock:
            thread = self._poll_thread
            stop_event = self._poll_stop_event
            self._poll_restart_token = None
            if not thread:
                self._poll_token = None
                self._poll_stop_event = threading.Event()
                return
        if not thread:
            return
        stop_event.set()
        thread.join(timeout=1)
        if not thread.is_alive():
            self._finish_poll_thread(thread)

    def _finish_poll_thread(self, thread: threading.Thread) -> str | None:
        with self._lock:
            if self._poll_thread is not thread:
                return None
            restart_token = self._poll_restart_token
            self._poll_thread = None
            self._poll_token = None
            self._poll_restart_token = None
            self._poll_stop_event = threading.Event()
            return restart_token

    def _poll_updates_loop(self, token: str, stop_event: threading.Event) -> None:
        client = TelegramBotClient(token=token)
        logger.info("Telegram bot command polling started")
        while not stop_event.is_set():
            payload: dict[str, Any] = {
                "timeout": 20,
                "allowed_updates": ["message"],
            }
            with self._lock:
                if self._poll_offset is not None:
                    payload["offset"] = self._poll_offset
            try:
                response = httpx.post(client._api_url("getUpdates"), json=payload, timeout=35)
                response.raise_for_status()
                body = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 409:
                    logger.warning("Telegram bot command polling conflict detected, backing off before retry")
                    stop_event.wait(5)
                    continue
                logger.warning("Telegram bot command polling request failed: %s", exc)
                stop_event.wait(2)
                continue
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Telegram bot command polling request failed: %s", exc)
                stop_event.wait(2)
                continue

            if not body.get("ok"):
                logger.warning(
                    "Telegram bot command polling rejected by Bot API: %s",
                    body.get("description") or body,
                )
                stop_event.wait(2)
                continue

            updates = body.get("result") or []
            if not isinstance(updates, list):
                stop_event.wait(1)
                continue

            for update in updates:
                if not isinstance(update, dict):
                    continue
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    with self._lock:
                        self._poll_offset = max(self._poll_offset or 0, update_id + 1)
                try:
                    self.handle_update(update, None)
                except Exception as exc:
                    logger.warning("Telegram bot command polling update handling failed: %s", exc)

        logger.info("Telegram bot command polling stopped")
        restart_token = self._finish_poll_thread(threading.current_thread())
        if restart_token:
            self._start_polling(restart_token)


telegram_bot_command_runtime = TelegramBotCommandRuntime()
