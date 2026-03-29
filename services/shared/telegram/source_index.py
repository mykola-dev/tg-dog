from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SourceRecord:
    source_id: str
    source_kind: str
    source_title: str
    is_bot: bool = False
    is_secret_chat: bool = False
