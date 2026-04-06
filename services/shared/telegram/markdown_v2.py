from __future__ import annotations

from dataclasses import dataclass


PLAIN_TEXT_PARSE_MODE = "plain_text"
HTML_PARSE_MODE = "html"
DEFAULT_CHUNK_SIZE = 3000


@dataclass(slots=True)
class PreparedTelegramText:
    text: str
    chunks: list[str]


def normalize_parse_mode(value: str | None, *, default: str = PLAIN_TEXT_PARSE_MODE) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return default
    return normalized


def prepare_digest_delivery(
    *,
    raw_text: str,
    output_format: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    title_text: str | None = None,
) -> PreparedTelegramText:
    normalized_format = normalize_parse_mode(output_format, default=HTML_PARSE_MODE)
    if normalized_format not in {PLAIN_TEXT_PARSE_MODE, HTML_PARSE_MODE}:
        raise ValueError(f"Unsupported digest output format: {output_format}")

    normalized_text = _normalize_text(raw_text)
    normalized_title = _normalize_text(title_text or "")
    chunks = _prepare_titled_chunks(
        text=normalized_text,
        output_format=normalized_format,
        title_text=normalized_title,
        chunk_size=chunk_size,
    )
    return PreparedTelegramText(
        text=_prepend_digest_title(text=normalized_text, output_format=normalized_format, title_text=normalized_title),
        chunks=chunks,
    )


def split_plain_text_chunks(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    return _split_text(text=text, chunk_size=chunk_size)


def _prepare_titled_chunks(*, text: str, output_format: str, title_text: str, chunk_size: int) -> list[str]:
    if not title_text:
        return _split_text(text=text, chunk_size=chunk_size)

    title_line = _render_digest_title_line(title_text=title_text, output_format=output_format)
    if len(title_line) > chunk_size:
        raise ValueError("Digest title exceeds Telegram message size limit")
    if not text:
        return [title_line]

    single_chunk_body = _split_text(
        text=text,
        chunk_size=_resolve_titled_body_chunk_size(
            chunk_size=chunk_size,
            title_text=title_text,
            output_format=output_format,
            part_count=1,
        ),
    )
    if len(single_chunk_body) <= 1:
        return [_join_title_and_body(title_line=title_line, body_text=single_chunk_body[0] if single_chunk_body else text)]

    part_count = len(single_chunk_body)
    while True:
        body_chunks = _split_text(
            text=text,
            chunk_size=_resolve_titled_body_chunk_size(
                chunk_size=chunk_size,
                title_text=title_text,
                output_format=output_format,
                part_count=part_count,
            ),
        )
        actual_part_count = len(body_chunks)
        if actual_part_count == part_count:
            return [
                _join_title_and_body(
                    title_line=_render_digest_title_line(
                        title_text=title_text,
                        output_format=output_format,
                        part_index=index,
                        part_count=part_count,
                    ),
                    body_text=chunk,
                )
                for index, chunk in enumerate(body_chunks, start=1)
            ]
        part_count = actual_part_count


def _resolve_titled_body_chunk_size(*, chunk_size: int, title_text: str, output_format: str, part_count: int) -> int:
    title_line = _render_digest_title_line(
        title_text=title_text,
        output_format=output_format,
        part_index=part_count if part_count > 1 else None,
        part_count=part_count if part_count > 1 else None,
    )
    available = chunk_size - len(title_line) - 2
    if available < 1:
        raise ValueError("Digest title leaves no room for message body")
    return available


def _prepend_digest_title(*, text: str, output_format: str, title_text: str) -> str:
    if not title_text:
        return text
    return _join_title_and_body(
        title_line=_render_digest_title_line(title_text=title_text, output_format=output_format),
        body_text=text,
    )


def _render_digest_title_line(
    *,
    title_text: str,
    output_format: str,
    part_index: int | None = None,
    part_count: int | None = None,
) -> str:
    suffix = ""
    if part_index is not None and part_count is not None and part_count > 1:
        suffix = f" (частина {part_index}/{part_count})"
    full_title = f"{title_text}{suffix}".strip()
    if output_format == HTML_PARSE_MODE:
        return f"<b>{_escape_html_text(full_title)}</b>"
    return full_title


def _join_title_and_body(*, title_line: str, body_text: str) -> str:
    normalized_body = body_text.strip()
    if not normalized_body:
        return title_line
    return f"{title_line}\n\n{normalized_body}"


def _normalize_text(raw_text: str) -> str:
    return raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _escape_html_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split_text(*, text: str, chunk_size: int) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > chunk_size:
        split_at = remaining.rfind("\n\n", 0, chunk_size + 1)
        if split_at < chunk_size // 2:
            split_at = remaining.rfind("\n", 0, chunk_size + 1)
        if split_at < chunk_size // 2:
            split_at = remaining.rfind(" ", 0, chunk_size + 1)
        if split_at < chunk_size // 2:
            split_at = chunk_size

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:chunk_size]
        chunks.append(chunk)
        remaining = remaining[len(chunk) :].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks
