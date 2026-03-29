import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _env(workspace: Path, sessions: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "telegram_digest",
            "POSTGRES_USER": "telegram_digest",
            "POSTGRES_PASSWORD": "telegram_digest",
            "WORKSPACE_PATH": str(workspace),
            "TELEGRAM_SESSION_PATH": str(sessions),
            "APP_TIMEZONE": "UTC",
            "APP_MASTER_KEY": "test_master_key",
        }
    )
    return env


def _write_messages(run_dir: Path) -> None:
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
                "text": "trump election update",
            }
        ]
    }
    (run_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")


def _run_classification(run_id: str, workspace: Path, sessions: Path, payload: dict) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.classification.main",
            "--run-id",
            run_id,
            "--messages-ref",
            f"runs/{run_id}/messages.json",
            "--payload-json",
            json.dumps(payload),
        ],
        cwd=ROOT,
        env=_env(workspace, sessions),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    ref = envelope["payload_ref"]
    return json.loads((workspace / ref).read_text(encoding="utf-8"))


def test_suppress_rule_moves_high_score_item_to_filtered_section(tmp_path: Path) -> None:
    runtime = tmp_path / "classification_filtered"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_id = "classification-filtered"
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _write_messages(run_dir)

    data = _run_classification(
        run_id,
        workspace,
        sessions,
        {
            "rules": [
                {
                    "rule_id": "r1",
                    "name": "Suppress Trump",
                    "mode": "suppress_topic",
                    "prompt_text": "trump",
                    "threshold": 80,
                    "enabled": True,
                }
            ],
            "providers": [
                {"provider_id": "opencode_cli", "enabled": True, "simulate_score": 95}
            ],
        },
    )
    record = data["message_scores"][0]
    assert record["action"] == "filtered"


def test_classification_failure_sends_item_to_unclassified_when_enabled(tmp_path: Path) -> None:
    runtime = tmp_path / "classification_unclassified"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_id = "classification-unclassified"
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _write_messages(run_dir)

    data = _run_classification(
        run_id,
        workspace,
        sessions,
        {
            "rules": [
                {
                    "rule_id": "r1",
                    "name": "Suppress Trump",
                    "mode": "suppress_topic",
                    "prompt_text": "trump",
                    "threshold": 80,
                    "enabled": True,
                }
            ],
            "providers": [
                {"provider_id": "opencode_cli", "enabled": True, "simulate_failure": True},
            ],
        },
    )
    record = data["message_scores"][0]
    assert record["action"] == "unclassified"
    assert data["degraded"] is True
