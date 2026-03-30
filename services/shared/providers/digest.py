from __future__ import annotations

import os
import shlex
from dataclasses import dataclass

from services.shared.runtime.opencode import opencode_container_name
from services.shared.runtime.worker_exec import WorkerExecResult, exec_in_worker, exec_in_worker_with_input


@dataclass
class DigestProviderResponse:
    success: bool
    output_text: str | None = None
    provider_id: str | None = None
    details: dict | str | None = None


def _provider_from_command(command_template: str) -> tuple[str, str]:
    return (
        "opencode_cli",
        opencode_container_name(),
    )


def run_digest_command(*, command_template: str, prompt: str, timeout_seconds: int = 180) -> DigestProviderResponse:
    provider_id, container_name = _provider_from_command(command_template)
    template_parts = shlex.split(command_template)

    if provider_id == "opencode_cli":
        command = [part for part in template_parts if part != "{prompt}"]
        result: WorkerExecResult = exec_in_worker_with_input(
            container_name,
            command,
            timeout_seconds,
            stdin_text=prompt,
        )
    else:
        command = [part.format(prompt=prompt) for part in template_parts]
        result = exec_in_worker(container_name, command, timeout_seconds)

    details = {
        "provider_id": provider_id,
        "container_name": container_name,
        "command": command,
        "stdin_length": len(prompt) if provider_id == "opencode_cli" else None,
        "exit_code": result.exit_code,
        "stderr": result.stderr,
        "stdout": result.stdout,
        "error_code": result.error_code,
    }
    if not result.success:
        return DigestProviderResponse(success=False, provider_id=provider_id, details=details)
    return DigestProviderResponse(
        success=True,
        output_text=result.stdout or "",
        provider_id=provider_id,
        details=details,
    )
