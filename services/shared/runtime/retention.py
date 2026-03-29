from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


def cleanup_runtime_artifacts(
    workspace_path: Path,
    *,
    now: datetime | None = None,
    active_run_id: str | None = None,
) -> None:
    now_utc = now or datetime.now(timezone.utc)
    runs_path = workspace_path / "runs"
    if not runs_path.exists():
        return

    for run_dir in runs_path.iterdir():
        if not run_dir.is_dir():
            continue
        if active_run_id and run_dir.name == active_run_id:
            continue

        meta_path = run_dir / "run_meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        status = meta.get("status", "failed")
        completed_at = datetime.fromisoformat(meta["completed_at"])

        keep_days = 14 if status == "success" else 30
        cutoff = now_utc - timedelta(days=keep_days)
        if completed_at < cutoff:
            shutil.rmtree(run_dir, ignore_errors=True)
