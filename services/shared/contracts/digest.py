from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DigestItem(BaseModel):
    source_id: str
    message_id: str
    text: str


class DigestSection(BaseModel):
    section_key: Literal["main", "filtered", "unclassified"]
    title: str
    items: list[DigestItem] = Field(default_factory=list)
    summary_text: str


class DigestOutput(BaseModel):
    digest_fingerprint: str
    sections: list[DigestSection] = Field(default_factory=list)
    message_count_summary: dict[str, int] = Field(default_factory=dict)
    rendered_text_markdown: str | None = None
    rendered_text_plain: str
    delivery_chunks: list[str] = Field(default_factory=list)
    whitelist_deliveries: dict[str, list[DigestItem]] = Field(default_factory=dict)
