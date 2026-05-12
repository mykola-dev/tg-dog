from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import PostMessageRequest, PostMessageResponse
from services.shared.config import load_config
from services.shared.telegram.markdown_v2 import (
    HTML_PARSE_MODE,
    PLAIN_TEXT_PARSE_MODE,
    normalize_parse_mode,
    split_html_chunks,
    split_plain_text_chunks,
)
from services.shared.telegram.bot_client import TelegramBotClient
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.errors import TelegramAuthError, TelegramDeliveryError

router = APIRouter()
SUPPORTED_DELIVERY_MODES = {"auto", "send", "forward", "copy"}


def _get_wrapper() -> TelegramClientWrapper:
    session_path = Path(os.environ["TELEGRAM_SESSION_PATH"])
    return TelegramClientWrapper(session_path)


def _get_bot_client() -> TelegramBotClient:
    config = load_config()
    if not config.telegram_bot_token:
        raise TelegramDeliveryError(
            code="BOT_TOKEN_NOT_CONFIGURED",
            message="Telegram bot token is not configured",
            retryable=False,
        )
    return TelegramBotClient(config.telegram_bot_token)


@router.post("/post/message", response_model=PostMessageResponse)
def post_message(payload: PostMessageRequest):
    parse_mode = normalize_parse_mode(payload.parse_mode, default=PLAIN_TEXT_PARSE_MODE)
    if payload.sender_mode not in {"user", "bot"}:
        return JSONResponse(status_code=400, content={"error": "Unsupported sender mode", "code": "POST_SENDER_MODE_UNSUPPORTED"})
    if payload.delivery_mode not in SUPPORTED_DELIVERY_MODES:
        return JSONResponse(status_code=400, content={"error": "Unsupported delivery mode", "code": "POST_DELIVERY_MODE_UNSUPPORTED"})
    if parse_mode not in {PLAIN_TEXT_PARSE_MODE, HTML_PARSE_MODE}:
        return JSONResponse(status_code=400, content={"error": "Unsupported parse mode", "code": "POST_PARSE_MODE_UNSUPPORTED"})

    raw_chunks = [chunk for chunk in payload.delivery_chunks if isinstance(chunk, str) and chunk.strip()]
    chunks: list[str] = []
    if parse_mode == HTML_PARSE_MODE:
        html_source = "\n\n".join(chunk.strip() for chunk in raw_chunks) if raw_chunks else payload.text.strip()
        if html_source:
            chunks = split_html_chunks(html_source)
    else:
        chunks = [chunk.strip() for chunk in raw_chunks]
        if not chunks and payload.text.strip():
            chunks = split_plain_text_chunks(payload.text)

    if parse_mode == HTML_PARSE_MODE and not chunks and payload.text.strip() and not raw_chunks:
        chunks = split_html_chunks(payload.text)
    if not chunks and not payload.media_file_ref:
        return JSONResponse(status_code=400, content={"error": "Message text is empty", "code": "POST_EMPTY_MESSAGE"})

    try:
        sender = _get_bot_client() if payload.sender_mode == "bot" else _get_wrapper()
        effective_delivery_mode = payload.delivery_mode
        has_telegram_origin = bool(payload.source_id and payload.source_message_id)
        if effective_delivery_mode == "auto":
            effective_delivery_mode = "forward" if has_telegram_origin else "send"

        if effective_delivery_mode in {"forward", "copy"}:
            if not has_telegram_origin:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Forward/copy delivery requires source_id and source_message_id",
                        "code": "POST_SOURCE_MESSAGE_REQUIRED",
                    },
                )

            if payload.sender_mode == "bot":
                if effective_delivery_mode == "forward":
                    sent_refs = [
                        sender.forward_message(
                            target_id=payload.target_id,
                            source_id=str(payload.source_id),
                            source_message_id=str(payload.source_message_id),
                        )
                    ]
                else:
                    sent_refs = [
                        sender.copy_message(
                            target_id=payload.target_id,
                            source_id=str(payload.source_id),
                            source_message_id=str(payload.source_message_id),
                        )
                    ]
            else:
                sent_refs = [
                    sender.repost_message(
                        target_id=payload.target_id,
                        source_id=str(payload.source_id),
                        source_message_id=str(payload.source_message_id),
                        mode=effective_delivery_mode,
                    )
                ]
        elif payload.media_file_ref:
            caption_text = chunks[0] if chunks else ""
            if payload.sender_mode == "bot":
                sent_refs = [
                        sender.send_media_chunk(
                            target_id=payload.target_id,
                            media_file_ref=payload.media_file_ref,
                            media_kind=payload.media_kind,
                            caption_text=caption_text,
                            parse_mode=parse_mode,
                        )
                    ]
            else:
                sent_refs = [
                    sender.send_text_chunk(
                        target_id=payload.target_id,
                        chunk_text=caption_text,
                        parse_mode=parse_mode,
                        media_file_ref=payload.media_file_ref,
                        media_mime_type=payload.media_mime_type,
                        media_kind=payload.media_kind,
                    )
                ]
        else:
            sent_refs = [
                sender.send_text_chunk(
                    target_id=payload.target_id,
                    chunk_text=chunk,
                    parse_mode=parse_mode,
                )
                for chunk in chunks
            ]
    except TelegramAuthError:
        return JSONResponse(status_code=503, content={"error": "telegram account not connected"})
    except TelegramDeliveryError as exc:
        return JSONResponse(status_code=503, content={"error": exc.message, "code": exc.code})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {
        "delivery_status": "sent",
        "target_id": payload.target_id,
        "sent_message_refs": sent_refs,
    }
