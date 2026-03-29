from __future__ import annotations

from pathlib import Path


def acquire_or_assert_run_lock(workspace_path: Path, run_id: str) -> bool:
    lock_file = workspace_path / ".active_run.lock"
    if lock_file.exists():
        active_run_id = lock_file.read_text(encoding="utf-8").strip()
        return active_run_id == run_id
    lock_file.write_text(run_id, encoding="utf-8")
    return True


def release_run_lock(workspace_path: Path, run_id: str) -> None:
    lock_file = workspace_path / ".active_run.lock"
    if not lock_file.exists():
        return
    active_run_id = lock_file.read_text(encoding="utf-8").strip()
    if active_run_id == run_id:
        lock_file.unlink()
