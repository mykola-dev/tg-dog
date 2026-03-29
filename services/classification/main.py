from __future__ import annotations

import argparse
import json

from services.shared.cli import build_success_envelope, emit_envelope
from services.shared.config import load_config
from services.shared.contracts.classification import (
    ClassificationOutput,
    ClassificationRecord,
    ClassificationRule,
    ProviderAttempt,
)
from services.shared.providers.classification import build_provider
from services.shared.runtime.artifacts import artifact_path, read_json, safe_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classification adapter")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--messages-ref", required=True)
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument("--heuristic-ref", default=None)
    return parser.parse_args()


def _load_messages(workspace_path, messages_ref: str) -> list[dict]:
    return read_json(workspace_path / messages_ref).get("messages", [])


def _load_heuristic_actions(workspace_path, heuristic_ref: str | None) -> dict[str, dict]:
    if not heuristic_ref:
        return {}
    payload = read_json(workspace_path / heuristic_ref)
    actions: dict[str, dict] = {}
    for decision in payload.get("message_decisions", []):
        actions[decision["message_id"]] = decision
    return actions


def main() -> None:
    args = parse_args()
    config = load_config()

    payload = json.loads(args.payload_json)
    rules = [ClassificationRule.model_validate(item) for item in payload.get("rules", []) if item.get("enabled", True)]
    providers = [item for item in payload.get("providers", []) if item.get("enabled", True)]

    messages = _load_messages(config.workspace_path, args.messages_ref)
    heuristic_actions = _load_heuristic_actions(config.workspace_path, args.heuristic_ref)

    provider_attempts: list[ProviderAttempt] = []
    message_scores: list[ClassificationRecord] = []
    degraded = False
    chosen_provider = "none"

    for message in messages:
        message_id = message["message_id"]
        text = (message.get("text") or "").lower()

        heuristic_decision = heuristic_actions.get(message_id)
        if heuristic_decision and heuristic_decision.get("action") == "drop_blacklist":
            continue

        winner = None
        for provider_cfg in providers:
            provider = build_provider(provider_cfg)
            response = provider.classify_text(text)
            provider_attempts.append(
                ProviderAttempt(
                    provider_id=provider.provider_id,
                    success=response.success,
                    details=response.details,
                )
            )
            if response.success:
                winner = response
                chosen_provider = provider.provider_id
                break

        if winner is None:
            degraded = True
            message_scores.append(
                ClassificationRecord(
                    source_id=message["source_id"],
                    message_id=message_id,
                    matched_rules=[],
                    labels=["degraded"],
                    score=0,
                    action="unclassified",
                    reason="All providers failed",
                )
            )
            continue

        matched_rule_ids: list[str] = []
        action = "main"

        for rule in rules:
            prompt_term = rule.prompt_text.lower().strip()
            if prompt_term and prompt_term in text:
                matched_rule_ids.append(rule.rule_id)
                if rule.mode == "suppress_topic" and winner.score is not None and winner.score >= rule.threshold:
                    action = "filtered"

        message_scores.append(
            ClassificationRecord(
                source_id=message["source_id"],
                message_id=message_id,
                matched_rules=matched_rule_ids,
                labels=winner.labels or [],
                score=winner.score or 0,
                action=action,
                reason=winner.reason or "classified",
            )
        )

    output = ClassificationOutput(
        message_scores=message_scores,
        rule_set_version="v1",
        provider_kind=chosen_provider,
        provider_attempts=provider_attempts,
        degraded=degraded,
    )
    output_path = artifact_path(config.workspace_path, args.run_id, "classification")
    safe_write_json(output_path, output.model_dump(mode="json"))
    ref = str(output_path.relative_to(config.workspace_path))

    emit_envelope(
        build_success_envelope(
            node_name="classification",
            run_id=args.run_id,
            payload_ref=ref,
            metrics={"messages": len(message_scores), "degraded": degraded},
        )
    )


if __name__ == "__main__":
    main()
