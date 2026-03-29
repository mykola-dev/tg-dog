from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.db import get_session_factory

from api.schemas import (
    TelegramBotCommandConfigRequest,
    TelegramBotCommandConfigResponse,
    TelegramBotCommandSubscriptionRequest,
    TelegramBotCommandSubscriptionResponse,
    TelegramBotCommandUnsubscribeRequest,
)
from api.telegram_bot_command_runtime import BotCommandSubscription, telegram_bot_command_runtime

router = APIRouter(prefix="/telegram-bot-commands")


def _normalize_path_segment(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "%20")


def _load_webhook_path(*, workflow_id: str, node_id: str, node_name: str = "") -> str:
    factory = get_session_factory()
    db = factory()
    try:
        row = None
        if str(node_name or "").strip():
            row = db.execute(
                text(
                    """
                    SELECT "webhookPath"
                    FROM webhook_entity
                    WHERE "workflowId" = :workflow_id AND node = :node_name
                    ORDER BY "pathLength" DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"workflow_id": workflow_id, "node_name": node_name},
            ).mappings().first()
        if not row:
            row = db.execute(
                text(
                    """
                    SELECT "webhookPath"
                    FROM webhook_entity
                    WHERE "workflowId" = :workflow_id AND node = :node_id
                    ORDER BY "pathLength" DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"workflow_id": workflow_id, "node_id": node_id},
            ).mappings().first()
    finally:
        db.close()
    if not row or not row.get("webhookPath"):
        safe_node = _normalize_path_segment(node_name or node_id)
        if safe_node:
            return f"{workflow_id}/{safe_node}/telegram-bot-command-trigger"
        raise RuntimeError(
            f"n8n webhook_entity row not found for workflow={workflow_id} node_id={node_id} node_name={node_name}"
        )
    return str(row["webhookPath"])


@router.post("/subscribe", response_model=TelegramBotCommandSubscriptionResponse)
def subscribe(payload: TelegramBotCommandSubscriptionRequest):
    subscription = BotCommandSubscription(
        id=uuid.uuid4().hex,
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        webhook_mode=payload.webhook_mode,
        command=payload.command,
        require_private_chat=payload.require_private_chat,
        allow_connected_account_only=payload.allow_connected_account_only,
        webhook_path=_load_webhook_path(
            workflow_id=payload.workflow_id,
            node_id=payload.node_id,
            node_name=payload.node_name,
        ),
    )
    try:
        telegram_bot_command_runtime.upsert_subscription(subscription)
        telegram_bot_command_runtime.refresh_webhooks()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {
        "subscription_id": subscription.id,
        "workflow_id": subscription.workflow_id,
        "node_id": subscription.node_id,
        "webhook_mode": subscription.webhook_mode,
        "command": subscription.command,
        "webhook_url": subscription.webhook_path,
    }


@router.post("/unsubscribe")
def unsubscribe(payload: TelegramBotCommandUnsubscribeRequest):
    telegram_bot_command_runtime.delete_subscription(
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        webhook_mode=payload.webhook_mode,
    )
    try:
        telegram_bot_command_runtime.refresh_webhooks()
    except Exception:
        pass
    return {"ok": True}


@router.get("/config", response_model=TelegramBotCommandConfigResponse)
def get_config():
    return {
        "webhook_base_url": telegram_bot_command_runtime.get_effective_webhook_base_url(),
        "source": telegram_bot_command_runtime.get_webhook_base_url_source(),
        "ingress_mode": telegram_bot_command_runtime.get_ingress_mode(),
        "override_active": telegram_bot_command_runtime.is_override_active(),
    }


@router.post("/config", response_model=TelegramBotCommandConfigResponse)
def set_config(payload: TelegramBotCommandConfigRequest):
    if payload.use_env:
        telegram_bot_command_runtime.clear_webhook_override()
    else:
        telegram_bot_command_runtime.set_webhook_override(
            webhook_base_url=payload.webhook_base_url,
            ingress_mode=payload.ingress_mode,
        )
    telegram_bot_command_runtime.refresh_webhooks()
    return {
        "webhook_base_url": telegram_bot_command_runtime.get_effective_webhook_base_url(),
        "source": telegram_bot_command_runtime.get_webhook_base_url_source(),
        "ingress_mode": telegram_bot_command_runtime.get_ingress_mode(),
        "override_active": telegram_bot_command_runtime.is_override_active(),
    }


@router.post("/reload")
def reload_runtime():
    telegram_bot_command_runtime.stop()
    telegram_bot_command_runtime.load_from_db()
    telegram_bot_command_runtime.refresh_webhooks()
    return {
        "webhook_base_url": telegram_bot_command_runtime.get_effective_webhook_base_url(),
        "source": telegram_bot_command_runtime.get_webhook_base_url_source(),
        "ingress_mode": telegram_bot_command_runtime.get_ingress_mode(),
        "override_active": telegram_bot_command_runtime.is_override_active(),
    }


@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    payload = await request.json()
    result = telegram_bot_command_runtime.handle_update(payload, x_telegram_bot_api_secret_token)
    return JSONResponse(status_code=200, content=result)
