from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OCRResultItem(BaseModel):
    source_id: str
    message_id: str
    media_index: int
    ocr_status: Literal["done", "failed", "skipped"]
    extracted_text: str | None = None
    confidence_hint: float | None = None


class OCRItemFailure(BaseModel):
    source_id: str
    message_id: str
    media_index: int
    code: str
    message: str


class OCROutput(BaseModel):
    message_ocr_results: list[OCRResultItem] = Field(default_factory=list)
    provider_kind: str
    failed_items: list[OCRItemFailure] = Field(default_factory=list)
