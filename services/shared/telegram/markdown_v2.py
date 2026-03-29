from __future__ import annotations

import re
from dataclasses import dataclass


MARKDOWN_V2_PARSE_MODE = "markdown_v2"
PLAIN_TEXT_PARSE_MODE = "plain_text"
DEFAULT_CHUNK_SIZE = 3000
_MARKDOWN_V2_SPECIAL_CHARS = frozenset("_*[]()~`>#+-=|{}.!")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<content>.+?)\s*$")
_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(?P<content>.+?)\s*$")
_NUMBERED_RE = re.compile(r"^\s*(?P<number>\d+)[.)]\s+(?P<content>.+?)\s*$")
_BLOCKQUOTE_RE = re.compile(r"^\s*>\s?(?P<content>.+?)\s*$")
_CODE_BLOCK_RE = re.compile(r"```(?P<language>[^\n`]*)\n(?P<code>.*?)```", re.DOTALL)


@dataclass(slots=True)
class PreparedTelegramText:
    text: str
    chunks: list[str]


def normalize_parse_mode(value: str | None, *, default: str = PLAIN_TEXT_PARSE_MODE) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return default
    return normalized


def prepare_digest_delivery(*, raw_text: str, output_format: str, chunk_size: int = DEFAULT_CHUNK_SIZE, title_text: str | None = None) -> PreparedTelegramText:
    normalized_format = normalize_parse_mode(output_format, default=MARKDOWN_V2_PARSE_MODE)
    normalized_title = _normalize_plain_text(title_text or "")
    if normalized_format == PLAIN_TEXT_PARSE_MODE:
        text = _normalize_plain_text(raw_text)
        chunks = _prepare_titled_chunks(
            text=text,
            output_format=normalized_format,
            title_text=normalized_title,
            chunk_size=chunk_size,
        )
        return PreparedTelegramText(text=_prepend_digest_title(text=text, output_format=normalized_format, title_text=normalized_title), chunks=chunks)
    if normalized_format != MARKDOWN_V2_PARSE_MODE:
        raise ValueError(f"Unsupported digest output format: {output_format}")

    blocks = _prepare_markdown_v2_blocks(raw_text)
    text = "\n\n".join(blocks).strip()
    chunks = _prepare_titled_chunks(
        text=text,
        output_format=normalized_format,
        title_text=normalized_title,
        chunk_size=chunk_size,
        blocks=blocks,
    )
    return PreparedTelegramText(text=_prepend_digest_title(text=text, output_format=normalized_format, title_text=normalized_title), chunks=chunks)


