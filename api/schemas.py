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


class CleanupRequest(BaseModel):
    messages: list[CanonicalMessageItem] = Field(default_factory=list)
    mode: str = Field(default="combined")
    output_format: str = Field(default="markdown")
    include_source_title: bool = True
    include_timestamp: bool = True
    include_ocr_text: bool = True
    max_characters_per_message: int = Field(default=1200, ge=80, le=10000)


class FormattedMessageItem(BaseModel):
    source_id: str
    message_id: str
    formatted_text: str


class CleanupResponse(BaseModel):
    mode: str
    output_format: str
    message_count: int
    combined_text: str | None = None
    formatted_messages: list[FormattedMessageItem] = Field(default_factory=list)


class DigestRequest(BaseModel):
    formatted_text: str = ""
    command_template: str = Field(default='opencode run -m opencode/minimax-m2.5-free "{prompt}"')
    system_prompt: str = Field(
        default=(
            "Create a compact Telegram digest from the provided messages.\n"
            "Group related updates by topic.\n"
            "Prioritize important developments.\n"
            "Avoid repetition.\n"
            "Preserve concrete facts, names, numbers, and links when present.\n"
            "Return Telegram-safe MarkdownV2 only.\n"
            "Formatting rules:\n"
            "- Use *bold* for section titles and important labels (single asterisk on each side).\n"
            "- Use _italic_ only for short source lists or light emphasis (single underscore on each side).\n"
            "- __underline__ means underline in MarkdownV2, not italic.\n"
            "- Use [text](url) for links and `code` only for literals.\n"
            "- Use simple bullet lists with '- '.\n"
            "- Do not use Markdown headings like # or ##.\n"
            "- Do not use HTML.\n"
            "- Do not use tables.\n"
            "- Do not use horizontal rules like ---.\n"
            "- Never use **bold** or __italic__ syntax.\n"
            "- Close every formatting marker correctly."
        )
    )
    output_format: str = Field(default="markdown_v2")


class ProviderAttemptSchema(BaseModel):
    provider_id: str
    success: bool
    details: dict[str, Any] | str | None = None


class DigestResponse(BaseModel):
    digest_text: str
    format: str
    parse_mode: str
    delivery_chunks: list[str] = Field(default_factory=list)
    provider_id: str
    provider_attempts: list[ProviderAttemptSchema] = Field(default_factory=list)
    message_count: int
    source_count: int
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
