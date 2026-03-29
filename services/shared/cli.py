from __future__ import annotations

import json
import sys
from typing import Any

from services.shared.contracts.common import AdapterEnvelope, StructuredError


def build_success_envelope(
    *,
    node_name: str,
    run_id: str,
    payload_inline: dict[str, Any] | None = None,
    payload_ref: str | None = None,
    warnings: list[str | dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> AdapterEnvelope:
    return AdapterEnvelope(
        contract_version="v1",
        node_name=node_name,
        run_id=run_id,
        status="ok",
        payload_inline=payload_inline,
        payload_ref=payload_ref,
        warnings=warnings or [],
        metrics=metrics,
        error=None,
    )


def build_error_envelope(
    *,
    node_name: str,
    run_id: str,
    code: str,
    message: str,
    retryable: bool,
    user_action_required: bool,
    details: dict[str, Any] | None = None,
    recommended_action: str | None = None,
    warnings: list[str | dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> AdapterEnvelope:
    return AdapterEnvelope(
        contract_version="v1",
        node_name=node_name,
        run_id=run_id,
        status="error",
        payload_inline=None,
        payload_ref=None,
        warnings=warnings or [],
        metrics=metrics,
        error=StructuredError(
            code=code,
            message=message,
            details=details,
            retryable=retryable,
            user_action_required=user_action_required,
            recommended_action=recommended_action,
        ),
    )


def emit_envelope(envelope: AdapterEnvelope) -> None:
    sys.stdout.write(json.dumps(envelope.model_dump(mode="json")))
    sys.stdout.write("\n")
