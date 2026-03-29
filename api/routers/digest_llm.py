from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import DigestRequest, DigestResponse, ProviderAttemptSchema
from services.shared.providers.digest import run_digest_command
from services.shared.telegram.markdown_v2 import normalize_parse_mode, prepare_digest_delivery

router = APIRouter()


@router.post("/digest/messages", response_model=DigestResponse)
def digest_messages(payload: DigestRequest):
    output_format = normalize_parse_mode(payload.output_format, default="markdown_v2")
    prompt = f"{payload.system_prompt.strip()}\n\nMessages:\n\n{payload.formatted_text.strip()}".strip()
    response = run_digest_command(command_template=payload.command_template, prompt=prompt)
    if not response.success:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Digest provider command failed",
                "provider_id": response.provider_id,
                "provider_attempts": [ProviderAttemptSchema(provider_id=response.provider_id or "unknown", success=False, details=response.details).model_dump(mode="json")],
            },
        )

    try:
        prepared = prepare_digest_delivery(raw_text=response.output_text or "", output_format=output_format)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc), "code": "DIGEST_OUTPUT_FORMAT_UNSUPPORTED"})

    lines = [line for line in (payload.formatted_text or "").splitlines() if line.strip()]
    source_count = sum(1 for line in lines if line.startswith("## ") or line.startswith("["))
    return {
        "digest_text": prepared.text,
        "format": output_format,
        "parse_mode": output_format,
        "delivery_chunks": prepared.chunks,
        "provider_id": response.provider_id or "unknown",
        "provider_attempts": [
            ProviderAttemptSchema(
                provider_id=response.provider_id or "unknown",
                success=True,
                details=response.details,
            ).model_dump(mode="json")
        ],
        "message_count": max(source_count, 1),
        "source_count": max(source_count, 1),
        "raw_output": response.output_text or "",
    }
