from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import DialogItem
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.errors import TelegramAuthError

router = APIRouter()


def _get_wrapper() -> TelegramClientWrapper:
    session_path = Path(os.environ["TELEGRAM_SESSION_PATH"])
    return TelegramClientWrapper(session_path)


@router.get("/dialogs", response_model=list[DialogItem])
def get_dialogs():
    wrapper = _get_wrapper()
    try:
        dialogs = wrapper.list_dialogs()
    except TelegramAuthError:
        return JSONResponse(
            status_code=503,
            content={"error": "telegram account not connected"},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )
    return dialogs


@router.get("/dialogs/send-targets", response_model=list[DialogItem])
def get_send_targets(sender_mode: str = "user"):
    wrapper = _get_wrapper()
    try:
        dialogs = wrapper.list_dialogs()
    except TelegramAuthError:
        return JSONResponse(
            status_code=503,
            content={"error": "telegram account not connected"},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )

    send_targets = []
    if sender_mode != "bot":
        send_targets.append(
            {
                "id": "self",
                "name": "Saved Messages",
                "kind": "saved_messages",
                "username": "",
                "last_message_date": None,
                "can_send": True,
            }
        )
    send_targets.extend(dialog for dialog in dialogs if dialog.get("can_send"))
    return send_targets
