from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _write_run_meta(run_dir: Path, status: str, completed_at: datetime) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_meta.json").write_text(
        json.dumps({"status": status, "completed_at": completed_at.isoformat()}),
        encoding="utf-8",
    )


def test_retention_cleanup_removes_expired_artifacts(tmp_path: Path) -> None:
    from services.shared.runtime.retention import cleanup_runtime_artifacts

    workspace = tmp_path / "run_artifacts"
    runs = workspace / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    now = datetime(2026, 3, 25, tzinfo=timezone.utc)

    old_success = runs / "old-success"
    _write_run_meta(old_success, "success", now - timedelta(days=20))
    (old_success / "digest.json").write_text("{}", encoding="utf-8")

    old_failed = runs / "old-failed"
    _write_run_meta(old_failed, "failed", now - timedelta(days=40))
    (old_failed / "digest.json").write_text("{}", encoding="utf-8")

    recent_success = runs / "recent-success"
    _write_run_meta(recent_success, "success", now - timedelta(days=2))
    (recent_success / "digest.json").write_text("{}", encoding="utf-8")

    cleanup_runtime_artifacts(workspace, now=now, active_run_id="recent-success")

    assert not old_success.exists()
    assert not old_failed.exists()
    assert recent_success.exists()