def split_plain_text_chunks(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    return _split_plain_text(text=text, chunk_size=chunk_size)


def _prepare_titled_chunks(
    *,
    text: str,
    output_format: str,
    title_text: str,
    chunk_size: int,
    blocks: list[str] | None = None,
) -> list[str]:
    if not title_text:
        if output_format == PLAIN_TEXT_PARSE_MODE:
            return _split_plain_text(text=text, chunk_size=chunk_size)
        return _chunk_blocks(blocks=blocks or [], chunk_size=chunk_size)

    title_line = _render_digest_title_line(title_text=title_text, output_format=output_format)
    if len(title_line) > chunk_size:
        raise ValueError("Digest title exceeds Telegram message size limit")
    if not text:
        return [title_line]

    single_chunk_body = _chunk_digest_body(
        text=text,
        output_format=output_format,
        chunk_size=_resolve_titled_body_chunk_size(
            chunk_size=chunk_size,
            title_text=title_text,
            output_format=output_format,
            part_count=1,
        ),
        blocks=blocks,
    )
    if len(single_chunk_body) <= 1:
        return [_join_title_and_body(title_line=title_line, body_text=single_chunk_body[0] if single_chunk_body else text)]

    part_count = len(single_chunk_body)
    while True:
        body_chunks = _chunk_digest_body(
            text=text,
            output_format=output_format,
            chunk_size=_resolve_titled_body_chunk_size(
                chunk_size=chunk_size,
                title_text=title_text,
                output_format=output_format,
                part_count=part_count,
            ),
            blocks=blocks,
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


def _chunk_digest_body(
    *,
    text: str,
    output_format: str,
    chunk_size: int,
    blocks: list[str] | None = None,
) -> list[str]:
    if output_format == PLAIN_TEXT_PARSE_MODE:
        return _split_plain_text(text=text, chunk_size=chunk_size)
    return _chunk_blocks(blocks=blocks or [], chunk_size=chunk_size)


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
    title_line = _render_digest_title_line(title_text=title_text, output_format=output_format)
    return _join_title_and_body(title_line=title_line, body_text=text)


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
    if output_format == MARKDOWN_V2_PARSE_MODE:
        return f"*{_escape_plain_text(full_title)}*"
    return full_title


def _join_title_and_body(*, title_line: str, body_text: str) -> str:
    normalized_body = body_text.strip()
    if not normalized_body:
        return title_line
    return f"{title_line}\n\n{normalized_body}"


def _normalize_plain_text(raw_text: str) -> str:
    return raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _prepare_markdown_v2_blocks(raw_text: str) -> list[str]:
    normalized = _normalize_plain_text(raw_text)
    if not normalized:
        return []

    blocks: list[str] = []
    cursor = 0
    for match in _CODE_BLOCK_RE.finditer(normalized):
        if match.start() > cursor:
            blocks.extend(_prepare_text_segment_blocks(normalized[cursor : match.start()]))
        blocks.append(_render_code_block(language=match.group("language"), code=match.group("code")))
        cursor = match.end()

    if cursor < len(normalized):
        blocks.extend(_prepare_text_segment_blocks(normalized[cursor:]))

    return [block for block in blocks if block.strip()]


def _prepare_text_segment_blocks(segment: str) -> list[str]:
    stripped = segment.strip()
    if not stripped:
        return []

    paragraphs = re.split(r"\n\s*\n+", stripped)
    blocks: list[str] = []
    for paragraph in paragraphs:
        sanitized_lines = []
        for raw_line in paragraph.split("\n"):
            line = _sanitize_markdown_line(raw_line)
            if line:
                sanitized_lines.append(line)
        if sanitized_lines:
            blocks.append("\n".join(sanitized_lines).strip())
    return blocks


def _sanitize_markdown_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""
    if _HR_RE.match(line):
        return ""

    heading_match = _HEADING_RE.match(line)
    if heading_match:
        content = _escape_plain_text(heading_match.group("content").strip())
        return f"*{content}*" if content else ""

    bullet_match = _BULLET_RE.match(line)
    if bullet_match:
        content = _sanitize_inline_text(bullet_match.group("content"))
        return f"\\- {content}" if content else "\\-"

    numbered_match = _NUMBERED_RE.match(line)
    if numbered_match:
        content = _sanitize_inline_text(numbered_match.group("content"))
        number = numbered_match.group("number")
        return f"{number}\\. {content}" if content else f"{number}\\."

    blockquote_match = _BLOCKQUOTE_RE.match(line)
    if blockquote_match:
        content = _sanitize_inline_text(blockquote_match.group("content"))
        return f">{content}" if content else ">"

    return _sanitize_inline_text(line)


def _sanitize_inline_text(text: str) -> str:
    out: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "\\":
            if cursor + 1 < len(text):
                out.append(_escape_plain_char(text[cursor + 1]))
                cursor += 2
                continue
            out.append("\\\\")
            cursor += 1
            continue

        link_token = _consume_link(text, cursor)
        if link_token is not None:
            rendered, cursor = link_token
            out.append(rendered)
            continue

        code_token = _consume_wrapped_token(text, cursor, "`", "`", renderer=_render_inline_code)
        if code_token is not None:
            rendered, cursor = code_token
            out.append(rendered)
            continue

        spoiler_token = _consume_wrapped_token(text, cursor, "||", "||", renderer=lambda value: f"||{_escape_plain_text(value)}||")
        if spoiler_token is not None:
            rendered, cursor = spoiler_token
            out.append(rendered)
            continue

        strike_token = _consume_wrapped_token(text, cursor, "~", "~", renderer=lambda value: f"~{_escape_plain_text(value)}~")
        if strike_token is not None:
            rendered, cursor = strike_token
            out.append(rendered)
            continue

        bold_token = _consume_wrapped_token(text, cursor, "**", "**", renderer=lambda value: f"*{_escape_plain_text(value)}*")
        if bold_token is not None:
            rendered, cursor = bold_token
            out.append(rendered)
            continue

        bold_token = _consume_wrapped_token(text, cursor, "*", "*", renderer=lambda value: f"*{_escape_plain_text(value)}*", require_word_boundary=True)
        if bold_token is not None:
            rendered, cursor = bold_token
            out.append(rendered)
            continue

        italic_token = _consume_wrapped_token(text, cursor, "__", "__", renderer=lambda value: f"_{_escape_plain_text(value)}_")
        if italic_token is not None:
            rendered, cursor = italic_token
            out.append(rendered)
            continue

        italic_token = _consume_wrapped_token(text, cursor, "_", "_", renderer=lambda value: f"_{_escape_plain_text(value)}_", require_word_boundary=True)
        if italic_token is not None:
            rendered, cursor = italic_token
            out.append(rendered)
            continue

        out.append(_escape_plain_char(text[cursor]))
        cursor += 1
    return "".join(out)


def _consume_link(text: str, start: int) -> tuple[str, int] | None:
    if text[start] != "[":
        return None

    label_end = _find_unescaped(text, "](", start + 1)
    if label_end == -1:
        return None
    url_end = _find_unescaped(text, ")", label_end + 2)
    if url_end == -1:
        return None

    label = text[start + 1 : label_end]
    url = text[label_end + 2 : url_end].strip()
    if not label or not url:
        return None

    rendered = f"[{_escape_plain_text(label)}]({_escape_link_url(url)})"
    return rendered, url_end + 1


def _consume_wrapped_token(
    text: str,
    start: int,
    opening: str,
    closing: str,
    *,
    renderer,
    require_word_boundary: bool = False,
) -> tuple[str, int] | None:
    if not text.startswith(opening, start):
        return None
    if require_word_boundary and not _has_opening_token_boundary(text, start, len(opening)):
        return None

    end = _find_unescaped(text, closing, start + len(opening))
    if end == -1 or end <= start + len(opening):
        return None

    content = text[start + len(opening) : end]
    if not content.strip():
        return None
    if require_word_boundary and not _has_closing_token_boundary(text, end, len(closing)):
        return None
    return renderer(content), end + len(closing)


def _has_opening_token_boundary(text: str, marker_index: int, marker_length: int) -> bool:
    prev_char = text[marker_index - 1] if marker_index > 0 else ""
    next_index = marker_index + marker_length
    next_char = text[next_index] if next_index < len(text) else ""
    if prev_char and prev_char.isalnum():
        return False
    if not next_char or next_char.isspace():
        return False
    return True


def _has_closing_token_boundary(text: str, marker_index: int, marker_length: int) -> bool:
    prev_char = text[marker_index - 1] if marker_index > 0 else ""
    next_index = marker_index + marker_length
    next_char = text[next_index] if next_index < len(text) else ""
    if not prev_char or prev_char.isspace():
        return False
    if next_char and next_char.isalnum():
        return False
    return True


def _find_unescaped(text: str, needle: str, start: int) -> int:
    cursor = start
    while True:
        index = text.find(needle, cursor)
        if index == -1:
            return -1
        backslash_count = 0
        probe = index - 1
        while probe >= 0 and text[probe] == "\\":
            backslash_count += 1
            probe -= 1
        if backslash_count % 2 == 0:
            return index
        cursor = index + 1


def _render_inline_code(value: str) -> str:
    return f"`{_escape_code_text(value)}`"


def _render_code_block(*, language: str, code: str) -> str:
    clean_language = re.sub(r"[^A-Za-z0-9_+-]", "", language.strip())
    escaped_code = _escape_code_text(code.rstrip("\n"))
    if clean_language:
        return f"```{clean_language}\n{escaped_code}\n```"
    return f"```\n{escaped_code}\n```"


def _escape_plain_text(text: str) -> str:
    out: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] == "\\":
            if cursor + 1 < len(text):
                out.append(_escape_plain_char(text[cursor + 1]))
                cursor += 2
                continue
            out.append("\\\\")
            cursor += 1
            continue
        out.append(_escape_plain_char(text[cursor]))
        cursor += 1
    return "".join(out)


def _escape_plain_char(char: str) -> str:
    if char in _MARKDOWN_V2_SPECIAL_CHARS:
        return f"\\{char}"
    return char


def _escape_code_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _escape_link_url(url: str) -> str:
    return url.replace("\\", "\\\\").replace(")", "\\)")


def _split_plain_text(*, text: str, chunk_size: int) -> list[str]:
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


def _chunk_blocks(*, blocks: list[str], chunk_size: int) -> list[str]:
    if not blocks:
        return []

    chunks: list[str] = []
    current_blocks: list[str] = []
    current_length = 0
    for block in blocks:
        separator_length = 2 if current_blocks else 0
        projected_length = current_length + separator_length + len(block)
        if current_blocks and projected_length <= chunk_size:
            current_blocks.append(block)
            current_length = projected_length
            continue
        if not current_blocks and len(block) <= chunk_size:
            current_blocks = [block]
            current_length = len(block)
            continue

        if current_blocks:
            chunks.append("\n\n".join(current_blocks))
            current_blocks = []
            current_length = 0

        if len(block) <= chunk_size:
            current_blocks = [block]
            current_length = len(block)
            continue

        oversized_chunks = _split_large_block(block=block, chunk_size=chunk_size)
        if oversized_chunks:
            chunks.extend(oversized_chunks[:-1])
            current_blocks = [oversized_chunks[-1]]
            current_length = len(oversized_chunks[-1])

    if current_blocks:
        chunks.append("\n\n".join(current_blocks))
    return chunks


def _split_large_block(*, block: str, chunk_size: int) -> list[str]:
    if block.startswith("```"):
        return _split_code_block(block=block, chunk_size=chunk_size)

    parts: list[str] = []
    current = ""
    for line in block.split("\n"):
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if len(line) <= chunk_size:
            current = line
            continue
        parts.extend(_split_long_line(line=line, chunk_size=chunk_size))
    if current:
        parts.append(current)
    return parts


def _split_code_block(*, block: str, chunk_size: int) -> list[str]:
    opening_end = block.find("\n")
    language = block[3:opening_end] if opening_end != -1 else ""
    code = block[opening_end + 1 : -3] if opening_end != -1 and block.endswith("```") else block
    code_lines = code.split("\n")
    pieces: list[str] = []
    current = ""
    for line in code_lines:
        candidate = line if not current else f"{current}\n{line}"
        fenced_candidate = _render_code_block(language=language, code=candidate)
        if len(fenced_candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            pieces.append(_render_code_block(language=language, code=current))
            current = ""
        single_line_block = _render_code_block(language=language, code=line)
        if len(single_line_block) <= chunk_size:
            current = line
            continue
        for fragment in _split_plain_text(text=line, chunk_size=max(1, chunk_size - len(_render_code_block(language=language, code="")) - 1)):
            pieces.append(_render_code_block(language=language, code=fragment))
    if current:
        pieces.append(_render_code_block(language=language, code=current))
    return pieces


def _split_long_line(*, line: str, chunk_size: int) -> list[str]:
    plain_fallback = _fallback_plain_text(line)
    return _split_plain_text(text=plain_fallback, chunk_size=chunk_size)


def _fallback_plain_text(text: str) -> str:
    plain = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    plain = re.sub(r"`([^`]*)`", r"\1", plain)
    for marker in ("||", "*", "_", "~"):
        plain = plain.replace(marker, "")
    plain = re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!])", r"\1", plain)
    return _escape_plain_text(plain)
