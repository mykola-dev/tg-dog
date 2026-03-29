from pathlib import Path
from unittest.mock import patch

from services.shared.contracts.message import CanonicalMediaItem, CanonicalMessage
from services.shared.ocr_enrichment import enrich_messages_with_ocr
from services.shared.providers.ocr import OCRProviderResult


def test_ocr_enrichment_uses_example_image() -> None:
    image_path = str((Path(__file__).resolve().parents[2] / "example.jpg").resolve())
    messages = [
        CanonicalMessage(
            source_kind="channel",
            source_id="-100123",
            source_title="Example",
            message_id="1",
            message_timestamp="2026-03-25T12:00:00Z",
            is_outbound=False,
            is_from_self=False,
            is_service_message=False,
            media_items=[
                CanonicalMediaItem(
                    media_kind="image",
                    file_ref=image_path,
                    ocr_status="pending",
                )
            ],
            ingestion_meta={},
            text="",
        )
    ]

    class FakeProvider:
        def extract_text(self, file_ref: str, *, simulate_failure: bool = False) -> OCRProviderResult:
            assert file_ref == image_path
            return OCRProviderResult(
                extracted_text="text from example.jpg",
                confidence_hint=0.75,
                status="done",
            )

    with patch("services.shared.ocr_enrichment.resolve_ocr_provider", return_value=FakeProvider()):
        enriched, metrics = enrich_messages_with_ocr(messages)

    assert metrics["items_processed"] == 1
    assert metrics["failures"] == 0
    assert enriched[0]["media_items"][0]["ocr_status"] == "done"
    assert enriched[0]["media_items"][0]["ocr_text"] == "text from example.jpg"
    assert enriched[0]["ocr_text"] == "text from example.jpg"


def test_ocr_enrichment_skips_non_image_media() -> None:
    messages = [
        CanonicalMessage(
            source_kind="channel",
            source_id="-100123",
            source_title="Example",
            message_id="1",
            message_timestamp="2026-03-25T12:00:00Z",
            is_outbound=False,
            is_from_self=False,
            is_service_message=False,
            media_items=[
                CanonicalMediaItem(
                    media_kind="document",
                    file_ref="/tmp/example.bin",
                    ocr_status="pending",
                )
            ],
            ingestion_meta={},
            text="",
        )
    ]

    with patch("services.shared.ocr_enrichment.resolve_ocr_provider") as mocked_resolver:
        enriched, metrics = enrich_messages_with_ocr(messages)

    mocked_resolver.assert_called_once()

    assert metrics["items_processed"] == 0
    assert metrics["failures"] == 0
    assert enriched[0]["media_items"][0]["ocr_status"] == "skipped"
    assert enriched[0]["ocr_text"] is None
