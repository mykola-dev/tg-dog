from __future__ import annotations

import argparse
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from services.shared.config import load_config
from services.shared.contracts.common import TargetDescriptor
from services.shared.contracts.run import RunManifest
from services.shared.runtime.artifacts import ensure_run_dir, read_json, safe_write_json
from services.shared.runtime.time_windows import manual_last_n_hours_window, now_utc


def create_initial_manifest(
    *,
    run_id: str,
    trigger_type: str,
    timezone_name: str,
    workspace_path: Path,
    hours: int = 24,
) -> Path:
    start, end = manual_last_n_hours_window(hours, now=now_utc())
    manifest = RunManifest(
        run_id=run_id,
        trigger_type=trigger_type,
        requested_at=now_utc(),
        timezone=timezone_name,
        window_mode="last_n_hours",
        time_window_start=start.astimezone(timezone.utc),
        time_window_end=end.astimezone(timezone.utc),
        selected_source_refs=[],
        enabled_nodes={
            "ocr": False,
            "heuristic-filter": False,
            "classification": False,
        },
        delivery_target=TargetDescriptor(target_id="self", target_kind="saved_messages"),
        workspace_path=str(workspace_path),
        safety_policy_version="v1",
    )
    run_path = ensure_run_dir(workspace_path, run_id)
    manifest_path = run_path / "manifest.json"
    safe_write_json(manifest_path, manifest.model_dump(mode="json"))
    return manifest_path


def update_previous_output(manifest_path: Path, *, node_name: str, artifact_ref: str) -> None:
    manifest = read_json(manifest_path)
    previous = dict(manifest.get("previous_outputs", {}))
    previous[node_name] = artifact_ref
    manifest["previous_outputs"] = previous
    safe_write_json(manifest_path, manifest)


def read_previous_output_ref(manifest_path: Path, *, node_name: str) -> str | None:
    manifest = read_json(manifest_path)
    return manifest.get("previous_outputs", {}).get(node_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create run manifest")
    parser.add_argument("--run-id", default=f"run-{uuid4()}")
    parser.add_argument("--trigger-type", choices=["manual", "scheduled"], required=True)
    parser.add_argument("--hours", type=int, default=24)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    path = create_initial_manifest(
        run_id=args.run_id,
        trigger_type=args.trigger_type,
        timezone_name=config.app_timezone,
        workspace_path=config.workspace_path,
        hours=args.hours,
    )
    print(path)


if __name__ == "__main__":
    main()
