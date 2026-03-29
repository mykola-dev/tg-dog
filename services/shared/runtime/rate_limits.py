from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path


class BoundedRateLimiter:
    def __init__(self, *, base_delay_seconds: float, max_chunks_per_run: int) -> None:
        self.base_delay_seconds = base_delay_seconds
        self.max_chunks_per_run = max_chunks_per_run

    def allow_chunk(self, chunk_index_1_based: int) -> bool:
        return chunk_index_1_based <= self.max_chunks_per_run

    def wait_base_delay(self) -> None:
        if self.base_delay_seconds > 0:
            time.sleep(self.base_delay_seconds)


class ExponentialBackoffPolicy:
    def __init__(self, *, max_retries: int = 3, base_delay_seconds: float = 0.0) -> None:
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds

    def delay_for_attempt(self, attempt_index_1_based: int) -> float:
        return self.base_delay_seconds * (2 ** max(attempt_index_1_based - 1, 0))


class ErrorCooldownTracker:
    def __init__(self, workspace_path: Path, *, failure_threshold: int = 2) -> None:
        self.path = workspace_path / "delivery_error_cooldown.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.failure_threshold = failure_threshold

    def _read(self) -> dict:
        if not self.path.exists():
            return {"failures": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload.setdefault("failures", {})
        return payload

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def should_block(self, error_code: str) -> bool:
        payload = self._read()
        entry = payload.get("failures", {}).get(error_code, {})
        return int(entry.get("count", 0)) >= self.failure_threshold

    def record_failure(self, error_code: str) -> None:
        payload = self._read()
        failures = dict(payload.get("failures", {}))
        entry = dict(failures.get(error_code, {}))
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_failed_at"] = datetime.now(timezone.utc).isoformat()
        failures[error_code] = entry
        payload["failures"] = failures
        self._write(payload)
