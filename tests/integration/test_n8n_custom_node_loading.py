from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from functools import cmp_to_key
from http.cookies import SimpleCookie
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
INTERNAL_N8N_URL = "http://n8n:5678"
INTERNAL_API_URL = "http://api:8000"
OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "BootstrapPassword123"
CUSTOM_NODE_TYPE = "telegramSourceSelector"
CUSTOM_NODE_FULL_TYPE = f"CUSTOM.{CUSTOM_NODE_TYPE}"
CUSTOM_NODE_FOLDER = "telegram-source-selector"
MESSAGE_READER_NODE_TYPE = "telegramMessageReader"
MESSAGE_READER_NODE_FULL_TYPE = f"CUSTOM.{MESSAGE_READER_NODE_TYPE}"
MESSAGE_READER_NODE_FOLDER = "telegram-message-reader"
OCR_NODE_TYPE = "telegramOCR"
OCR_NODE_FULL_TYPE = f"CUSTOM.{OCR_NODE_TYPE}"
OCR_NODE_FOLDER = "telegram-ocr"
CLEANUP_NODE_TYPE = "messagesCleanup"
CLEANUP_NODE_FULL_TYPE = f"CUSTOM.{CLEANUP_NODE_TYPE}"
CLEANUP_NODE_FOLDER = "messages-cleanup"
DIGEST_NODE_TYPE = "telegramDigest"
DIGEST_NODE_FULL_TYPE = f"CUSTOM.{DIGEST_NODE_TYPE}"
DIGEST_NODE_FOLDER = "telegram-digest"
POST_NODE_TYPE = "postMessage"
POST_NODE_FULL_TYPE = f"CUSTOM.{POST_NODE_TYPE}"
POST_NODE_FOLDER = "post-message"
TRIGGER_NODE_TYPE = "telegramMessageTrigger"
TRIGGER_NODE_FULL_TYPE = f"CUSTOM.{TRIGGER_NODE_TYPE}"
TRIGGER_NODE_FOLDER = "telegram-message-trigger"
RANDOM_NODE_TYPE = "telegramRandomMessage"
RANDOM_NODE_FULL_TYPE = f"CUSTOM.{RANDOM_NODE_TYPE}"
RANDOM_NODE_FOLDER = "telegram-random-message"
BOT_COMMAND_TRIGGER_NODE_TYPE = "telegramBotCommandTrigger"
BOT_COMMAND_TRIGGER_NODE_FULL_TYPE = f"CUSTOM.{BOT_COMMAND_TRIGGER_NODE_TYPE}"
BOT_COMMAND_TRIGGER_NODE_FOLDER = "telegram-bot-command-trigger"
CUSTOM_EXTENSIONS_DIR = "/custom-extensions"
REAL_TELEGRAM_SESSION_SOURCE_VOLUME = os.getenv(
    "REAL_TELEGRAM_SESSION_SOURCE_VOLUME",
    "tg-dog_telegram_sessions",
)
SUPPORTED_DIALOG_KINDS = {"channel", "group", "contact"}


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
        "API_PORT": str(_unused_tcp_port()),
        "COMPOSE_PROJECT_NAME": f"n8n-custom-node-{suffix}",
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
    return _compose_cmd(env, "up", "-d", "--build", *services)


