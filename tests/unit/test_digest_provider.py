from unittest.mock import patch

from services.shared.providers.ai_text import run_ai_text_command
from services.shared.runtime.worker_exec import WorkerExecResult


def test_run_ai_text_command_uses_local_opencode_runtime_by_default(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_RUNTIME_NAME", "api")

    with patch("services.shared.providers.ai_text.exec_in_worker_with_input") as mocked_exec:
        mocked_exec.return_value = WorkerExecResult(
            success=True,
            stdout="# Digest",
            stderr=None,
            exit_code=0,
            error_code=None,
        )
        result = run_ai_text_command(
            command_template='opencode run -m opencode/minimax-m2.5-free "{prompt}"',
            prompt="hello",
        )

    assert result.success is True
    assert result.provider_id == "opencode_cli"
    mocked_exec.assert_called_once_with(
        ["opencode", "run", "-m", "opencode/minimax-m2.5-free"],
        180,
        stdin_text="hello",
    )


def test_run_ai_text_command_keeps_prompt_out_of_opencode_argv() -> None:
    long_prompt = "x" * 10000

    with patch("services.shared.providers.ai_text.exec_in_worker_with_input") as mocked_exec:
        mocked_exec.return_value = WorkerExecResult(
            success=False,
            stdout=None,
            stderr="boom",
            exit_code=None,
            error_code="WORKER_EXEC_ERROR",
        )

        result = run_ai_text_command(
            command_template='opencode run -m opencode/minimax-m2.5-free "{prompt}"',
            prompt=long_prompt,
        )

    assert result.success is False
    assert result.details["command"] == ["opencode", "run", "-m", "opencode/minimax-m2.5-free"]
    assert result.details["stdin_length"] == len(long_prompt)
