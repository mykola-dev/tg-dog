from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_runs_opencode_in_api_with_persisted_state() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "api:" in compose
    assert "- opencode_state:/workspace/opencode" in compose
    assert "opencode_state:" in compose
    assert "/var/run/docker.sock" not in compose