def _service_request(
    env: dict[str, str],
    service: str,
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    cookie_header: str | None = None,
) -> tuple[int, str, str | None]:
    payload_literal = repr(payload)
    cookie_literal = repr(cookie_header)
    script = f"""
import json
import urllib.error
import urllib.request

url = {base_url!r} + {path!r}
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
    result = _compose_cmd(env, "exec", "-T", service, "python", "-c", script)
    if result.returncode != 0:
        stderr = result.stderr or result.stdout
        if (
            result.returncode in {137, 143}
            or "ConnectionRefusedError" in stderr
            or "URLError" in stderr
            or "is restarting, wait until the container is running" in stderr
            or not stderr.strip()
        ):
            return 0, stderr, None
        assert result.returncode == 0, stderr
    response = json.loads(result.stdout)
    return int(response["status"]), str(response["body"]), response.get("set_cookie")


def _internal_request(env: dict[str, str], path: str, *, method: str = "GET", payload: dict[str, object] | None = None, cookie_header: str | None = None) -> tuple[int, str, str | None]:
    return _service_request(
        env,
        "api",
        INTERNAL_N8N_URL,
        path,
        method=method,
        payload=payload,
        cookie_header=cookie_header,
    )


def _api_request(env: dict[str, str], path: str, *, method: str = "GET", payload: dict[str, object] | None = None) -> tuple[int, str]:
    status, body, _ = _service_request(env, "api", INTERNAL_API_URL, path, method=method, payload=payload)
    return status, body


def _wait_for_health(env: dict[str, str], timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "n8n health endpoint never responded"

    while time.time() < deadline:
        probe = _compose_cmd(
            env,
            "exec",
            "-T",
            "n8n",
            "node",
            "-e",
            (
                "fetch('http://127.0.0.1:5678/healthz')"
                ".then(async (response) => {"
                "const body = await response.text();"
                "console.log(JSON.stringify({status: response.status, body}));"
                "})"
                ".catch((error) => {"
                "console.error(error instanceof Error ? error.stack || error.message : String(error));"
                "process.exit(1);"
                "});"
            ),
        )
        if probe.returncode == 0:
            payload = json.loads(probe.stdout)
            status = int(payload["status"])
            body = str(payload["body"])
        else:
            status = 0
            body = probe.stderr or probe.stdout or "n8n health probe failed"

        if status == 200:
            return
        last_error = body if status == 0 else f"unexpected health status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _ensure_owner_ready(env: dict[str, str], timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "n8n owner setup never completed"
    setup_requested = False

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "/rest/settings")
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
                "/rest/owner/setup",
                method="POST",
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


def _login(env: dict[str, str], timeout_seconds: int = 120) -> str:
    _ensure_owner_ready(env, timeout_seconds=timeout_seconds)
    deadline = time.time() + timeout_seconds
    last_error = "n8n login never became ready"

    while time.time() < deadline:
        status, body, set_cookie = _internal_request(
            env,
            "/rest/login",
            method="POST",
            payload={"emailOrLdapLoginId": OWNER_EMAIL, "password": OWNER_PASSWORD},
        )
        if status == 200:
            if body == "n8n is starting up. Please wait":
                last_error = body
                time.sleep(2)
                continue
            assert set_cookie, body
            cookie = SimpleCookie()
            cookie.load(set_cookie)
            assert "n8n-auth" in cookie, set_cookie
            return f"n8n-auth={cookie['n8n-auth'].value}"
        last_error = f"{status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _wait_for_node_types(env: dict[str, str], cookie_header: str, timeout_seconds: int = 120) -> str:
    deadline = time.time() + timeout_seconds
    last_error = "n8n node types endpoint never became ready"

    while time.time() < deadline:
        status, body, _ = _internal_request(env, "/types/nodes.json", cookie_header=cookie_header)
        if status == 200 and "n8n is starting up. Please wait" not in body:
            return body
        last_error = body if status == 200 else f"unexpected node types status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _docker_volume_exists(volume_name: str) -> bool:
    result = subprocess.run(
        ["docker", "volume", "inspect", volume_name],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _seed_real_telegram_session_volume(env: dict[str, str]) -> None:
    source_volume = REAL_TELEGRAM_SESSION_SOURCE_VOLUME
    if not _docker_volume_exists(source_volume):
        pytest.skip(f"Real Telegram session source volume is unavailable: {source_volume}")

    target_volume = f"{env['COMPOSE_PROJECT_NAME']}_telegram_sessions"
    copy = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{source_volume}:/from:ro",
            "-v",
            f"{target_volume}:/to",
            "alpine",
            "sh",
            "-lc",
            "cp -a /from/. /to/",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert copy.returncode == 0, copy.stderr or copy.stdout


def _wait_for_dialogs(env: dict[str, str], timeout_seconds: int = 120) -> list[dict[str, object]]:
    deadline = time.time() + timeout_seconds
    last_error = "dialogs endpoint never became ready"

    while time.time() < deadline:
        status, body = _api_request(env, "/dialogs")
        if status == 200:
            payload = json.loads(body)
            assert isinstance(payload, list), payload
            return payload
        last_error = body if status == 0 else f"unexpected dialogs status {status}: {body}"
        time.sleep(2)

    raise AssertionError(last_error)


def _sort_dialogs(dialogs: list[dict[str, object]]) -> list[dict[str, object]]:
    def compare(left: dict[str, object], right: dict[str, object]) -> int:
        left_date = str(left.get("last_message_date") or "")
        right_date = str(right.get("last_message_date") or "")
        if left_date != right_date:
            if left_date > right_date:
                return -1
            return 1

        left_name = str(left.get("name") or "")
        right_name = str(right.get("name") or "")
        if left_name < right_name:
            return -1
        if left_name > right_name:
            return 1
        return 0

    return sorted(dialogs, key=cmp_to_key(compare))


def _filtered_supported_dialogs(dialogs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [dialog for dialog in dialogs if dialog.get("kind") in SUPPORTED_DIALOG_KINDS]


def _dynamic_option_name(dialog: dict[str, object]) -> str:
    last_message_date = dialog.get("last_message_date") or "no recent message"
    return f"{dialog['name']} ({dialog['kind']}) - {last_message_date}"


def _unwrap_n8n_payload(body: str) -> object:
    payload = json.loads(body)
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _workflows(env: dict[str, str], cookie_header: str) -> list[dict[str, object]]:
    status, body, _ = _internal_request(env, "/rest/workflows", cookie_header=cookie_header)
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, list), payload
    return payload


def _wait_for_workflow(
    env: dict[str, str],
    cookie_header: str,
    workflow_name: str,
    timeout_seconds: int = 120,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_error = f"workflow {workflow_name!r} never appeared"

    while time.time() < deadline:
        workflows = _workflows(env, cookie_header)
        matches = [workflow for workflow in workflows if workflow.get("name") == workflow_name]
        if len(matches) == 1:
            return matches[0]
        last_error = f"workflow matches={len(matches)} payload={workflows}"
        time.sleep(2)

    raise AssertionError(last_error)


def _workflow_details(env: dict[str, str], cookie_header: str, workflow_id: str) -> dict[str, object]:
    status, body, _ = _internal_request(env, f"/rest/workflows/{workflow_id}", cookie_header=cookie_header)
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, dict), payload
    return payload


def _create_workflow(
    env: dict[str, str],
    cookie_header: str,
    *,
    name: str,
    nodes: list[dict[str, object]],
    connections: dict[str, object],
) -> dict[str, object]:
    status, body, _ = _internal_request(
        env,
        "/rest/workflows",
        method="POST",
        cookie_header=cookie_header,
        payload={
            "name": name,
            "active": False,
            "settings": {},
            "nodes": nodes,
            "connections": connections,
        },
    )
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, dict), payload
    return payload


def _dynamic_dialog_options(
    env: dict[str, str],
    cookie_header: str,
    include_kinds: list[str],
    selected_dialog_ids: list[str],
) -> list[dict[str, object]]:
    status, body, _ = _internal_request(
        env,
        "/rest/dynamic-node-parameters/options",
        method="POST",
        cookie_header=cookie_header,
        payload={
            "path": "parameters.selectedDialogIds",
            "nodeTypeAndVersion": {"name": CUSTOM_NODE_FULL_TYPE, "version": 1},
            "currentNodeParameters": {
                "includeKinds": include_kinds,
                "selectedDialogIds": selected_dialog_ids,
            },
            "methodName": "getSelectableDialogs",
        },
    )
    assert status == 200, body
    payload = _unwrap_n8n_payload(body)
    assert isinstance(payload, list), payload
    return payload


def _node_execute_result(env: dict[str, str], selected_dialog_ids: list[str]) -> list[dict[str, object]]:
    node_path = f"{CUSTOM_EXTENSIONS_DIR}/{CUSTOM_NODE_FOLDER}/TelegramSourceSelector.node.js"
    selected_dialog_ids_literal = repr(selected_dialog_ids)
    script = f"""
