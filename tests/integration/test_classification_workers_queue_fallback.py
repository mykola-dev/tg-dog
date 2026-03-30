from __future__ import annotations

import json
from pathlib import Path

from services.classification.main import main
from services.shared.runtime.worker_exec import WorkerExecResult


def test_queue_marks_output_degraded_when_only_worker_fails(monkeypatch, capsys, tmp_path: Path) -> None:
    workspace = tmp_path / "run_artifacts"
    sessions = tmp_path / "telegram_sessions"
    run_dir = workspace / "runs" / "classification-worker-fallback"
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)

    messages = {
        "messages": [
            {
                "schema_version": "v1",
                "source_kind": "channel",
                "source_id": "c1",
                "source_title": "News",
                "message_id": "m1",
                "message_timestamp": "2026-03-21T10:00:00Z",
                "is_outbound": False,
                "is_from_self": False,
                "is_service_message": False,
                "media_items": [],
                "ingestion_meta": {},
                "text": "urgent security update",
            }
        ]
    }
    (run_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")

    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "telegram_digest")
    monkeypatch.setenv("POSTGRES_USER", "telegram_digest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "telegram_digest")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(sessions))
    monkeypatch.setenv("APP_TIMEZONE", "UTC")
    monkeypatch.setenv("OPENCODE_RUNTIME_NAME", "api")

    calls: list[list[str]] = []

    def _fake_exec(command: list[str], _timeout_seconds: int) -> WorkerExecResult:
        calls.append(command)
        return WorkerExecResult(
            success=False,
            stdout=None,
            stderr="provider unavailable",
            exit_code=2,
            error_code="WORKER_COMMAND_FAILED",
        )

    monkeypatch.setattr("services.shared.providers.classification.exec_in_worker", _fake_exec)
    monkeypatch.setattr(
        "sys.argv",
        [
            "classification",
            "--run-id",
            "classification-worker-fallback",
            "--messages-ref",
            "runs/classification-worker-fallback/messages.json",
            "--payload-json",
            json.dumps(
                {
                    "rules": [],
                    "providers": [
                        {"provider_id": "opencode_cli", "enabled": True},
                    ],
                }
            ),
        ],
    )

    main()
    envelope = json.loads(capsys.readouterr().out)
    classification = json.loads((workspace / envelope["payload_ref"]).read_text(encoding="utf-8"))

    assert calls == [["opencode", "run", "-m", "opencode/minimax-m2.5-free", "urgent security update"]]
    assert classification["degraded"] is True
    assert classification["provider_kind"] == "none"
    assert len(classification["provider_attempts"]) == 1
    assert classification["provider_attempts"][0]["success"] is False
    assert classification["provider_attempts"][0]["details"]["runtime_name"] == "api"
