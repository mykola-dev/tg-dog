from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HeuristicRule(BaseModel):
    rule_id: str
    name: str
    kind: Literal["blacklist", "whitelist"]
    terms: list[str]
    language_scope: Literal["en", "uk", "ru", "auto"] = "auto"
    enabled: bool = True
    target_ref: str | None = None


class HeuristicDecision(BaseModel):
    source_id: str
    message_id: str
    matched_blacklist_rules: list[str] = Field(default_factory=list)
    matched_whitelist_rules: list[str] = Field(default_factory=list)
    normalized_terms: list[str] = Field(default_factory=list)
    action: Literal["allow", "drop_blacklist", "copy_to_whitelist"]
    reason: str


class HeuristicOutput(BaseModel):
    message_decisions: list[HeuristicDecision] = Field(default_factory=list)
    matched_whitelist_groups: dict[str, list[dict]] = Field(default_factory=dict)
    rule_set_version: str
    engine_kind: Literal["local_heuristic"] = "local_heuristic"