process.env.NODE_PATH = '/usr/local/lib/node_modules/n8n/node_modules';
require('module').Module._initPaths();
const {{ TelegramSourceSelector }} = require({node_path!r});

async function main() {{
  const node = new TelegramSourceSelector();
  const context = {{
    getInputData() {{
      return [{{ json: {{ existing: 'value' }} }}];
    }},
    getNodeParameter(name, itemIndex) {{
      if (itemIndex !== 0) throw new Error(`unexpected itemIndex ${{itemIndex}}`);
      if (name === 'selectedDialogIds') return {selected_dialog_ids_literal};
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};

  const result = await node.execute.call(context);
  process.stdout.write(JSON.stringify(result));
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = _compose_cmd(env, "exec", "-T", "n8n", "node", "-e", script)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list), payload
    return payload


def _message_reader_execute_result(env: dict[str, str], selected_dialog_ids: list[str], lookback_hours: int) -> list[dict[str, object]]:
    node_path = f"{CUSTOM_EXTENSIONS_DIR}/{MESSAGE_READER_NODE_FOLDER}/TelegramMessageReader.node.js"
    selected_dialog_ids_literal = repr(selected_dialog_ids)
    script = f"""
process.env.NODE_PATH = '/usr/local/lib/node_modules/n8n/node_modules';
require('module').Module._initPaths();
const {{ TelegramMessageReader }} = require({node_path!r});

async function main() {{
  const node = new TelegramMessageReader();
  const context = {{
    getInputData() {{
      return [{{ json: {{ selected_dialog_ids: {selected_dialog_ids_literal} }} }}];
    }},
    getNodeParameter(name, itemIndex) {{
      if (itemIndex !== 0) throw new Error(`unexpected itemIndex ${{itemIndex}}`);
      if (name === 'lookbackHours') return {lookback_hours};
      if (name === 'includeMedia') return true;
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};

  const result = await node.execute.call(context);
  process.stdout.write(JSON.stringify(result));
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = _compose_cmd(env, "exec", "-T", "n8n", "node", "-e", script)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list), payload
    return payload


def _random_message_execute_result(
    env: dict[str, str],
    dialog_id: str,
    *,
    skip_empty_text: bool = True,
    ignore_self: bool = False,
    ignore_service_messages: bool = True,
) -> list[dict[str, object]]:
    node_path = f"{CUSTOM_EXTENSIONS_DIR}/{RANDOM_NODE_FOLDER}/TelegramRandomMessage.node.js"
    script = f"""
process.env.NODE_PATH = '/usr/local/lib/node_modules/n8n/node_modules';
require('module').Module._initPaths();
const {{ TelegramRandomMessage }} = require({node_path!r});

const originalRandom = Math.random;
Math.random = () => 0;

async function main() {{
  const node = new TelegramRandomMessage();
  const context = {{
    getInputData() {{
      return [{{ json: {{ existing: 'value' }} }}];
    }},
    getNodeParameter(name, itemIndex) {{
      if (itemIndex !== 0) throw new Error(`unexpected itemIndex ${{itemIndex}}`);
      if (name === 'dialogId') return {dialog_id!r};
      if (name === 'skipEmptyText') return {str(skip_empty_text).lower()};
      if (name === 'ignoreSelf') return {str(ignore_self).lower()};
      if (name === 'ignoreServiceMessages') return {str(ignore_service_messages).lower()};
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};

  try {{
    const result = await node.execute.call(context);
    process.stdout.write(JSON.stringify(result));
  }} finally {{
    Math.random = originalRandom;
  }}
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = _compose_cmd(env, "exec", "-T", "n8n", "node", "-e", script)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list), payload
    return payload


def _ocr_execute_result(env: dict[str, str], input_messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node_path = f"{CUSTOM_EXTENSIONS_DIR}/{OCR_NODE_FOLDER}/TelegramOCR.node.js"
    input_messages_literal = json.dumps(input_messages)
    script = f"""
process.env.NODE_PATH = '/usr/local/lib/node_modules/n8n/node_modules';
require('module').Module._initPaths();
const {{ TelegramOCR }} = require({node_path!r});

async function main() {{
  const node = new TelegramOCR();
  const context = {{
    getInputData() {{
      return {input_messages_literal}.map((entry) => ({{ json: entry }}));
    }},
    getNodeParameter(name, itemIndex) {{
      if (name === 'providerMode') return 'local';
      throw new Error(`unexpected node parameter ${{name}} @ ${{itemIndex}}`);
    }},
  }};

  const result = await node.execute.call(context);
  process.stdout.write(JSON.stringify(result));
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = _compose_cmd(env, "exec", "-T", "n8n", "node", "-e", script)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list), payload
    return payload


def _cleanup_execute_result(env: dict[str, str], input_messages: list[dict[str, object]], *, mode: str = "combined") -> list[dict[str, object]]:
    node_path = f"{CUSTOM_EXTENSIONS_DIR}/{CLEANUP_NODE_FOLDER}/MessagesCleanup.node.js"
    input_messages_literal = json.dumps(input_messages)
    script = f"""
process.env.NODE_PATH = '/usr/local/lib/node_modules/n8n/node_modules';
require('module').Module._initPaths();
const {{ MessagesCleanup }} = require({node_path!r});

async function main() {{
  const node = new MessagesCleanup();
  const context = {{
    getInputData() {{
      return {input_messages_literal}.map((entry) => ({{ json: entry }}));
    }},
    getNodeParameter(name) {{
      if (name === 'mode') return {mode!r};
      if (name === 'outputFormat') return 'markdown';
      if (name === 'includeSourceTitle') return true;
      if (name === 'includeTimestamp') return true;
      if (name === 'includeOcrText') return true;
      if (name === 'maxCharactersPerMessage') return 1200;
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};
  const result = await node.execute.call(context);
  process.stdout.write(JSON.stringify(result));
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = _compose_cmd(env, "exec", "-T", "n8n", "node", "-e", script)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list), payload
    return payload


def _digest_execute_result(
    env: dict[str, str],
    input_messages: list[dict[str, object]],
    *,
    include_title: bool = True,
    title_template: str = '={{ "📰 ДАЙДЖЕСТ НОВИН ЗА " + $now.setLocale("uk").toFormat("d MMMM") }}',
) -> list[dict[str, object]]:
    node_path = f"{CUSTOM_EXTENSIONS_DIR}/{DIGEST_NODE_FOLDER}/TelegramDigest.node.js"
    input_messages_literal = json.dumps(input_messages)
    include_title_literal = json.dumps(include_title)
    title_template_literal = json.dumps(title_template)
    script = f"""
process.env.NODE_PATH = '/usr/local/lib/node_modules/n8n/node_modules';
require('module').Module._initPaths();
const {{ TelegramDigest }} = require({node_path!r});

async function main() {{
  const node = new TelegramDigest();
  const context = {{
    getInputData() {{
      return {input_messages_literal}.map((entry) => ({{ json: entry }}));
    }},
    getNodeParameter(name) {{
      if (name === 'commandTemplate') return 'opencode run -m opencode/minimax-m2.5-free "{{prompt}}"';
      if (name === 'systemPrompt') return 'Create a compact Telegram digest from the provided messages.';
      if (name === 'outputFormat') return 'markdown_v2';
      if (name === 'includeTitle') return {include_title_literal};
      if (name === 'titleTemplate') return {title_template_literal};
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};
  const result = await node.execute.call(context);
  process.stdout.write(JSON.stringify(result));
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = _compose_cmd(env, "exec", "-T", "n8n", "node", "-e", script)
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list), payload
    return payload


def test_n8n_loads_local_custom_node_package() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()

    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _wait_for_health(env)

        env_result = _compose_cmd(env, "exec", "-T", "n8n", "env")
        assert env_result.returncode == 0, env_result.stderr or env_result.stdout
        assert f"N8N_CUSTOM_EXTENSIONS={CUSTOM_EXTENSIONS_DIR}" in env_result.stdout

        package_listing = _compose_cmd(env, "exec", "-T", "n8n", "ls", "-R", CUSTOM_EXTENSIONS_DIR)
        assert package_listing.returncode == 0, package_listing.stderr or package_listing.stdout
        assert CUSTOM_NODE_FOLDER in package_listing.stdout
        assert MESSAGE_READER_NODE_FOLDER in package_listing.stdout
        assert OCR_NODE_FOLDER in package_listing.stdout
        assert CLEANUP_NODE_FOLDER in package_listing.stdout
        assert DIGEST_NODE_FOLDER in package_listing.stdout
        assert POST_NODE_FOLDER in package_listing.stdout
        assert TRIGGER_NODE_FOLDER in package_listing.stdout
        assert RANDOM_NODE_FOLDER in package_listing.stdout
        assert BOT_COMMAND_TRIGGER_NODE_FOLDER in package_listing.stdout

        auth_cookie = _login(env)
        body = _wait_for_node_types(env, auth_cookie)
        assert CUSTOM_NODE_FULL_TYPE in body, body
        assert "TG Dog Source Selector" in body, body
        assert MESSAGE_READER_NODE_FULL_TYPE in body, body
        assert "TG Dog Message Reader" in body, body
        assert OCR_NODE_FULL_TYPE in body, body
        assert "TG Dog OCR" in body, body
        assert CLEANUP_NODE_FULL_TYPE in body, body
        assert "TG Dog Messages Cleanup" in body, body
        assert DIGEST_NODE_FULL_TYPE in body, body
        assert "TG Dog Digest" in body, body
        assert POST_NODE_FULL_TYPE in body, body
        assert "TG Dog Post Message" in body, body
        assert '"name":"senderMode"' in body, body
        assert TRIGGER_NODE_FULL_TYPE in body, body
        assert "TG Dog Message Trigger" in body, body
        assert RANDOM_NODE_FULL_TYPE in body, body
        assert "TG Dog Random Message" in body, body
        assert BOT_COMMAND_TRIGGER_NODE_FULL_TYPE in body, body
        assert "TG Dog Bot Command Trigger" in body, body
        assert "webhookMethods" in Path(ROOT / "n8n/custom-nodes/telegram-message-trigger/TelegramMessageTrigger.node.js").read_text(encoding="utf-8")
        assert "webhookMethods" in Path(ROOT / "n8n/custom-nodes/telegram-bot-command-trigger/TelegramBotCommandTrigger.node.js").read_text(encoding="utf-8")
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_random_message_node_returns_one_real_message() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _seed_real_telegram_session_volume(env)
        _wait_for_health(env)

        dialogs = _sort_dialogs(_filtered_supported_dialogs(_wait_for_dialogs(env)))
        assert dialogs, dialogs

        chosen_dialog = None
        for dialog in dialogs:
            status, body = _api_request(
                env,
                "/messages/random",
                method="POST",
                payload={
                    "dialog_id": str(dialog["id"]),
                    "skip_empty_text": True,
                    "ignore_self": False,
                    "ignore_service_messages": True,
                },
            )
            if status == 200:
                chosen_dialog = dialog
                break

        assert chosen_dialog is not None, "No dialog with non-empty recent messages found for random-message test"

        result = _random_message_execute_result(
            env,
            str(chosen_dialog["id"]),
            skip_empty_text=True,
            ignore_self=False,
            ignore_service_messages=True,
        )

        assert len(result) == 1, result
        output_items = result[0]
        assert len(output_items) == 1, output_items
        output_json = output_items[0]["json"]
        assert output_json["source_id"] == str(chosen_dialog["id"])
        assert str(output_json.get("text") or "").strip(), output_json
        assert output_json["message_id"], output_json
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_custom_node_exposes_dynamic_dialog_multi_select() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _seed_real_telegram_session_volume(env)
        _wait_for_health(env)

        auth_cookie = _login(env)
        node_types_body = _wait_for_node_types(env, auth_cookie)
        assert '"name":"selectedDialogIds"' in node_types_body, node_types_body
        assert '"type":"multiOptions"' in node_types_body, node_types_body
        assert "getSelectableDialogs" in node_types_body, node_types_body

        dialogs = _filtered_supported_dialogs(_wait_for_dialogs(env))
        assert dialogs, dialogs

        include_kinds = sorted({str(dialog["kind"]) for dialog in dialogs[:2]})
        filtered_dialogs = [dialog for dialog in _sort_dialogs(dialogs) if dialog["kind"] in include_kinds]
        assert filtered_dialogs, filtered_dialogs

        status, body, _ = _internal_request(
            env,
            "/rest/dynamic-node-parameters/options",
            method="POST",
            cookie_header=auth_cookie,
            payload={
                "path": "parameters.selectedDialogIds",
                "nodeTypeAndVersion": {"name": CUSTOM_NODE_FULL_TYPE, "version": 1},
                "currentNodeParameters": {
                    "includeKinds": include_kinds,
                    "selectedDialogIds": [],
                },
                "methodName": "getSelectableDialogs",
            },
        )
        assert status == 200, body

        payload = _unwrap_n8n_payload(body)
        assert isinstance(payload, list), payload

        expected = [
            {"name": _dynamic_option_name(dialog), "value": str(dialog["id"])}
            for dialog in filtered_dialogs
        ]
        assert payload == expected
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_custom_node_execution_returns_selected_dialog_metadata() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _seed_real_telegram_session_volume(env)
        _wait_for_health(env)

        auth_cookie = _login(env)
        dialogs = _sort_dialogs(_filtered_supported_dialogs(_wait_for_dialogs(env)))
        assert dialogs, dialogs

        selected_dialogs = dialogs[: min(2, len(dialogs))]
        selected_dialog_ids = [str(dialog["id"]) for dialog in selected_dialogs]
        include_kinds = sorted({str(dialog["kind"]) for dialog in selected_dialogs})

        created_workflow = _create_workflow(
            env,
            auth_cookie,
            name="telegram-source-selector-runtime",
            nodes=[
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
                        "includeKinds": include_kinds,
                        "selectedDialogIds": selected_dialog_ids,
                    },
                    "id": "telegram-source-selector-node",
                    "name": "TG Dog Source Selector",
                    "type": CUSTOM_NODE_FULL_TYPE,
                    "typeVersion": 1,
                    "position": [520, 300],
                },
            ],
            connections={
                "Manual Trigger": {
                    "main": [[{"node": "TG Dog Source Selector", "type": "main", "index": 0}]]
                },
                "TG Dog Source Selector": {"main": [[]]},
            },
        )
        workflow_id = str(created_workflow["id"])

        updated_workflow = _workflow_details(env, auth_cookie, workflow_id)
        selector_node = next(
            node for node in updated_workflow["nodes"] if node["type"] == CUSTOM_NODE_FULL_TYPE
        )
        assert selector_node["parameters"]["includeKinds"] == include_kinds
        assert selector_node["parameters"]["selectedDialogIds"] == selected_dialog_ids

        execution_output = _node_execute_result(env, selected_dialog_ids)
        assert len(execution_output) == 1, execution_output
        selector_output = execution_output[0][0]["json"]
        dialogs_by_id = {str(dialog["id"]): dialog for dialog in _sort_dialogs(_filtered_supported_dialogs(_wait_for_dialogs(env)))}
        expected_selected_dialogs = [dialogs_by_id[dialog_id] for dialog_id in selected_dialog_ids]
        assert selector_output["existing"] == "value"
        assert selector_output["selected_dialog_ids"] == selected_dialog_ids
        actual_selected_dialogs = selector_output["selected_dialogs"]
        assert len(actual_selected_dialogs) == len(expected_selected_dialogs)
        for actual_dialog, expected_dialog in zip(actual_selected_dialogs, expected_selected_dialogs, strict=True):
            assert actual_dialog["id"] == str(expected_dialog["id"])
            assert actual_dialog["name"] == expected_dialog["name"]
            assert actual_dialog["kind"] == expected_dialog["kind"]
            assert actual_dialog["username"] == expected_dialog["username"]
            assert actual_dialog["can_send"] == expected_dialog["can_send"]

        payload = _dynamic_dialog_options(env, auth_cookie, include_kinds, selected_dialog_ids)

        selected_entries = [entry for entry in payload if entry["value"] in selected_dialog_ids]
        assert [entry["value"] for entry in selected_entries] == selected_dialog_ids
        for entry, dialog in zip(selected_entries, expected_selected_dialogs, strict=True):
            assert entry["name"].startswith(f"{dialog['name']} ({dialog['kind']}) - "), entry
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_custom_node_selected_dialogs_persist_across_restart() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _seed_real_telegram_session_volume(env)
        _wait_for_health(env)

        auth_cookie = _login(env)
        dialogs = _sort_dialogs(_filtered_supported_dialogs(_wait_for_dialogs(env)))
        assert len(dialogs) >= 2, dialogs

        selected_dialogs = dialogs[:2]
        selected_dialog_ids = [str(dialog["id"]) for dialog in selected_dialogs]
        include_kinds = sorted({str(dialog["kind"]) for dialog in selected_dialogs})

        created_workflow = _create_workflow(
            env,
            auth_cookie,
            name="telegram-source-selector-persistence",
            nodes=[
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
                        "includeKinds": include_kinds,
                        "selectedDialogIds": selected_dialog_ids,
                    },
                    "id": "telegram-source-selector-node",
                    "name": "TG Dog Source Selector",
                    "type": CUSTOM_NODE_FULL_TYPE,
                    "typeVersion": 1,
                    "position": [520, 300],
                },
            ],
            connections={
                "Manual Trigger": {
                    "main": [[{"node": "TG Dog Source Selector", "type": "main", "index": 0}]]
                },
                "TG Dog Source Selector": {"main": [[]]},
            },
        )
        workflow_id = str(created_workflow["id"])

        updated_workflow = _workflow_details(env, auth_cookie, workflow_id)
        selector_node_before_restart = next(
            node for node in updated_workflow["nodes"] if node["type"] == CUSTOM_NODE_FULL_TYPE
        )
        assert selector_node_before_restart["parameters"]["includeKinds"] == include_kinds
        assert selector_node_before_restart["parameters"]["selectedDialogIds"] == selected_dialog_ids

        restart = _compose_cmd(env, "restart", "n8n")
        assert restart.returncode == 0, restart.stderr or restart.stdout
        _wait_for_health(env)

        auth_cookie_after_restart = _login(env)
        persisted_workflow = _workflow_details(env, auth_cookie_after_restart, workflow_id)
        selector_node_after_restart = next(
            node for node in persisted_workflow["nodes"] if node["type"] == CUSTOM_NODE_FULL_TYPE
        )
        assert selector_node_after_restart["parameters"]["includeKinds"] == include_kinds
        assert selector_node_after_restart["parameters"]["selectedDialogIds"] == selected_dialog_ids

        dialogs_after_restart = {
            str(dialog["id"]): dialog
            for dialog in _sort_dialogs(_filtered_supported_dialogs(_wait_for_dialogs(env)))
        }
        expected_selected_after_restart = [dialogs_after_restart[dialog_id] for dialog_id in selected_dialog_ids]

        options_after_restart = _dynamic_dialog_options(
            env,
            auth_cookie_after_restart,
            include_kinds,
            selected_dialog_ids,
        )
        selected_entries = [entry for entry in options_after_restart if entry["value"] in selected_dialog_ids]
        assert {entry["value"] for entry in selected_entries} == set(selected_dialog_ids)
        selected_entries_by_id = {str(entry["value"]): entry for entry in selected_entries}
        for dialog in expected_selected_after_restart:
            dialog_id = str(dialog["id"])
            assert selected_entries_by_id[dialog_id]["name"].startswith(
                f"{dialog['name']} ({dialog['kind']}) - "
            )
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_message_reader_returns_live_messages_with_image_only_media() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _seed_real_telegram_session_volume(env)
        _wait_for_health(env)

        auth_cookie = _login(env)
        body = _wait_for_node_types(env, auth_cookie)
        assert '"name":"lookbackHours"' in body, body
        assert '"type":"number"' in body, body

        dialogs = _sort_dialogs(_filtered_supported_dialogs(_wait_for_dialogs(env)))
        assert dialogs, dialogs
        selected_dialog_ids = [str(dialogs[0]["id"])]

        execution_output = _message_reader_execute_result(env, selected_dialog_ids, 24)
        assert len(execution_output) == 1, execution_output
        reader_items = execution_output[0]
        assert isinstance(reader_items, list), reader_items
        assert reader_items, reader_items

        saw_image = False
        for item in reader_items:
            payload = item["json"]
            assert payload["source_id"] in selected_dialog_ids
            assert payload["source_kind"] in SUPPORTED_DIALOG_KINDS
            assert isinstance(payload["message_id"], str)
            assert isinstance(payload["message_timestamp"], str)
            assert payload["text"] or payload["media_items"]
            for media in payload["media_items"]:
                assert media["media_kind"] == "image"
                assert media["ocr_status"] == "pending"
                assert isinstance(media["file_ref"], str) and media["file_ref"]
                saw_image = True

        # Do not require images in every account/window, but when present they must be image-only.
        assert saw_image or any(item["json"]["text"] for item in reader_items)
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_ocr_node_enriches_example_image_message() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _wait_for_health(env)

        auth_cookie = _login(env)
        body = _wait_for_node_types(env, auth_cookie)
        assert OCR_NODE_FULL_TYPE in body, body
        assert '"name":"providerMode"' in body, body

        example_image = "/app/example.jpg"
        execution_output = _ocr_execute_result(
            env,
            [
                {
                    "schema_version": "v1",
                    "source_kind": "channel",
                    "source_id": "-100123",
                    "source_title": "Example",
                    "message_id": "1",
                    "message_timestamp": "2026-03-25T12:00:00Z",
                    "author_id": None,
                    "author_title": None,
                    "text": "",
                    "reply_to_message_id": None,
                    "forwarded_from_source_id": None,
                    "is_outbound": False,
                    "is_from_self": False,
                    "is_service_message": False,
                    "media_items": [
                        {
                            "media_kind": "image",
                            "file_ref": example_image,
                            "ocr_status": "pending",
                        }
                    ],
                    "ingestion_meta": {},
                }
            ],
        )
        assert len(execution_output) == 1, execution_output
        ocr_items = execution_output[0]
        assert isinstance(ocr_items, list) and len(ocr_items) == 1, ocr_items
        payload = ocr_items[0]["json"]
        assert payload["media_items"][0]["ocr_status"] == "done"
        assert payload["media_items"][0]["ocr_text"]
        assert payload["ocr_text"]
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_cleanup_node_combines_messages() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _wait_for_health(env)
        auth_cookie = _login(env)
        body = _wait_for_node_types(env, auth_cookie)
        assert CLEANUP_NODE_FULL_TYPE in body, body

        execution_output = _cleanup_execute_result(
            env,
            [
                {
                    "schema_version": "v1",
                    "source_kind": "channel",
                    "source_id": "-100123",
                    "source_title": "Example",
                    "message_id": "1",
                    "message_timestamp": "2026-03-25T12:00:00Z",
                    "author_id": None,
                    "author_title": None,
                    "text": "Hello",
                    "reply_to_message_id": None,
                    "forwarded_from_source_id": None,
                    "is_outbound": False,
                    "is_from_self": False,
                    "is_service_message": False,
                    "media_items": [],
                    "ocr_text": "OCR",
                    "ingestion_meta": {},
                }
            ],
        )
        payload = execution_output[0][0]["json"]
        assert payload["mode"] == "combined"
        assert "Hello" in payload["combined_text"]
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")


def test_n8n_digest_node_returns_digest_text() -> None:
    docker_ok, docker_reason = _docker_available()
    if not docker_ok:
        pytest.skip(f"Docker Compose is not available: {docker_reason}")

    env = _base_env()
    up = _compose_up(env, "postgres", "api", "n8n")
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        _wait_for_health(env)
        auth_cookie = _login(env)
        body = _wait_for_node_types(env, auth_cookie)
        assert DIGEST_NODE_FULL_TYPE in body, body

        execution_output = _digest_execute_result(
            env,
            [{"formatted_text": "## Example\n\nHello world"}],
        )
        payload = execution_output[0][0]["json"]
        assert payload["provider_id"] == "opencode_cli"
        assert isinstance(payload["digest_text"], str) and payload["digest_text"].strip()
        assert payload["parse_mode"] == "markdown_v2"
        assert isinstance(payload["delivery_chunks"], list) and payload["delivery_chunks"]
        assert payload["digest_text"].startswith("*📰 ДАЙДЖЕСТ НОВИН ЗА ")
    finally:
        _compose_cmd(env, "down", "-v", "--remove-orphans")
