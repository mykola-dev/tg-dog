from __future__ import annotations

import shlex
from dataclasses import dataclass

from services.shared.runtime.worker_exec import WorkerExecResult, exec_in_worker, exec_in_worker_with_input, opencode_runtime_name


@dataclass
class AITextProviderResponse:
    success: bool
    output_text: str | None = None
    provider_id: str | None = None
    details: dict | str | None = None


def _provider_from_command(command_template: str) -> tuple[str, str]:
    return (
        "opencode_cli",
        opencode_runtime_name(),
    )


def run_ai_text_command(*, command_template: str, prompt: str, system_prompt: str = "", timeout_seconds: int = 180) -> AITextProviderResponse:
    provider_id, runtime_name = _provider_from_command(command_template)
    template_parts = shlex.split(command_template)
    stdin_prompt = _build_stdin_prompt(system_prompt=system_prompt, prompt=prompt)

    if provider_id == "opencode_cli":
        command = [part for part in template_parts if part != "{prompt}"]
        result: WorkerExecResult = exec_in_worker_with_input(
            command,
            timeout_seconds,
            stdin_text=stdin_prompt,
        )
    else:
        command = [part.format(prompt=stdin_prompt) for part in template_parts]
        result = exec_in_worker(command, timeout_seconds)

    details = {
        "provider_id": provider_id,
        "runtime_name": runtime_name,
        "command": command,
        "stdin_length": len(stdin_prompt) if provider_id == "opencode_cli" else None,
        "exit_code": result.exit_code,
        "stderr": result.stderr,
        "stdout": result.stdout,
        "error_code": result.error_code,
    }
    if not result.success:
        return AITextProviderResponse(success=False, provider_id=provider_id, details=details)
    return AITextProviderResponse(
        success=True,
        output_text=result.stdout or "",
        provider_id=provider_id,
        details=details,
    )


def _build_stdin_prompt(*, system_prompt: str, prompt: str) -> str:
    prompt_text = (prompt or "").strip()
    system_text = (system_prompt or "").strip()
    if system_text and prompt_text:
        return f"{system_text}\n\n{prompt_text}"
    return system_text or prompt_text
