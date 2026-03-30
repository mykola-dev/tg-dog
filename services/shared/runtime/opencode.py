from __future__ import annotations

import os


def opencode_container_name() -> str:
    configured = os.getenv("OPENCODE_CONTAINER_NAME")
    if configured:
        return configured

    project_name = os.getenv("COMPOSE_PROJECT_NAME", "tg-dog")
    return f"{project_name}-opencode-worker"
