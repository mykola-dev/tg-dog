from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "BootstrapPassword123"
USER_WORKFLOW_NAME = "bridge-probe-user-workflow"
INTERNAL_N8N_URL = "http://n8n:5678"
INTERNAL_API_URL = "http://api:8000"


def _docker_available() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "docker executable is not available"

    result = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False, result.stderr or result.stdout or "docker compose version failed"

    return True, result.stdout.strip()


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _base_env() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "POSTGRES_DB": "telegram_digest",
        "POSTGRES_USER": "telegram_digest",
        "POSTGRES_PASSWORD": "telegram_digest",
        "POSTGRES_PORT": str(_unused_tcp_port()),
        "APP_MASTER_KEY": "test_master_key_1234567890",
        "APP_TIMEZONE": "UTC",
        "WORKSPACE_PATH": "/workspace/run_artifacts",
        "TELEGRAM_SESSION_PATH": "/workspace/telegram_sessions",
        "N8N_PORT": str(_unused_tcp_port()),
        "N8N_RUNNERS_BROKER_PORT": str(_unused_tcp_port()),
        "API_PORT": str(_unused_tcp_port()),
        "WEB_PORT": str(_unused_tcp_port()),
        "COMPOSE_PROJECT_NAME": f"n8n-user-workflow-e2e-{suffix}",
    }


def _compose_cmd(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    override = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yml", delete=False)
    try:
        override.write(
            "services:\n"
            "  postgres:\n"
            "    ports: !reset []\n"
            "  api:\n"
            "    ports: !reset []\n"
            "  n8n:\n"
            "    ports: !reset []\n"
            "  web:\n"
            "    ports: !reset []\n"
        )
        override.close()

        merged_env = dict(os.environ)
        merged_env.update(env)
        return subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(ROOT / "docker-compose.yml"),
                "-f",
                override.name,
                *args,
            ],
            cwd=ROOT,
            env=merged_env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(override.name).unlink(missing_ok=True)


def _compose_up(env: dict[str, str], *services: str) -> subprocess.CompletedProcess[str]:
    last_result: subprocess.CompletedProcess[str] | None = None

    for _ in range(3):
        result = _compose_cmd(env, "up", "-d", "--build", *services)
        if result.returncode == 0:
            return result

        last_result = result
        output = f"{result.stderr}\n{result.stdout}"
        if "/forwards/expose returned unexpected status: 500" not in output:
            return result

        _compose_cmd(env, "down", "-v", "--remove-orphans")
        time.sleep(2)

    assert last_result is not None
    return last_result


def _internal_request(
    env: dict[str, str],
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    cookie_header: str | None = None,
) -> tuple[int, str, str | None]:
    payload_literal = repr(payload)
    cookie_literal = repr(cookie_header)
    script = f"""
import json
import urllib.error
import urllib.request

payload = {payload_literal}
cookie_header = {cookie_literal}
headers = {{}}
if payload is not None:
    headers['Content-Type'] = 'application/json'
if cookie_header:
    headers['Cookie'] = cookie_header
data = None if payload is None else json.dumps(payload).encode('utf-8')
request = urllib.request.Request({url!r}, data=data, headers=headers, method={method!r})

try:
    with urllib.request.urlopen(request, timeout=20) as response:
        print(json.dumps({{
            'status': response.status,
            'body': response.read().decode('utf-8'),
            'set_cookie': response.headers.get('Set-Cookie'),
        }}))
except urllib.error.HTTPError as exc:
    print(json.dumps({{
        'status': exc.code,
        'body': exc.read().decode('utf-8'),
        'set_cookie': exc.headers.get('Set-Cookie'),
    }}))
"""
    result = _compose_cmd(env, "exec", "-T", "api", "python", "-c", script)
    if result.returncode != 0:
        stderr = result.stderr or result.stdout
        if "ConnectionRefusedError" in stderr or "URLError" in stderr:
            return 0, stderr, None
        assert result.returncode == 0, stderr
    response = json.loads(result.stdout)
    return int(response["status"]), str(response["body"]), response.get("set_cookie")


def _wait_for_health(env: dict[str, str], timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "n8n health endpoint never responded"

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "GET", f"{INTERNAL_N8N_URL}/healthz")
        if status == 200:
            return
        last_error = body if status == 0 else f"unexpected health status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _wait_for_bridge_probe(env: dict[str, str], timeout_seconds: int = 120) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_error = "bridge probe never responded"

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "GET", f"{INTERNAL_API_URL}/n8n/bridge-probe")
        if status == 200:
            payload = json.loads(body)
            assert payload["ok"] is True
            assert payload["bridge"] == "n8n"
            assert payload["service"] == "tg-dog-api"
            return payload
        last_error = body if status == 0 else f"unexpected bridge status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _wait_for_bootstrap_ready(env: dict[str, str], timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "n8n bootstrap never completed"

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "GET", f"{INTERNAL_N8N_URL}/rest/settings")
        if status == 200:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                last_error = body
                time.sleep(2)
                continue
            show_setup = payload.get("data", {}).get("userManagement", {}).get("showSetupOnFirstLoad")
            if show_setup is False:
                return
            last_error = f"showSetupOnFirstLoad still {show_setup!r}"
        else:
            last_error = body if status == 0 else f"unexpected settings status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _ensure_owner_ready(env: dict[str, str], timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "n8n owner setup never completed"
    setup_requested = False

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "GET", f"{INTERNAL_N8N_URL}/rest/settings")
        if status != 200:
            last_error = body if status == 0 else f"unexpected settings status {status}: {body}"
            time.sleep(2)
            continue

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            time.sleep(2)
            continue

        show_setup = payload.get("data", {}).get("userManagement", {}).get("showSetupOnFirstLoad")
        if show_setup is False:
            return

        if show_setup is True and not setup_requested:
            setup_status, setup_body, _ = _internal_request(
                env,
                "POST",
                f"{INTERNAL_N8N_URL}/rest/owner/setup",
                payload={
                    "email": OWNER_EMAIL,
                    "firstName": "Test",
                    "lastName": "Owner",
                    "password": OWNER_PASSWORD,
                },
            )
            if setup_status in {200, 201}:
                setup_requested = True
                time.sleep(2)
                continue
            last_error = f"owner setup failed with {setup_status}: {setup_body}"
            time.sleep(2)
            continue

        last_error = f"showSetupOnFirstLoad still {show_setup!r}"
        time.sleep(2)

    raise AssertionError(last_error)


