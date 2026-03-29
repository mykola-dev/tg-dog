from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CanonicalMediaItem(BaseModel):
    media_kind: str
    file_ref: str
    mime_type: str | None = None
    size_bytes: int | None = None
    ocr_status: Literal["pending", "skipped", "done", "failed"] = "pending"
    ocr_text: str | None = None
    ocr_confidence_hint: float | None = None
    ocr_error_code: str | None = None
    ocr_error_message: str | None = None


class CanonicalMessage(BaseModel):
    schema_version: Literal["v1"] = "v1"
    source_kind: Literal["channel", "group", "contact"]
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
    media_items: list[CanonicalMediaItem] = Field(default_factory=list)
    ocr_text: str | None = None
    ingestion_meta: dict[str, Any] = Field(default_factory=dict)
