from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/n8n")


class BridgeProbeResponse(BaseModel):
    ok: bool
    service: str
    bridge: str
    timestamp: str


@router.get("/bridge-probe", response_model=BridgeProbeResponse)
def bridge_probe() -> dict[str, object]:
    return {
        "ok": True,
        "service": "tg-dog-api",
        "bridge": "n8n",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
