from __future__ import annotations

import json
from pathlib import Path


DEFAULT_TOGGLES = {"ocr": False, "classification": False}


def _toggles_path(workspace_path: Path) -> Path:
    return workspace_path / "node_toggles.json"


def load_node_toggles(workspace_path: Path) -> dict[str, bool]:
    path = _toggles_path(workspace_path)
    if not path.exists():
        return dict(DEFAULT_TOGGLES)
    raw = json.loads(path.read_text(encoding="utf-8"))
    result = dict(DEFAULT_TOGGLES)
    result.update({k: bool(v) for k, v in raw.items() if k in DEFAULT_TOGGLES})
    return result


def save_node_toggles(workspace_path: Path, toggles: dict[str, bool]) -> None:
    payload = dict(DEFAULT_TOGGLES)
    payload.update({k: bool(v) for k, v in toggles.items() if k in DEFAULT_TOGGLES})
    path = _toggles_path(workspace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