def _login(env: dict[str, str]) -> str:
    _ensure_owner_ready(env)
    deadline = time.time() + 120
    last_error = "login endpoint never became ready"

    while time.time() < deadline:
        status, body, set_cookie = _internal_request(
            env,
            "POST",
            f"{INTERNAL_N8N_URL}/rest/login",
            payload={"emailOrLdapLoginId": OWNER_EMAIL, "password": OWNER_PASSWORD},
        )
        if status == 200:
            assert set_cookie, body
            cookie = SimpleCookie()
            cookie.load(set_cookie)
            assert "n8n-auth" in cookie, set_cookie
            return f"n8n-auth={cookie['n8n-auth'].value}"
        last_error = f"{status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _unwrap_n8n_payload(body: str) -> object:
    payload = json.loads(body)
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _create_workflow(env: dict[str, str], cookie_header: str) -> dict[str, object]:
    status, body, _ = _internal_request(
        env,
        "POST",
        f"{INTERNAL_N8N_URL}/rest/workflows",
        payload={
            "name": USER_WORKFLOW_NAME,
            "active": False,
            "settings": {},
            "nodes": [
                {
                    "parameters": {},
                    "id": "manual-trigger-node",
                    "name": "Manual Trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "typeVersion": 1,
                    "position": [260, 300],
                },
                {
                    "parameters": {
                        "method": "GET",
                        "url": "http://api:8000/n8n/bridge-probe",
                        "options": {},
                    },
                    "id": "bridge-probe-node",
                    "name": "Bridge Probe",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [480, 300],
                },
                {
                    "parameters": {
                        "mode": "manual",
                        "includeOtherFields": False,
                        "assignments": {
                            "assignments": [
                                {
                                    "id": "bridge-status-assignment",
                                    "name": "bridge_status",
                                    "type": "string",
                                    "value": "={{ $json.ok ? 'ok' : 'failed' }}",
                                },
                                {
                                    "id": "service-assignment",
                                    "name": "service",
                                    "type": "string",
                                    "value": "={{ $json.service }}",
                                },
                            ]
                        },
                        "options": {},
                    },
                    "id": "format-output-node",
                    "name": "Format Output",
                    "type": "n8n-nodes-base.set",
                    "typeVersion": 3.4,
                    "position": [700, 300],
                },
            ],
            "connections": {
                "Manual Trigger": {
                    "main": [[{"node": "Bridge Probe", "type": "main", "index": 0}]]
                },
                "Bridge Probe": {
                    "main": [[{"node": "Format Output", "type": "main", "index": 0}]]
                },
                "Format Output": {"main": [[]]},
            },
        },
        cookie_header=cookie_header,
    )
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, dict), payload
    return payload


def _run_workflow(env: dict[str, str], workflow_id: str) -> dict[str, object]:
    result = _compose_cmd(
        env,
        "exec",
        "-e",
        f"N8N_RUNNERS_BROKER_PORT={env['N8N_RUNNERS_BROKER_PORT']}",
        "-T",
        "n8n",
        "n8n",
        "execute",
        f"--id={workflow_id}",
        "--rawOutput",
    )
    assert result.returncode == 0, result.stderr or result.stdout
    json_start = result.stdout.find("{")
    assert json_start >= 0, result.stdout
    payload, _ = json.JSONDecoder().raw_decode(result.stdout[json_start:])
    return payload


def test_user_created_n8n_workflow_runs_end_to_end() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _wait_for_health(env)
        bridge_probe = _wait_for_bridge_probe(env)
        _wait_for_bootstrap_ready(env)

        auth_cookie = _login(env)
        workflow = _create_workflow(env, auth_cookie)
        execution = _run_workflow(env, str(workflow["id"]))

        assert execution["finished"] is True
        assert execution["status"] == "success"
        run_data = execution["data"]["resultData"]["runData"]
        bridge_payload = run_data["Bridge Probe"][0]["data"]["main"][0][0]["json"]
        formatted_payload = run_data["Format Output"][0]["data"]["main"][0][0]["json"]

        assert bridge_payload["ok"] is True
        assert bridge_payload["bridge"] == bridge_probe["bridge"]
        assert bridge_payload["service"] == bridge_probe["service"]
        assert isinstance(bridge_payload["timestamp"], str)
        assert datetime.fromisoformat(bridge_payload["timestamp"])
        assert formatted_payload == {
            "bridge_status": "ok",
            "service": bridge_probe["service"],
        }
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")
