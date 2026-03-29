from __future__ import annotations

import argparse
import json

from services.shared.config import load_config
from services.shared.runtime.retention import cleanup_runtime_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup maintenance command")
    parser.add_argument("--active-run-id", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    cleanup_runtime_artifacts(
        config.workspace_path,
        active_run_id=args.active_run_id or None,
    )
    print(json.dumps({"status": "ok"}))


if __name__ == "__main__":
    main()
