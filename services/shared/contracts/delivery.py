from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from services.shared.contracts.common import TargetDescriptor


class SentMessageRef(BaseModel):
    chat_id: str
    message_id: str


class DeliveryReceipt(BaseModel):
    delivery_status: Literal[
        "sent",
        "skipped_duplicate",
        "blocked_safety_policy",
        "failed",
    ]
    delivery_target: TargetDescriptor
    sent_message_refs: list[SentMessageRef] = Field(default_factory=list)
    digest_fingerprint: str
    idempotency_key: str
