from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DialogItem(BaseModel):
    id: str
    name: str
    kind: str
    username: str
    last_message_date: datetime | None = None
    can_send: bool = False


class MessageReadRequest(BaseModel):
    dialog_ids: list[str] = Field(default_factory=list)
    lookback_hours: int = Field(default=24, ge=1, le=24 * 30)
    include_media: bool = True


class RandomMessageRequest(BaseModel):
    dialog_id: str
    skip_empty_text: bool = True
    ignore_self: bool = False
    ignore_service_messages: bool = True


class TelegramTriggerSubscriptionRequest(BaseModel):
    workflow_id: str
    node_id: str
    webhook_mode: str = "production"
    dialog_id: str
    dialog_name: str = ""
    webhook_url: str
    only_incoming: bool = True
    ignore_self: bool = True
    ignore_service_messages: bool = True
    include_media: bool = True


class TelegramTriggerSubscriptionResponse(BaseModel):
    subscription_id: str
    workflow_id: str
    node_id: str
    webhook_mode: str
    dialog_id: str
    webhook_url: str


class TelegramTriggerUnsubscribeRequest(BaseModel):
    workflow_id: str
    node_id: str
    webhook_mode: str = "production"


class TelegramBotCommandSubscriptionRequest(BaseModel):
    workflow_id: str
    node_id: str
    node_name: str = ""
    webhook_mode: str = "production"
    command: str
    require_private_chat: bool = True
    allow_connected_account_only: bool = True


class TelegramBotCommandSubscriptionResponse(BaseModel):
    subscription_id: str
    workflow_id: str
    node_id: str
    webhook_mode: str
    command: str
    webhook_url: str


class TelegramBotCommandUnsubscribeRequest(BaseModel):
    workflow_id: str
    node_id: str
    webhook_mode: str = "production"


class TelegramBotCommandConfigRequest(BaseModel):
    webhook_base_url: str = ""
    ingress_mode: str = ""
    use_env: bool = False


class TelegramBotCommandConfigResponse(BaseModel):
    webhook_base_url: str = ""
    source: str = "unset"
    ingress_mode: str = "webhook"
    override_active: bool = False


class CanonicalMediaItemSchema(BaseModel):
    media_kind: str
    file_ref: str
    mime_type: str | None = None
    size_bytes: int | None = None
    ocr_status: str = "pending"
    ocr_text: str | None = None
    ocr_confidence_hint: float | None = None
    ocr_error_code: str | None = None
    ocr_error_message: str | None = None


class CanonicalMessageItem(BaseModel):
    schema_version: str = "v1"
    source_kind: str
    source_id: str
    source_title: str
    message_id: str
    message_timestamp: datetime
    author_id: str | None = None
    author_title: str | None = None
    text: str | None = None
    reply_to_message_id: str | None = None
    forwarded_from_source_id: str | None = None
    is_outbound: bool
    is_from_self: bool
    is_service_message: bool
    media_items: list[CanonicalMediaItemSchema] = Field(default_factory=list)
    ocr_text: str | None = None
    ingestion_meta: dict[str, Any] = Field(default_factory=dict)


class MessageOCREnrichRequest(BaseModel):
    messages: list[CanonicalMessageItem] = Field(default_factory=list)


class AITextRequest(BaseModel):
    prompt: str = Field(min_length=1)
    command_template: str = Field(default='opencode run -m opencode/minimax-m2.5-free "{prompt}"')
    system_prompt: str = Field(default="")


class ProviderAttemptSchema(BaseModel):
    provider_id: str
    success: bool
    details: dict[str, Any] | str | None = None


class AITextResponse(BaseModel):
    output_text: str
    provider_id: str
    provider_attempts: list[ProviderAttemptSchema] = Field(default_factory=list)
    raw_output: str | None = None


class PostMessageRequest(BaseModel):
    sender_mode: str = Field(default="user")
    delivery_mode: str = Field(default="auto")
    target_id: str = "self"
    text: str = ""
    parse_mode: str = Field(default="plain_text")
    delivery_chunks: list[str] = Field(default_factory=list)
    media_file_ref: str | None = None
    media_mime_type: str | None = None
    media_kind: str | None = None
    source_id: str | None = None
    source_message_id: str | None = None


class PostMessageResponse(BaseModel):
    delivery_status: str
    target_id: str
    sent_message_refs: list[dict[str, str]] = Field(default_factory=list)
