from __future__ import annotations

from typing import Any

from services.shared.contracts.message import CanonicalMessage
from services.shared.providers.ocr import resolve_ocr_provider


def enrich_messages_with_ocr(
    messages: list[CanonicalMessage],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    provider = resolve_ocr_provider()
    enriched_messages: list[dict[str, Any]] = []
    items_processed = 0
    failures = 0

    for message in messages:
        message_payload = message.model_dump(mode="json")
        media_payloads: list[dict[str, Any]] = []
        extracted_chunks: list[str] = []

        for media in message.media_items:
            media_payload = media.model_dump(mode="json")

            if media.media_kind != "image":
                if media_payload.get("ocr_status") == "pending":
                    media_payload["ocr_status"] = "skipped"
                media_payloads.append(media_payload)
                continue

            if media.ocr_status == "done" and media.ocr_text:
                extracted_chunks.append(media.ocr_text)
                media_payloads.append(media_payload)
                continue

            provider_result = provider.extract_text(media.file_ref)
            items_processed += 1
            if provider_result.status == "done":
                media_payload["ocr_status"] = "done"
                media_payload["ocr_text"] = provider_result.extracted_text
                media_payload["ocr_confidence_hint"] = provider_result.confidence_hint
                media_payload["ocr_error_code"] = None
                media_payload["ocr_error_message"] = None
                if provider_result.extracted_text:
                    extracted_chunks.append(provider_result.extracted_text)
            else:
                failures += 1
                media_payload["ocr_status"] = "failed"
                media_payload["ocr_text"] = None
                media_payload["ocr_confidence_hint"] = None
                media_payload["ocr_error_code"] = provider_result.code or "OCR_ITEM_FAILED"
                media_payload["ocr_error_message"] = provider_result.message or "OCR failed"

            media_payloads.append(media_payload)

        message_payload["media_items"] = media_payloads
        joined_text = "\n\n".join(chunk.strip() for chunk in extracted_chunks if chunk and chunk.strip())
        message_payload["ocr_text"] = joined_text or None
        enriched_messages.append(message_payload)

    return enriched_messages, {
        "items_processed": items_processed,
        "failures": failures,
    }
