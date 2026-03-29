from __future__ import annotations

from services.shared.providers.classification import CommandClassificationProvider
from services.shared.runtime.worker_exec import WorkerExecResult


def test_opencode_command_template_targets_minimax_model_by_default(monkeypatch) -> None:
    seen_commands: list[list[str]] = []

    def _fake_exec(_container_name: str, command: list[str], _timeout_seconds: int) -> WorkerExecResult:
        seen_commands.append(command)
        return WorkerExecResult(success=True, stdout="ok", stderr=None, exit_code=0, error_code=None)

    monkeypatch.setattr("services.shared.providers.classification.exec_in_worker", _fake_exec)
    monkeypatch.setenv("OPENCODE_CONTAINER_NAME", "telegram-digest-opencode-worker")
    monkeypatch.delenv("OPENCODE_COMMAND_TEMPLATE", raising=False)

    provider = CommandClassificationProvider("opencode_cli", {"provider_id": "opencode_cli"})
    response = provider.classify_text("provider smoke prompt")

    assert response.success is True
    assert seen_commands, "expected opencode worker command to run"
    assert seen_commands[0][:3] == ["opencode", "run", "-m"]
    assert seen_commands[0][3] == "opencode/minimax-m2.5-free"


def test_opencode_command_template_can_be_overridden(monkeypatch) -> None:
    seen_commands: list[list[str]] = []

    def _fake_exec(_container_name: str, command: list[str], _timeout_seconds: int) -> WorkerExecResult:
        seen_commands.append(command)
        return WorkerExecResult(success=True, stdout="ok", stderr=None, exit_code=0, error_code=None)

    monkeypatch.setattr("services.shared.providers.classification.exec_in_worker", _fake_exec)
    monkeypatch.setenv("OPENCODE_CONTAINER_NAME", "telegram-digest-opencode-worker")
    monkeypatch.setenv("OPENCODE_COMMAND_TEMPLATE", "opencode run -m opencode/mimo-v2-pro-free \"{prompt}\"")

    provider = CommandClassificationProvider("opencode_cli", {"provider_id": "opencode_cli"})
    response = provider.classify_text("provider smoke prompt")

    assert response.success is True
    assert seen_commands, "expected opencode worker command to run"
    assert seen_commands[0][:4] == ["opencode", "run", "-m", "opencode/mimo-v2-pro-free"]
