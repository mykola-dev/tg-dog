from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.shared.cli import build_success_envelope, emit_envelope
from services.shared.config import load_config
from services.shared.contracts.message import CanonicalMessage
from services.shared.contracts.ocr import OCRItemFailure, OCROutput, OCRResultItem
from services.shared.providers.ocr import resolve_ocr_provider
from services.shared.runtime.artifacts import artifact_path, read_json, safe_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR adapter")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--messages-ref", required=True)
    return parser.parse_args()


def _load_messages(workspace_path: Path, messages_ref: str) -> list[CanonicalMessage]:
    payload = read_json(workspace_path / messages_ref)
    return [CanonicalMessage.model_validate(item) for item in payload.get("messages", [])]


def main() -> None:
    args = parse_args()
    config = load_config()

    provider = resolve_ocr_provider()
    messages = _load_messages(config.workspace_path, args.messages_ref)

    results: list[OCRResultItem] = []
    failures: list[OCRItemFailure] = []

    for message in messages:
        for media_index, media in enumerate(message.media_items):
            if media.media_kind != "image":
                continue
            simulate_failure = bool(message.ingestion_meta.get("simulate_ocr_failure", False))
            provider_result = provider.extract_text(media.file_ref, simulate_failure=simulate_failure)
            if provider_result.status == "done":
                results.append(
                    OCRResultItem(
                        source_id=message.source_id,
                        message_id=message.message_id,
                        media_index=media_index,
                        ocr_status="done",
                        extracted_text=provider_result.extracted_text,
                        confidence_hint=provider_result.confidence_hint,
                    )
                )
            else:
                results.append(
                    OCRResultItem(
                        source_id=message.source_id,
                        message_id=message.message_id,
                        media_index=media_index,
                        ocr_status="failed",
                        extracted_text=None,
                        confidence_hint=None,
                    )
                )
                failures.append(
                    OCRItemFailure(
                        source_id=message.source_id,
                        message_id=message.message_id,
                        media_index=media_index,
                        code=provider_result.code or "OCR_ITEM_FAILED",
                        message=provider_result.message or "OCR failed",
                    )
                )

    output = OCROutput(
        message_ocr_results=results,
        provider_kind=provider.provider_id,
        failed_items=failures,
    )
    output_path = artifact_path(config.workspace_path, args.run_id, "ocr")
    safe_write_json(output_path, output.model_dump(mode="json"))
    relative_ref = str(output_path.relative_to(config.workspace_path))

    emit_envelope(
        build_success_envelope(
            node_name="ocr",
            run_id=args.run_id,
            payload_ref=relative_ref,
            metrics={
                "items_processed": len(results),
                "failures": len(failures),
            },
        )
    )


if __name__ == "__main__":
    main()
