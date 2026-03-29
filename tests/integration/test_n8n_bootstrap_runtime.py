from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from http.cookies import SimpleCookie
import json
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
OWNER_EMAIL = "admin@example.com"
CHANGED_PASSWORD = "ChangedPassword123"
USER_WORKFLOW_NAME = "user-persisted-workflow"
INTERNAL_N8N_URL = "http://n8n:5678"


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


def _base_env() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    postgres_port = _unused_tcp_port()
    api_port = _unused_tcp_port()
    web_port = _unused_tcp_port()
    n8n_port = _unused_tcp_port()
    return {
        "POSTGRES_DB": "telegram_digest",
        "POSTGRES_USER": "telegram_digest",
        "POSTGRES_PASSWORD": "telegram_digest",
        "POSTGRES_PORT": str(postgres_port),
        "APP_MASTER_KEY": "test_master_key_1234567890",
        "APP_TIMEZONE": "UTC",
        "WORKSPACE_PATH": "/workspace/run_artifacts",
        "TELEGRAM_SESSION_PATH": "/workspace/telegram_sessions",
        "N8N_PASSWORD": "BootstrapPassword123",
        "N8N_PORT": str(n8n_port),
        "API_PORT": str(api_port),
        "WEB_PORT": str(web_port),
        "COMPOSE_PROJECT_NAME": f"n8n-bootstrap-{suffix}",
    }


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


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

        command = [
            "docker",
            "compose",
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            override.name,
            *args,
        ]

        merged_env = dict(os.environ)
        merged_env.update(env)
        return subprocess.run(
            command,
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
    path: str,
    payload: dict[str, object] | None = None,
    cookie_header: str | None = None,
) -> tuple[int, str, str | None]:
    payload_literal = repr(payload)
    cookie_literal = repr(cookie_header)
    script = f"""
import json
import urllib.error
import urllib.request

url = {INTERNAL_N8N_URL!r} + {path!r}
payload = {payload_literal}
cookie_header = {cookie_literal}
headers = {{}}
if payload is not None:
    headers['Content-Type'] = 'application/json'
if cookie_header:
    headers['Cookie'] = cookie_header
data = None if payload is None else json.dumps(payload).encode('utf-8')
request = urllib.request.Request(url, data=data, headers=headers, method={method!r})

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
        status, body, _ = _internal_request(env, "GET", "/healthz")
        if status == 200:
            return
        if status == 0:
            last_error = body
        else:
            last_error = f"unexpected health status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _wait_for_bootstrap_ready(env: dict[str, str], timeout_seconds: int = 120) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_error = "n8n bootstrap never completed"

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "GET", "/rest/settings")
        if status != 200:
            last_error = f"unexpected settings status {status}: {body}"
            time.sleep(2)
            continue

        try:
            payload = pytest.importorskip("json").loads(body)
        except ValueError as exc:
            last_error = str(exc)
            time.sleep(2)
            continue

        if isinstance(payload, dict):
            show_setup = payload.get("data", {}).get("userManagement", {}).get("showSetupOnFirstLoad")
            if show_setup is False:
                return payload
            last_error = f"showSetupOnFirstLoad still {show_setup!r}"
        else:
            last_error = f"unexpected settings payload type: {type(payload).__name__}"
        time.sleep(2)

    raise AssertionError(last_error)


def _login(env: dict[str, str], password: str) -> str:
    deadline = time.time() + 120
    last_error = "login endpoint never became ready"

    while time.time() < deadline:
        status, body, set_cookie = _internal_request(
            env,
            "POST",
            "/rest/login",
            payload={"emailOrLdapLoginId": OWNER_EMAIL, "password": password},
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
    payload = pytest.importorskip("json").loads(body)
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _json_body(body: str) -> list[dict[str, object]]:
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, list), payload
    return payload


def _workflows(env: dict[str, str], cookie_header: str) -> list[dict[str, object]]:
    status, body, _ = _internal_request(env, "GET", "/rest/workflows", cookie_header=cookie_header)
    assert status == 200, body
    return _json_body(body)


def _workflow_details(env: dict[str, str], cookie_header: str, workflow_id: str) -> dict[str, object]:
    status, body, _ = _internal_request(env, "GET", f"/rest/workflows/{workflow_id}", cookie_header=cookie_header)
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, dict), payload
    return payload


def _create_persisted_workflow(env: dict[str, str], cookie_header: str) -> dict[str, object]:
    status, body, _ = _internal_request(
        env,
        "POST",
        "/rest/workflows",
        payload={
            "name": USER_WORKFLOW_NAME,
            "active": False,
            "settings": {"executionOrder": "v1"},
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
                        "mode": "manual",
                        "includeOtherFields": False,
                        "assignments": {
                            "assignments": [
                                {
                                    "id": "persisted-value-assignment",
                                    "name": "status",
                                    "type": "string",
                                    "value": "persisted",
                                }
                            ]
                        },
                        "options": {},
                    },
                    "id": "set-node",
                    "name": "Set Persisted Value",
                    "type": "n8n-nodes-base.set",
                    "typeVersion": 3.4,
                    "position": [520, 300],
                },
            ],
            "connections": {
                "Manual Trigger": {
                    "main": [[{"node": "Set Persisted Value", "type": "main", "index": 0}]]
                },
                "Set Persisted Value": {"main": [[]]},
            },
        },
        cookie_header=cookie_header,
    )
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, dict), payload
    return payload


def test_n8n_bootstrap_runtime_reseeds_owner_and_preserves_user_workflow() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()

    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _wait_for_health(env)

        settings = _wait_for_bootstrap_ready(env)
        assert settings["data"]["userManagement"]["showSetupOnFirstLoad"] is False

        auth_cookie = _login(env, env["N8N_PASSWORD"])
        created_workflow = _create_persisted_workflow(env, auth_cookie)
        workflow_id = str(created_workflow["id"])
        workflow_before_restart = _workflow_details(env, auth_cookie, workflow_id)
        set_node_before_restart = next(
            node for node in workflow_before_restart["nodes"] if node["name"] == "Set Persisted Value"
        )
        assert workflow_before_restart["name"] == USER_WORKFLOW_NAME
        assert workflow_before_restart["settings"] == {"executionOrder": "v1"}
        assert set_node_before_restart["parameters"]["assignments"]["assignments"][0]["value"] == "persisted"

        password_status, password_body, _ = _internal_request(
            env,
            "PATCH",
            "/rest/me/password",
            payload={
                "currentPassword": env["N8N_PASSWORD"],
                "newPassword": CHANGED_PASSWORD,
            },
            cookie_header=auth_cookie,
        )
        assert password_status == 200, password_body

        restart = _compose_cmd(env, "restart", "n8n")
        assert restart.returncode == 0, restart.stderr or restart.stdout
        _wait_for_health(env)

        changed_cookie = _login(env, CHANGED_PASSWORD)
        workflows_after_restart = _workflows(env, changed_cookie)
        persisted_workflow = _workflow_details(env, changed_cookie, workflow_id)
        set_node_after_restart = next(
            node for node in persisted_workflow["nodes"] if node["name"] == "Set Persisted Value"
        )
        assert persisted_workflow["name"] == USER_WORKFLOW_NAME
        assert persisted_workflow["settings"] == {"executionOrder": "v1"}
        assert set_node_after_restart["parameters"]["assignments"]["assignments"][0]["value"] == "persisted"
        assert any(
            str(workflow.get("id")) == workflow_id and workflow.get("name") == USER_WORKFLOW_NAME
            for workflow in workflows_after_restart
        ), workflows_after_restart
        assert not any(workflow.get("name") == "starter-workflow" for workflow in workflows_after_restart), workflows_after_restart

        listed = _compose_cmd(env, "exec", "-T", "n8n", "n8n", "list:workflow")
        assert listed.returncode == 0, listed.stderr or listed.stdout
        workflow_rows = [line for line in listed.stdout.splitlines() if line.strip()]
        assert any(line.split("|", 1)[-1] == USER_WORKFLOW_NAME for line in workflow_rows), listed.stdout
        assert not any(line.split("|", 1)[-1] == "starter-workflow" for line in workflow_rows), listed.stdout
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")
