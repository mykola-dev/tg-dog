from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import CleanupRequest, CleanupResponse
from services.shared.contracts.message import CanonicalMessage
from services.shared.formatting import format_messages

router = APIRouter()


@router.post("/messages/cleanup", response_model=CleanupResponse)
def cleanup_messages(payload: CleanupRequest):
    try:
        messages = [CanonicalMessage.model_validate(item.model_dump(mode="json")) for item in payload.messages]
        formatted = format_messages(
            messages,
            mode=payload.mode,
            output_format=payload.output_format,
            include_source_title=payload.include_source_title,
            include_timestamp=payload.include_timestamp,
            include_ocr_text=payload.include_ocr_text,
            max_characters_per_message=payload.max_characters_per_message,
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return formatted
