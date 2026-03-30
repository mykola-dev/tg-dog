from __future__ import annotations

from services.shared.providers.classification import CommandClassificationProvider
from services.shared.runtime.worker_exec import WorkerExecResult


def test_opencode_provider_executes_in_api_runtime(monkeypatch) -> None:
    calls: list[tuple[list[str], int]] = []

    def _fake_exec(command: list[str], timeout_seconds: int) -> WorkerExecResult:
        calls.append((command, timeout_seconds))
        return WorkerExecResult(success=True, stdout='{"score":35}', stderr=None, exit_code=0, error_code=None)

    monkeypatch.setattr("services.shared.providers.classification.exec_in_worker", _fake_exec)
    monkeypatch.setenv("OPENCODE_RUNTIME_NAME", "api")

    provider = CommandClassificationProvider("opencode_cli", {"provider_id": "opencode_cli"})
    response = provider.classify_text("normal update")

    assert response.success is True
    assert response.score == 35.0
    assert response.details["runtime_name"] == "api"
    assert calls[0][1] == 45


def test_auth_failure_normalizes_to_provider_auth_required(monkeypatch) -> None:
    def _fake_exec(_command: list[str], _timeout_seconds: int) -> WorkerExecResult:
        return WorkerExecResult(
            success=False,
            stdout=None,
            stderr="not authenticated",
            exit_code=1,
            error_code="WORKER_COMMAND_FAILED",
        )

    monkeypatch.setattr("services.shared.providers.classification.exec_in_worker", _fake_exec)
    monkeypatch.setenv("OPENCODE_RUNTIME_NAME", "api")

    provider = CommandClassificationProvider("opencode_cli", {"provider_id": "opencode_cli"})
    response = provider.classify_text("urgent incident")

    assert response.success is False
    assert isinstance(response.details, dict)
    assert response.details["error_code"] == "PROVIDER_AUTH_REQUIRED"
