from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from services.shared.contracts.common import TargetDescriptor


class RunManifest(BaseModel):
    contract_version: Literal["v1"] = "v1"
    run_id: str
    trigger_type: Literal["manual", "scheduled"]
    requested_at: datetime
    timezone: str
    window_mode: Literal["last_n_hours", "manual_range", "scheduled_window"]
    time_window_start: datetime
    time_window_end: datetime
    selected_source_refs: list[str]
    enabled_nodes: dict[str, bool]
    delivery_target: TargetDescriptor
    whitelist_targets: dict[str, TargetDescriptor] = Field(default_factory=dict)
    workspace_path: str
    scheduled_window_key: str | None = None
    dry_run: bool = False
    safety_policy_version: str
    previous_outputs: dict[str, str] = Field(default_factory=dict)
    classification_provider_queue: list[dict] = Field(default_factory=list)
    heuristic_rules_version: str | None = None
    classification_rules_version: str | None = None
