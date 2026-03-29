from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_dir(workspace_path: Path, run_id: str) -> Path:
    return workspace_path / "runs" / run_id


def ensure_run_dir(workspace_path: Path, run_id: str) -> Path:
    target = run_dir(workspace_path, run_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "logs").mkdir(exist_ok=True)
    return target


def artifact_path(workspace_path: Path, run_id: str, node_name: str) -> Path:
    base = ensure_run_dir(workspace_path, run_id)
    return base / f"{node_name}.json"


def safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lookup_artifact_by_node(manifest: dict[str, Any], node_name: str) -> str | None:
    return manifest.get("previous_outputs", {}).get(node_name)
