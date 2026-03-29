from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


class ClassificationRule(BaseModel):
    rule_id: str
    name: str
    mode: Literal["suppress_topic", "boost_topic"]
    prompt_text: str
    threshold: int
    enabled: bool = True


class ClassificationRecord(BaseModel):
    source_id: str
    message_id: str
    matched_rules: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    score: float
    action: Literal["main", "filtered", "unclassified"]
    reason: str


class ProviderAttempt(BaseModel):
    provider_id: str
    success: bool
    details: dict[str, Any] | str | None = None
    latency_ms: int | None = None


class ClassificationOutput(BaseModel):
    message_scores: list[ClassificationRecord] = Field(default_factory=list)
    rule_set_version: str
    provider_kind: str
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list)
    degraded: bool = False
