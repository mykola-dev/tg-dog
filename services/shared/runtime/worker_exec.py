from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class WorkerExecResult:
    success: bool
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    error_code: str | None


def exec_in_worker(container_name: str, command: list[str], timeout_seconds: int) -> WorkerExecResult:
    return exec_in_worker_with_input(container_name, command, timeout_seconds, stdin_text=None)


def exec_in_worker_with_input(
    container_name: str,
    command: list[str],
    timeout_seconds: int,
    *,
    stdin_text: str | None,
) -> WorkerExecResult:
    docker_command = ["docker", "exec"]
    if stdin_text is not None:
        docker_command.append("-i")
    docker_command.extend([container_name, *command])
    try:
        result = subprocess.run(
            docker_command,
            capture_output=True,
            text=True,
            input=stdin_text,
            check=False,
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        return WorkerExecResult(
            success=False,
            stdout=None,
            stderr=str(exc),
            exit_code=None,
            error_code="WORKER_COMMAND_TIMEOUT",
        )
    except Exception as exc:
        return WorkerExecResult(
            success=False,
            stdout=None,
            stderr=str(exc),
            exit_code=None,
            error_code="WORKER_EXEC_ERROR",
        )

    stdout = (result.stdout or "").strip() or None
    stderr = (result.stderr or "").strip() or None
    if result.returncode != 0:
        return WorkerExecResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
            exit_code=result.returncode,
            error_code="WORKER_COMMAND_FAILED",
        )

    return WorkerExecResult(
        success=True,
        stdout=stdout,
        stderr=stderr,
        exit_code=result.returncode,
        error_code=None,
    )
