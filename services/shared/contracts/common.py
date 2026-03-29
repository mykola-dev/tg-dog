from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class StructuredError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool
    user_action_required: bool
    recommended_action: str | None = None


class TargetDescriptor(BaseModel):
    target_id: str
    target_kind: Literal["saved_messages", "chat", "channel"] = "saved_messages"
    target_title: str | None = None


class AdapterEnvelope(BaseModel):
    contract_version: Literal["v1"] = "v1"
    node_name: str
    run_id: str
    status: Literal["ok", "error"]
    payload_inline: dict[str, Any] | None = None
    payload_ref: str | None = None
    warnings: list[str | dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None
    error: StructuredError | None = None

    @model_validator(mode="after")
    def validate_status_error_consistency(self) -> "AdapterEnvelope":
        if self.status == "error" and self.error is None:
            raise ValueError("error field is required when status=error")
        if self.status == "ok" and self.error is not None:
            raise ValueError("error field must be empty when status=ok")
        return self
