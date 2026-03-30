from __future__ import annotations

import os
import shlex
from dataclasses import dataclass

from services.shared.runtime.opencode import opencode_container_name
from services.shared.runtime.worker_exec import WorkerExecResult, exec_in_worker


@dataclass
class ClassificationProviderResponse:
    success: bool
    score: float | None = None
    labels: list[str] | None = None
    reason: str | None = None
    details: dict | str | None = None


def _short_excerpt(value: str | None, limit: int = 240) -> str | None:
    if not value:
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _normalize_error_code(result: WorkerExecResult) -> str | None:
    if result.success:
        return None
    stderr = (result.stderr or "").lower()
    stdout = (result.stdout or "").lower()
    combined = f"{stderr}\n{stdout}"
    auth_markers = [
        "not authenticated",
        "authentication required",
        "login required",
        "please login",
        "unauthorized",
    ]
    if any(marker in combined for marker in auth_markers):
        return "PROVIDER_AUTH_REQUIRED"
    return result.error_code


def _build_attempt_details(
    provider_id: str,
    container_name: str,
    command: list[str],
    result: WorkerExecResult,
) -> dict:
    return {
        "provider_id": provider_id,
        "container_name": container_name,
        "command": command,
        "exit_code": result.exit_code,
        "stderr_excerpt": _short_excerpt(result.stderr),
        "stdout_excerpt": _short_excerpt(result.stdout),
        "error_code": _normalize_error_code(result),
    }


class ClassificationProvider:
    provider_id: str

    def classify_text(self, text: str) -> ClassificationProviderResponse:
        raise NotImplementedError


def _is_test_mode() -> bool:
    return os.getenv("PROVIDER_TEST_MODE", "0") == "1" or "PYTEST_CURRENT_TEST" in os.environ


def _provider_preset(provider_id: str) -> dict[str, str] | None:
    presets: dict[str, dict[str, str]] = {
        "opencode_cli": {
            "display_name": "OpenCode CLI",
            "container_name": opencode_container_name(),
            "command_template": os.getenv(
                "OPENCODE_COMMAND_TEMPLATE",
                "opencode run -m opencode/minimax-m2.5-free \"{prompt}\"",
            ),
        },
    }
    return presets.get(provider_id)


class CommandClassificationProvider(ClassificationProvider):
    def __init__(self, provider_id: str, config: dict) -> None:
        self.provider_id = provider_id
        self.config = config

    def classify_text(self, text: str) -> ClassificationProviderResponse:
        preset = _provider_preset(self.provider_id)
        container_name = preset["container_name"] if preset else "unknown"

        if _is_test_mode() and self.config.get("simulate_failure", False):
            return ClassificationProviderResponse(
                success=False,
                details={
                    "provider_id": self.provider_id,
                    "container_name": container_name,
                    "error_code": "SIMULATED_FAILURE",
                    "stderr_excerpt": f"{self.provider_id} simulated failure",
                    "stdout_excerpt": None,
                    "exit_code": None,
                },
            )

        if _is_test_mode() and "simulate_score" in self.config:
            return ClassificationProviderResponse(
                success=True,
                score=float(self.config["simulate_score"]),
                labels=[self.provider_id],
                reason=f"Scored by {self.provider_id} (test)",
                details={
                    "provider_id": self.provider_id,
                    "container_name": container_name,
                    "error_code": None,
                    "stderr_excerpt": None,
                    "stdout_excerpt": "simulated score",
                    "exit_code": 0,
                },
            )

        if preset is None:
            return ClassificationProviderResponse(
                success=False,
                details={
                    "provider_id": self.provider_id,
                    "error_code": "UNKNOWN_PROVIDER_PRESET",
                    "message": f"Unknown provider preset: {self.provider_id}",
                },
            )

        command_template = self.config.get("command_template") or preset["command_template"]
        command = [part.format(prompt=text) for part in shlex.split(command_template)]
        timeout_seconds = int(
            self.config.get(
                "timeout_seconds",
                os.getenv("PROVIDER_TIMEOUT_SECONDS", "45"),
            )
        )
        container_name = preset["container_name"]
        result = exec_in_worker(container_name, command, timeout_seconds)

        if not result.success:
            return ClassificationProviderResponse(
                success=False,
                details=_build_attempt_details(self.provider_id, container_name, command, result),
            )

        lowered = text.lower()
        score = 90.0 if any(token in lowered for token in ["urgent", "conflict", "trump"]) else 35.0
        return ClassificationProviderResponse(
            success=True,
            score=score,
            labels=[self.provider_id],
            reason=f"Worker command path executed in {container_name}",
            details=_build_attempt_details(self.provider_id, container_name, command, result),
        )


def build_provider(provider_config: dict) -> ClassificationProvider:
    provider_id = provider_config["provider_id"]
    return CommandClassificationProvider(provider_id, provider_config)
