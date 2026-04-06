from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import AITextRequest, AITextResponse, ProviderAttemptSchema
from services.shared.providers.ai_text import run_ai_text_command

router = APIRouter()


@router.post("/ai/text", response_model=AITextResponse)
def ai_text(payload: AITextRequest):
    response = run_ai_text_command(
        command_template=payload.command_template,
        prompt=payload.prompt,
        system_prompt=payload.system_prompt,
    )
    if not response.success:
        return JSONResponse(
            status_code=503,
            content={
                "error": "AI text provider command failed",
                "provider_id": response.provider_id,
                "provider_attempts": [
                    ProviderAttemptSchema(
                        provider_id=response.provider_id or "unknown",
                        success=False,
                        details=response.details,
                    ).model_dump(mode="json")
                ],
            },
        )

    return {
        "output_text": response.output_text or "",
        "provider_id": response.provider_id or "unknown",
        "provider_attempts": [
            ProviderAttemptSchema(
                provider_id=response.provider_id or "unknown",
                success=True,
                details=response.details,
            ).model_dump(mode="json")
        ],
        "raw_output": response.output_text or "",
    }
