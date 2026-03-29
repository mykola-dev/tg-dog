from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any, Literal, cast

from services.shared.cli import build_error_envelope, build_success_envelope, emit_envelope
from services.shared.config import load_config
from services.shared.contracts.common import TargetDescriptor
from services.shared.contracts.delivery import DeliveryReceipt, SentMessageRef
from services.shared.runtime.artifacts import artifact_path, read_json, safe_write_json
from services.shared.runtime.idempotency import DeliveryDedupStore
from services.shared.runtime.rate_limits import (
    BoundedRateLimiter,
    ErrorCooldownTracker,
    ExponentialBackoffPolicy,
)
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.errors import TelegramDeliveryError


MAX_CHUNKS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delivery adapter")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--digest-ref", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--resume", choices=["true", "false"], default="false")
    return parser.parse_args()


def _build_receipt(
    *,
    delivery_status: Literal["sent", "skipped_duplicate", "blocked_safety_policy", "failed"],
    target_id: str,
    digest_fingerprint: str,
    run_id: str,
    sent_refs: list[SentMessageRef],
    truncated: bool,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = DeliveryReceipt(
        delivery_status=cast(Literal["sent", "skipped_duplicate", "blocked_safety_policy", "failed"], delivery_status),
        delivery_target=TargetDescriptor(target_id=target_id, target_kind="saved_messages"),
        sent_message_refs=sent_refs,
        digest_fingerprint=digest_fingerprint,
        idempotency_key=hashlib.sha256(f"{run_id}:{digest_fingerprint}".encode("utf-8")).hexdigest()[:24],
    ).model_dump(mode="json")
    receipt["truncated"] = truncated
    if extras:
        receipt.update(extras)
    return receipt


def _emit_error_and_exit(*, run_id: str, error: TelegramDeliveryError) -> None:
    recommended_action = None
    user_action_required = False
    if error.code == "AUTH_REQUIRED":
        recommended_action = "Re-authenticate the Telegram session before running delivery again"
        user_action_required = True
    elif error.code == "UNSUPPORTED_DELIVERY_TARGET":
        recommended_action = "Use --target-id self for Telegram Saved Messages delivery"
        user_action_required = True

    emit_envelope(
        build_error_envelope(
            node_name="delivery",
            run_id=run_id,
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            user_action_required=user_action_required,
            recommended_action=recommended_action,
        )
    )
    sys.exit(1)


def _write_receipt_envelope(
    *,
    workspace_path: Path,
    run_id: str,
    receipt: dict[str, Any],
    chunks_sent: int,
    truncated: bool,
    retry_attempts: int,
) -> None:
    output_path = artifact_path(workspace_path, run_id, "delivery")
    safe_write_json(output_path, receipt)
    relative_ref = str(output_path.relative_to(workspace_path))

    emit_envelope(
        build_success_envelope(
            node_name="delivery",
            run_id=run_id,
            payload_ref=relative_ref,
            metrics={
                "chunks_sent": chunks_sent,
                "truncated": truncated,
                "status": receipt["delivery_status"],
                "retry_attempts": retry_attempts,
            },
        )
    )


def _write_receipt_artifact(
    *,
    workspace_path: Path,
    run_id: str,
    receipt: dict[str, Any],
) -> None:
    output_path = artifact_path(workspace_path, run_id, "delivery")
    safe_write_json(output_path, receipt)


def _load_existing_sent_refs(*, workspace_path: Path, run_id: str) -> list[SentMessageRef]:
    output_path = artifact_path(workspace_path, run_id, "delivery")
    if not output_path.exists():
        return []

    previous_receipt = read_json(output_path)
    sent_message_refs = previous_receipt.get("sent_message_refs", [])
    return [SentMessageRef.model_validate(item) for item in sent_message_refs]


def _ensure_supported_target(target_id: str) -> None:
    if target_id != "self":
        raise TelegramDeliveryError(
            code="UNSUPPORTED_DELIVERY_TARGET",
            message=f"Unsupported delivery target: {target_id}",
            retryable=False,
        )


def main() -> None:
    args = parse_args()
    config = load_config()
    digest = read_json(config.workspace_path / args.digest_ref)
    dedup_store = DeliveryDedupStore(config.workspace_path)
    cooldown = ErrorCooldownTracker(config.workspace_path)
    backoff = ExponentialBackoffPolicy(max_retries=3, base_delay_seconds=0.0)
    limiter = BoundedRateLimiter(base_delay_seconds=0.0, max_chunks_per_run=MAX_CHUNKS)
    client = TelegramClientWrapper(config.telegram_session_path)

    fingerprint = digest["digest_fingerprint"]
    resume = args.resume == "true"

    try:
        _ensure_supported_target(args.target_id)
    except TelegramDeliveryError as exc:
        _emit_error_and_exit(run_id=args.run_id, error=exc)

    chunks: list[str] = list(digest.get("delivery_chunks", []))
    truncated = len(chunks) > MAX_CHUNKS
    if truncated:
        kept = chunks[:MAX_CHUNKS]
        kept[-1] = f"{kept[-1]}\n\n[Truncated: digest exceeded max chunk count]"
        chunks = kept

    if dedup_store.is_duplicate_fingerprint(fingerprint):
        existing_sent_refs = _load_existing_sent_refs(workspace_path=config.workspace_path, run_id=args.run_id)
        receipt = _build_receipt(
            delivery_status="skipped_duplicate",
            target_id=args.target_id,
            digest_fingerprint=fingerprint,
            run_id=args.run_id,
            sent_refs=existing_sent_refs,
            truncated=truncated,
            extras={"retry_attempts": 0},
        )
        _write_receipt_envelope(
            workspace_path=config.workspace_path,
            run_id=args.run_id,
            receipt=receipt,
            chunks_sent=len(existing_sent_refs),
            truncated=truncated,
            retry_attempts=0,
        )
        return

    already_sent = dedup_store.get_sent_count(fingerprint) if resume else 0
    sendable_chunks = chunks[already_sent:]

    existing_sent_refs = _load_existing_sent_refs(workspace_path=config.workspace_path, run_id=args.run_id) if resume else []
    sent_refs: list[SentMessageRef] = list(existing_sent_refs)
    new_sent_refs: list[SentMessageRef] = []
    retry_attempts = 0

    for offset, chunk in enumerate(sendable_chunks, start=1):
        chunk_index_1_based = already_sent + offset
        if not limiter.allow_chunk(chunk_index_1_based):
            break

        attempts_for_chunk = 0
        while True:
            try:
                wrapper_result = client.send_text_chunk(target_id=args.target_id, chunk_text=chunk)
                sent_ref = SentMessageRef.model_validate(wrapper_result)
                sent_refs.append(sent_ref)
                new_sent_refs.append(sent_ref)
                limiter.wait_base_delay()
                break
            except TelegramDeliveryError as exc:
                if exc.code in {"UNSUPPORTED_DELIVERY_TARGET", "AUTH_REQUIRED"} or not exc.retryable:
                    if sent_refs:
                        dedup_store.set_sent_count(fingerprint, already_sent + len(new_sent_refs))
                        receipt = _build_receipt(
                            delivery_status="failed",
                            target_id=args.target_id,
                            digest_fingerprint=fingerprint,
                            run_id=args.run_id,
                            sent_refs=sent_refs,
                            truncated=truncated,
                            extras={"retry_attempts": retry_attempts},
                        )
                        _write_receipt_artifact(
                            workspace_path=config.workspace_path,
                            run_id=args.run_id,
                            receipt=receipt,
                        )
                    _emit_error_and_exit(run_id=args.run_id, error=exc)

                attempts_for_chunk += 1
                retry_attempts += 1
                delay = backoff.delay_for_attempt(attempts_for_chunk)
                if attempts_for_chunk < backoff.max_retries and delay >= 0:
                    continue

                cooldown.record_failure(exc.code)
                dedup_store.set_sent_count(fingerprint, already_sent + len(new_sent_refs))

                if cooldown.should_block(exc.code):
                    receipt = _build_receipt(
                        delivery_status="blocked_safety_policy",
                        target_id=args.target_id,
                        digest_fingerprint=fingerprint,
                        run_id=args.run_id,
                        sent_refs=sent_refs,
                        truncated=truncated,
                        extras={"retry_attempts": retry_attempts, "system_status": "delivery paused"},
                    )
                else:
                    extras: dict[str, Any] = {"retry_attempts": retry_attempts}
                    if exc.code == "RATE_LIMIT":
                        extras["system_status"] = "rate limited"
                    receipt = _build_receipt(
                        delivery_status="failed",
                        target_id=args.target_id,
                        digest_fingerprint=fingerprint,
                        run_id=args.run_id,
                        sent_refs=sent_refs,
                        truncated=truncated,
                        extras=extras,
                    )

                _write_receipt_envelope(
                    workspace_path=config.workspace_path,
                    run_id=args.run_id,
                    receipt=receipt,
                    chunks_sent=len(sent_refs),
                    truncated=truncated,
                    retry_attempts=retry_attempts,
                )
                return

    dedup_store.record_fingerprint(fingerprint)
    dedup_store.clear_progress(fingerprint)
    receipt = _build_receipt(
        delivery_status="sent",
        target_id=args.target_id,
        digest_fingerprint=fingerprint,
        run_id=args.run_id,
        sent_refs=sent_refs,
        truncated=truncated,
        extras={"retry_attempts": retry_attempts},
    )
    _write_receipt_envelope(
        workspace_path=config.workspace_path,
        run_id=args.run_id,
        receipt=receipt,
        chunks_sent=len(sent_refs),
        truncated=truncated,
        retry_attempts=retry_attempts,
    )


if __name__ == "__main__":
    main()
