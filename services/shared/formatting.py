from __future__ import annotations

from datetime import datetime

from services.shared.contracts.message import CanonicalMessage


def _clip(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _format_timestamp(raw: datetime | str | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return raw.isoformat()


def format_single_message(
    message: CanonicalMessage,
    *,
    output_format: str,
    include_source_title: bool,
    include_timestamp: bool,
    include_ocr_text: bool,
    max_characters_per_message: int,
) -> str:
    lines: list[str] = []
    header_parts: list[str] = []

    if include_source_title and message.source_title:
        header_parts.append(message.source_title)
    if include_timestamp:
        timestamp = _format_timestamp(message.message_timestamp)
        if timestamp:
            header_parts.append(timestamp)

    if header_parts:
        if output_format == "markdown":
            lines.append(f"## {' | '.join(header_parts)}")
        else:
            lines.append(f"[{ ' | '.join(header_parts) }]")

    text_value = _clip(message.text or "", max_characters_per_message)
    if text_value:
        lines.append(text_value)

    if include_ocr_text and message.ocr_text:
        ocr_value = _clip(message.ocr_text, max_characters_per_message)
        if ocr_value:
            if output_format == "markdown":
                lines.append(f"OCR:\n{ocr_value}")
            else:
                lines.append(f"OCR:\n{ocr_value}")

    return "\n\n".join(line for line in lines if line.strip()).strip()


def format_messages(
    messages: list[CanonicalMessage],
    *,
    mode: str,
    output_format: str,
    include_source_title: bool,
    include_timestamp: bool,
    include_ocr_text: bool,
    max_characters_per_message: int,
) -> dict:
    formatted_messages = []

    for message in messages:
        formatted_text = format_single_message(
            message,
            output_format=output_format,
            include_source_title=include_source_title,
            include_timestamp=include_timestamp,
            include_ocr_text=include_ocr_text,
            max_characters_per_message=max_characters_per_message,
        )
        if not formatted_text:
            continue
        formatted_messages.append(
            {
                "source_id": message.source_id,
                "message_id": message.message_id,
                "formatted_text": formatted_text,
            }
        )

    combined_text = None
    if mode == "combined":
        combined_text = "\n\n---\n\n".join(item["formatted_text"] for item in formatted_messages)

    return {
        "mode": mode,
        "output_format": output_format,
        "message_count": len(formatted_messages),
        "combined_text": combined_text,
        "formatted_messages": formatted_messages,
    }
