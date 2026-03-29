from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import CanonicalMessageItem, MessageReadRequest, RandomMessageRequest
from services.shared.config import load_config
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.errors import TelegramAuthError, TelegramOperationalError

router = APIRouter()


def _get_wrapper() -> TelegramClientWrapper:
    session_path = Path(os.environ["TELEGRAM_SESSION_PATH"])
    return TelegramClientWrapper(session_path)


@router.post("/messages/read", response_model=list[CanonicalMessageItem])
def read_messages(payload: MessageReadRequest):
    wrapper = _get_wrapper()
    config = load_config()
    now = datetime.now(UTC)
    time_window_start = now - timedelta(hours=payload.lookback_hours)
    run_id = f"n8n-read-{uuid.uuid4().hex[:12]}"
    try:
        messages = wrapper.fetch_messages(
            source_refs=[str(dialog_id) for dialog_id in payload.dialog_ids],
            limit_per_source=500,
            time_window_start=time_window_start,
            time_window_end=now,
            workspace_path=config.workspace_path,
            run_id=run_id,
            include_media=payload.include_media,
        )
    except TelegramAuthError:
        return JSONResponse(status_code=503, content={"error": "telegram account not connected"})
    except TelegramOperationalError as exc:
        return JSONResponse(status_code=503, content={"error": exc.message, "code": exc.code})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return messages


@router.post("/messages/random", response_model=CanonicalMessageItem)
def random_message(payload: RandomMessageRequest):
    wrapper = _get_wrapper()
    config = load_config()
    run_id = f"n8n-random-{uuid.uuid4().hex[:12]}"
    try:
        message = wrapper.pick_random_message(
            source_ref=str(payload.dialog_id),
            workspace_path=config.workspace_path,
            run_id=run_id,
            skip_empty_text=payload.skip_empty_text,
            ignore_self=payload.ignore_self,
            ignore_service_messages=payload.ignore_service_messages,
        )
    except TelegramAuthError:
        return JSONResponse(status_code=503, content={"error": "telegram account not connected"})
    except TelegramOperationalError as exc:
        return JSONResponse(status_code=503, content={"error": exc.message, "code": exc.code})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    if not message:
        return JSONResponse(
            status_code=404,
            content={"error": "No matching messages found for the selected dialog", "code": "RANDOM_MESSAGE_NOT_FOUND"},
        )
    return message
