from __future__ import annotations

import json
from pathlib import Path


class DeliveryDedupStore:
    def __init__(self, workspace_path: Path) -> None:
        self.path = workspace_path / "delivery_dedup.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {
                "fingerprints": [],
                "completed_fingerprints": [],
                "in_progress": {},
            }
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("fingerprints", [])
        data.setdefault("completed_fingerprints", [])
        data.setdefault("in_progress", {})
        return data

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def is_duplicate_fingerprint(self, fingerprint: str) -> bool:
        data = self._read()
        return fingerprint in data.get("completed_fingerprints", []) or fingerprint in data.get(
            "fingerprints", []
        )

    def record_fingerprint(self, fingerprint: str) -> None:
        data = self._read()
        items = set(data.get("fingerprints", []))
        completed = set(data.get("completed_fingerprints", []))
        items.add(fingerprint)
        completed.add(fingerprint)
        in_progress = dict(data.get("in_progress", {}))
        in_progress.pop(fingerprint, None)
        self._write(
            {
                "fingerprints": sorted(items),
                "completed_fingerprints": sorted(completed),
                "in_progress": in_progress,
            }
        )

    def get_sent_count(self, fingerprint: str) -> int:
        data = self._read()
        in_progress = data.get("in_progress", {})
        item = in_progress.get(fingerprint, {})
        return int(item.get("sent_count", 0))

    def set_sent_count(self, fingerprint: str, sent_count: int) -> None:
        data = self._read()
        in_progress = dict(data.get("in_progress", {}))
        in_progress[fingerprint] = {"sent_count": int(sent_count)}
        data["in_progress"] = in_progress
        self._write(data)

    def clear_progress(self, fingerprint: str) -> None:
        data = self._read()
        in_progress = dict(data.get("in_progress", {}))
        in_progress.pop(fingerprint, None)
        data["in_progress"] = in_progress
        self._write(data)
