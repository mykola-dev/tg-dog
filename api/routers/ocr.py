from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import CanonicalMessageItem, MessageOCREnrichRequest
from services.shared.contracts.message import CanonicalMessage
from services.shared.ocr_enrichment import enrich_messages_with_ocr

router = APIRouter()


@router.post("/ocr/messages", response_model=list[CanonicalMessageItem])
def enrich_messages(payload: MessageOCREnrichRequest):
    try:
        messages = [CanonicalMessage.model_validate(item.model_dump(mode="json")) for item in payload.messages]
        enriched_messages, _metrics = enrich_messages_with_ocr(messages)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return enriched_messages
