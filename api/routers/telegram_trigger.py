from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import (
    TelegramTriggerSubscriptionRequest,
    TelegramTriggerSubscriptionResponse,
    TelegramTriggerUnsubscribeRequest,
)
from api.telegram_trigger_runtime import TriggerSubscription, telegram_trigger_runtime

router = APIRouter(prefix="/telegram-trigger")


@router.post("/subscribe", response_model=TelegramTriggerSubscriptionResponse)
def subscribe(payload: TelegramTriggerSubscriptionRequest):
    subscription = TriggerSubscription(
        id=uuid.uuid4().hex,
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        webhook_mode=payload.webhook_mode,
        dialog_id=payload.dialog_id,
        dialog_name=payload.dialog_name,
        webhook_url=payload.webhook_url,
        only_incoming=payload.only_incoming,
        ignore_self=payload.ignore_self,
        ignore_service_messages=payload.ignore_service_messages,
        include_media=payload.include_media,
    )
    try:
        telegram_trigger_runtime.upsert_subscription(subscription)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {
        "subscription_id": subscription.id,
        "workflow_id": subscription.workflow_id,
        "node_id": subscription.node_id,
        "webhook_mode": subscription.webhook_mode,
        "dialog_id": subscription.dialog_id,
        "webhook_url": subscription.webhook_url,
    }


@router.post("/unsubscribe")
def unsubscribe(payload: TelegramTriggerUnsubscribeRequest):
    telegram_trigger_runtime.delete_subscription(
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        webhook_mode=payload.webhook_mode,
    )
    return {"ok": True}
