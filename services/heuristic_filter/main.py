from __future__ import annotations

import argparse
import json
import re
from typing import Any

from services.shared.cli import build_success_envelope, emit_envelope
from services.shared.config import load_config
from services.shared.contracts.heuristic import HeuristicDecision, HeuristicOutput, HeuristicRule
from services.shared.contracts.message import CanonicalMessage
from services.shared.runtime.artifacts import artifact_path, read_json, safe_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heuristic filter adapter")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--messages-ref", required=True)
    parser.add_argument("--rules-json", default="{}")
    return parser.parse_args()


def _normalize(text: str) -> list[str]:
    lowered = text.lower()
    cleaned = re.sub(r"[^a-zа-яіїє0-9\s]+", " ", lowered)
    return [token for token in cleaned.split() if token]


def _load_messages(workspace_path, messages_ref: str) -> list[CanonicalMessage]:
    payload = read_json(workspace_path / messages_ref)
    return [CanonicalMessage.model_validate(item) for item in payload.get("messages", [])]


def _load_rules(raw_json: str) -> list[HeuristicRule]:
    payload = json.loads(raw_json)
    return [HeuristicRule.model_validate(rule) for rule in payload.get("rules", []) if rule.get("enabled", True)]


def main() -> None:
    args = parse_args()
    config = load_config()
    messages = _load_messages(config.workspace_path, args.messages_ref)
    rules = _load_rules(args.rules_json)

    decisions: list[HeuristicDecision] = []
    whitelist_buckets: dict[str, list[dict[str, Any]]] = {}

    for message in messages:
        text = message.text or ""
        tokens = _normalize(text)

        matched_blacklist: list[str] = []
        matched_whitelist: list[str] = []
        matched_targets: set[str] = set()

        for rule in rules:
            normalized_terms = [_normalize(term) for term in rule.terms]
            flattened = {token for chunk in normalized_terms for token in chunk}
            hit = any(term in tokens for term in flattened)
            if not hit:
                continue
            if rule.kind == "blacklist":
                matched_blacklist.append(rule.rule_id)
            else:
                matched_whitelist.append(rule.rule_id)
                if rule.target_ref:
                    matched_targets.add(rule.target_ref)

        if matched_blacklist:
            action = "drop_blacklist"
            reason = "Matched blacklist rule"
        elif matched_whitelist:
            action = "copy_to_whitelist"
            reason = "Matched whitelist rule"
        else:
            action = "allow"
            reason = "No heuristic matches"

        decisions.append(
            HeuristicDecision(
                source_id=message.source_id,
                message_id=message.message_id,
                matched_blacklist_rules=matched_blacklist,
                matched_whitelist_rules=matched_whitelist,
                normalized_terms=tokens,
                action=action,
                reason=reason,
            )
        )

        if not matched_blacklist:
            for target in matched_targets:
                whitelist_buckets.setdefault(target, []).append(
                    {
                        "source_id": message.source_id,
                        "message_id": message.message_id,
                        "text": text,
                    }
                )

    output = HeuristicOutput(
        message_decisions=decisions,
        matched_whitelist_groups=whitelist_buckets,
        rule_set_version="v1",
        engine_kind="local_heuristic",
    )
    output_path = artifact_path(config.workspace_path, args.run_id, "heuristic")
    safe_write_json(output_path, output.model_dump(mode="json"))
    ref = str(output_path.relative_to(config.workspace_path))

    emit_envelope(
        build_success_envelope(
            node_name="heuristic-filter",
            run_id=args.run_id,
            payload_ref=ref,
            metrics={"messages": len(messages), "rules": len(rules)},
        )
    )


if __name__ == "__main__":
    main()
