from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

from api.db import get_session_factory
from services.shared.config import load_config
from services.shared.telegram.client import TelegramClientWrapper, TelegramClient
from services.shared.telegram.errors import TelegramAuthError, TelegramOperationalError

try:
    from telethon import events
except Exception:  # pragma: no cover
    events = None


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TriggerSubscription:
    id: str
    workflow_id: str
    node_id: str
    webhook_mode: str
    dialog_id: str
    dialog_name: str
    webhook_url: str
    only_incoming: bool
    ignore_self: bool
    ignore_service_messages: bool
    include_media: bool


class TelegramTriggerRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriptions: dict[str, TriggerSubscription] = {}
        self._client: Any | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.info("Telegram trigger runtime already running")
                return
            logger.info("Starting Telegram trigger runtime thread")
            self._thread = threading.Thread(target=self._run_loop, name="telegram-trigger-runtime", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        logger.info("Stopping Telegram trigger runtime")
        with self._lock:
            loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5)

    def load_from_db(self) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, workflow_id, node_id, webhook_mode, dialog_id, dialog_name, webhook_url,
                           only_incoming, ignore_self, ignore_service_messages, include_media
                    FROM telegram_trigger_subscriptions
                    """
                )
            ).mappings().all()
        finally:
            db.close()

        subscriptions = [TriggerSubscription(**dict(row)) for row in rows]
        with self._lock:
            self._subscriptions = {item.id: item for item in subscriptions}
        logger.info("Loaded %s Telegram trigger subscriptions from database", len(subscriptions))

    def upsert_subscription(self, subscription: TriggerSubscription) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO telegram_trigger_subscriptions (
                        id, workflow_id, node_id, dialog_id, dialog_name, webhook_url,
                        webhook_mode, only_incoming, ignore_self, ignore_service_messages, include_media
                    ) VALUES (
                        :id, :workflow_id, :node_id, :dialog_id, :dialog_name, :webhook_url,
                        :webhook_mode, :only_incoming, :ignore_self, :ignore_service_messages, :include_media
                    )
                    ON CONFLICT (workflow_id, node_id, webhook_mode) DO UPDATE SET
                        id = EXCLUDED.id,
                        dialog_id = EXCLUDED.dialog_id,
                        dialog_name = EXCLUDED.dialog_name,
                        webhook_url = EXCLUDED.webhook_url,
                        only_incoming = EXCLUDED.only_incoming,
                        ignore_self = EXCLUDED.ignore_self,
                        ignore_service_messages = EXCLUDED.ignore_service_messages,
                        include_media = EXCLUDED.include_media,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": subscription.id,
                    "workflow_id": subscription.workflow_id,
                    "node_id": subscription.node_id,
                    "webhook_mode": subscription.webhook_mode,
                    "dialog_id": subscription.dialog_id,
                    "dialog_name": subscription.dialog_name,
                    "webhook_url": subscription.webhook_url,
                    "only_incoming": subscription.only_incoming,
                    "ignore_self": subscription.ignore_self,
                    "ignore_service_messages": subscription.ignore_service_messages,
                    "include_media": subscription.include_media,
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
            "Upserted Telegram trigger subscription workflow=%s node=%s mode=%s dialog=%s",
            subscription.workflow_id,
            subscription.node_id,
            subscription.webhook_mode,
            subscription.dialog_id,
        )

        self.start()

    def delete_subscription(self, *, workflow_id: str, node_id: str, webhook_mode: str) -> None:
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(
                text(
                    "DELETE FROM telegram_trigger_subscriptions WHERE workflow_id = :workflow_id AND node_id = :node_id AND webhook_mode = :webhook_mode"
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
        logger.info("Deleted Telegram trigger subscription workflow=%s node=%s mode=%s", workflow_id, node_id, webhook_mode)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
        loop.create_task(self._listener_main())
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        finally:
            loop.close()
            with self._lock:
                self._loop = None
                self._thread = None

    async def _listener_main(self) -> None:
        while True:
            try:
                logger.info("Telegram trigger listener connecting")
                await self._connect_and_listen_once()
            except Exception as exc:
                logger.exception("Telegram trigger listener crashed: %s", exc)
                await asyncio.sleep(3)

    async def _connect_and_listen_once(self) -> None:
        if events is None:
            raise TelegramOperationalError(
                code="TELETHON_NOT_INSTALLED",
                message="Telethon event support is required for Telegram realtime triggers.",
            )
        config = load_config()
        wrapper = TelegramClientWrapper(Path(config.telegram_session_path))
        api_id, api_hash = wrapper._load_connected_auth()
        client = await wrapper._async_open_event_client(api_id=api_id, api_hash=api_hash)
        self._client = client
        logger.info("Telegram trigger listener connected")

        @client.on(events.NewMessage())
        async def _handler(event):
            await self._handle_new_message(wrapper, client, event)

        try:
            await client.run_until_disconnected()
        finally:
            await client.disconnect()
            self._client = None

    def _event_dialog_id(self, event: Any, chat: Any) -> str:
        event_chat_id = getattr(event, "chat_id", None)
        if event_chat_id is not None:
            return str(event_chat_id)

        raw_chat_id = getattr(chat, "id", None)
        if raw_chat_id is not None:
            return str(raw_chat_id)

        return ""

    async def _handle_new_message(self, wrapper: TelegramClientWrapper, client: Any, event: Any) -> None:
        chat = await event.get_chat()
        if chat is None:
            return
        dialog_id = self._event_dialog_id(event, chat)
        if not dialog_id:
            return

        with self._lock:
            subscriptions = [item for item in self._subscriptions.values() if item.dialog_id == dialog_id]

        logger.info("Telegram trigger received message for dialog=%s matching_subscriptions=%s", dialog_id, len(subscriptions))

        if not subscriptions:
            return

        config = load_config()
        for subscription in subscriptions:
            if subscription.only_incoming and bool(getattr(event.message, "out", False)):
                continue
            if subscription.ignore_self and bool(getattr(event.message, "out", False)):
                continue
            if subscription.ignore_service_messages and bool(getattr(event.message, "action", None) is not None):
                continue

            canonical = await wrapper._async_build_canonical_message(
                client=client,
                source_ref=subscription.dialog_id,
                entity=chat,
                message=event.message,
                workspace_path=config.workspace_path,
                run_id=f"trigger-{subscription.id}-{uuid.uuid4().hex[:8]}",
            )
            if canonical is None:
                continue
            if not subscription.include_media:
                canonical["media_items"] = []

            try:
                async with httpx.AsyncClient(timeout=30) as http_client:
                    response = await http_client.post(subscription.webhook_url, json=canonical)
                    response.raise_for_status()
                logger.info(
                    "Telegram trigger delivered message workflow=%s node=%s dialog=%s",
                    subscription.workflow_id,
                    subscription.node_id,
                    subscription.dialog_id,
                )
            except Exception as exc:
                logger.warning(
                    "Telegram trigger delivery failed for workflow=%s node=%s dialog=%s: %s",
                    subscription.workflow_id,
                    subscription.node_id,
                    subscription.dialog_id,
                    exc,
                )
                continue


telegram_trigger_runtime = TelegramTriggerRuntime()
