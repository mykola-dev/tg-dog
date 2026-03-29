from services.shared.contracts.message import CanonicalMessage
from services.shared.formatting import format_messages


def _message(*, text: str = "Hello", ocr_text: str | None = None) -> CanonicalMessage:
    return CanonicalMessage(
        source_kind="channel",
        source_id="-100123",
        source_title="Example Channel",
        message_id="1",
        message_timestamp="2026-03-25T12:00:00Z",
        is_outbound=False,
        is_from_self=False,
        is_service_message=False,
        text=text,
        ocr_text=ocr_text,
        media_items=[],
        ingestion_meta={},
    )


def test_format_messages_combined_markdown_includes_source_and_ocr() -> None:
    payload = format_messages(
        [_message(text="Hello world", ocr_text="OCR text")],
        mode="combined",
        output_format="markdown",
        include_source_title=True,
        include_timestamp=True,
        include_ocr_text=True,
        max_characters_per_message=1200,
    )

    assert payload["mode"] == "combined"
    assert payload["message_count"] == 1
    assert "## Example Channel" in payload["combined_text"]
    assert "Hello world" in payload["combined_text"]
    assert "OCR text" in payload["combined_text"]


def test_format_messages_per_message_plain_text_omits_ocr_when_disabled() -> None:
    payload = format_messages(
        [_message(text="Hello world", ocr_text="OCR text")],
        mode="per_message",
        output_format="plain_text",
        include_source_title=True,
        include_timestamp=False,
        include_ocr_text=False,
        max_characters_per_message=1200,
    )

    assert payload["combined_text"] is None
    assert len(payload["formatted_messages"]) == 1
    assert "Hello world" in payload["formatted_messages"][0]["formatted_text"]
    assert "OCR text" not in payload["formatted_messages"][0]["formatted_text"]
