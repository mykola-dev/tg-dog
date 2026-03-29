import json
import os
import shutil
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
                "text": "news about trump today",
            },
            {
                "schema_version": "v1",
                "source_kind": "group",
                "source_id": "g1",
                "source_title": "Group",
                "message_id": "m2",
                "message_timestamp": "2026-03-21T10:05:00Z",
                "is_outbound": False,
                "is_from_self": False,
                "is_service_message": False,
                "media_items": [],
                "ingestion_meta": {},
                "text": "python release notes",
            },
        ]
    }
    (run_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")


def _run_heuristic(run_id: str, workspace: Path, sessions: Path, rules: dict) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.heuristic_filter.main",
            "--run-id",
            run_id,
            "--messages-ref",
            f"runs/{run_id}/messages.json",
            "--rules-json",
            json.dumps(rules),
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


def test_blacklist_match_removes_message_from_user_outputs() -> None:
    runtime = ROOT / ".pytest_runtime" / "heuristic_blacklist"
    shutil.rmtree(runtime, ignore_errors=True)
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_id = "heuristic-blacklist"
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _write_messages(run_dir)

    data = _run_heuristic(
        run_id,
        workspace,
        sessions,
        {
            "rules": [
                {
                    "rule_id": "b1",
                    "name": "No Trump",
                    "kind": "blacklist",
                    "terms": ["trump"],
                    "language_scope": "en",
                    "enabled": True,
                }
            ]
        },
    )

    decisions = {d["message_id"]: d for d in data["message_decisions"]}
    assert decisions["m1"]["action"] == "drop_blacklist"


def test_whitelist_match_routes_message_to_target_bucket() -> None:
    runtime = ROOT / ".pytest_runtime" / "heuristic_whitelist"
    shutil.rmtree(runtime, ignore_errors=True)
    workspace = runtime / "run_artifacts"
    sessions = runtime / "telegram_sessions"
    run_id = "heuristic-whitelist"
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sessions.mkdir(parents=True, exist_ok=True)
    _write_messages(run_dir)

    data = _run_heuristic(
        run_id,
        workspace,
        sessions,
        {
            "rules": [
                {
                    "rule_id": "w1",
                    "name": "Python alerts",
                    "kind": "whitelist",
                    "terms": ["python"],
                    "language_scope": "en",
                    "enabled": True,
                    "target_ref": "target-python",
                }
            ]
        },
    )

    buckets = data["matched_whitelist_groups"]
    assert "target-python" in buckets
    assert buckets["target-python"][0]["message_id"] == "m2"
