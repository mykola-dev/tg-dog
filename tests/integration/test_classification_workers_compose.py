from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_classification_workers_with_isolated_volumes() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "opencode-worker:" in compose
    assert "container_name: ${COMPOSE_PROJECT_NAME:-tg-dog}-opencode-worker" in compose
    assert "- opencode_state:/workspace/opencode" in compose
    assert "- /var/run/docker.sock:/var/run/docker.sock" in compose
    assert "opencode_state:" in compose

    opencode_block = compose.split("opencode-worker:", 1)[1]

    assert "ports:" not in opencode_block
    assert "- ./" not in opencode_block
    assert "- ./:" not in opencode_block
