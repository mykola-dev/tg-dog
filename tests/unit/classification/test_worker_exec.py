from __future__ import annotations

from subprocess import CompletedProcess

from services.shared.runtime.worker_exec import exec_in_worker, exec_in_worker_with_input


def test_worker_exec_returns_stdout_on_zero_exit(monkeypatch) -> None:
    def _fake_run(*_args, **_kwargs):
        return CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("services.shared.runtime.worker_exec.subprocess.run", _fake_run)

    result = exec_in_worker(
        container_name="telegram-digest-opencode-worker",
        command=["opencode", "--version"],
        timeout_seconds=30,
    )

    assert result.success is True
    assert result.stdout == "ok"
    assert result.exit_code == 0
    assert result.error_code is None


def test_worker_exec_returns_structured_error_on_nonzero_exit(monkeypatch) -> None:
    def _fake_run(*_args, **_kwargs):
        return CompletedProcess(args=[], returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr("services.shared.runtime.worker_exec.subprocess.run", _fake_run)

    result = exec_in_worker(
        container_name="telegram-digest-opencode-worker",
        command=["opencode", "run", "hello"],
        timeout_seconds=30,
    )

    assert result.success is False
    assert result.exit_code == 2
    assert result.stderr == "boom"
    assert result.error_code == "WORKER_COMMAND_FAILED"


def test_worker_exec_marks_timeout_as_operational_error(monkeypatch) -> None:
    def _fake_run(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("services.shared.runtime.worker_exec.subprocess.run", _fake_run)

    result = exec_in_worker(
        container_name="telegram-digest-opencode-worker",
        command=["opencode", "run", "hello"],
        timeout_seconds=1,
    )

    assert result.success is False
    assert result.error_code == "WORKER_COMMAND_TIMEOUT"
    assert result.exit_code is None


def test_worker_exec_passes_stdin_to_subprocess(monkeypatch) -> None:
    captured = {}

    def _fake_run(*args, **kwargs):
        captured["input"] = kwargs.get("input")
        return CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("services.shared.runtime.worker_exec.subprocess.run", _fake_run)

    result = exec_in_worker_with_input(
        container_name="telegram-digest-opencode-worker",
        command=["opencode", "run", "-m", "model"],
        timeout_seconds=30,
        stdin_text="hello from stdin",
    )

    assert result.success is True
    assert captured["input"] == "hello from stdin"
