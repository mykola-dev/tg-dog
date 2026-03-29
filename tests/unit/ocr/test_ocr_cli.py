import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _base_env(workspace: Path, sessions: Path) -> dict[str, str]:
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


def test_ocr_adds_extracted_text_for_image_messages() -> None:
    runtime = ROOT / ".pytest_runtime" / "ocr_cli_success"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_dir = workspace / "runs" / "ocr-run"
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
                "media_items": [
                    {
                        "media_kind": "image",
                        "file_ref": "runs/ocr-run/media-1.png",
                        "ocr_status": "pending",
                    }
                ],
                "ingestion_meta": {},
                "text": "",
            }
        ]
    }
    (run_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.ocr.main",
            "--run-id",
            "ocr-run",
            "--messages-ref",
            "runs/ocr-run/messages.json",
        ],
        cwd=ROOT,
        env=_base_env(workspace, sessions),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "ok"
    ocr_ref = envelope["payload_ref"]
    ocr_json = json.loads((workspace / ocr_ref).read_text(encoding="utf-8"))
    assert ocr_json["provider_kind"] == "local:tesseract"
    assert ocr_json["message_ocr_results"][0]["extracted_text"]


def test_ocr_failure_marks_message_as_failed_without_stopping_pipeline() -> None:
    runtime = ROOT / ".pytest_runtime" / "ocr_cli_failure"
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_dir = workspace / "runs" / "ocr-run-fail"
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
                "media_items": [
                    {
                        "media_kind": "image",
                        "file_ref": "runs/ocr-run-fail/missing.png",
                        "ocr_status": "pending",
                    }
                ],
                "ingestion_meta": {"simulate_ocr_failure": True},
                "text": "",
            }
        ]
    }
    (run_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.ocr.main",
            "--run-id",
            "ocr-run-fail",
            "--messages-ref",
            "runs/ocr-run-fail/messages.json",
        ],
        cwd=ROOT,
        env=_base_env(workspace, sessions),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    ocr_ref = envelope["payload_ref"]
    ocr_json = json.loads((workspace / ocr_ref).read_text(encoding="utf-8"))
    assert ocr_json["message_ocr_results"][0]["ocr_status"] == "failed"
    assert len(ocr_json["failed_items"]) == 1
