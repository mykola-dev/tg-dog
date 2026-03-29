from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_digest_node_default_title_template_uses_n8n_expression_syntax() -> None:
    source = (ROOT / "n8n/custom-nodes/telegram-digest/TelegramDigest.node.js").read_text(encoding="utf-8")

    assert 'const DEFAULT_TITLE_TEMPLATE = \'={{ "📰 ДАЙДЖЕСТ НОВИН ЗА " + $now.setLocale("uk").toFormat("d MMMM") }}\';' in source


def test_digest_node_sends_title_text_to_api_payload() -> None:
    node_path = ROOT / "n8n/custom-nodes/telegram-digest/TelegramDigest.node.js"
    script = f"""
const path = require('path');
const Module = require('module');
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {{
  if (request === 'n8n-workflow') {{
    return {{ NodeConnectionTypes: {{ Main: 'main' }} }};
  }}
  return originalLoad(request, parent, isMain);
}};

global.fetch = async (_url, options) => {{
  process.stdout.write(options.body);
  return {{
    ok: true,
    text: async () => JSON.stringify({{ digest_text: 'ok', parse_mode: 'markdown_v2', delivery_chunks: ['ok'] }}),
  }};
}};

const {{ TelegramDigest }} = require({str(node_path)!r});

async function main() {{
  const node = new TelegramDigest();
  const context = {{
    getInputData() {{
      return [{{ json: {{ formatted_text: 'Hello world' }} }}];
    }},
    getNodeParameter(name) {{
      if (name === 'commandTemplate') return 'opencode run -m opencode/minimax-m2.5-free "{{prompt}}"';
      if (name === 'systemPrompt') return 'Create digest';
      if (name === 'outputFormat') return 'markdown_v2';
      if (name === 'includeTitle') return true;
      if (name === 'titleTemplate') return '📰 ДАЙДЖЕСТ НОВИН';
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};
  await node.execute.call(context);
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr or result.stdout
    assert '"title_text":"📰 ДАЙДЖЕСТ НОВИН"' in result.stdout


def test_digest_node_omits_title_text_when_disabled() -> None:
    node_path = ROOT / "n8n/custom-nodes/telegram-digest/TelegramDigest.node.js"
    script = f"""
const Module = require('module');
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {{
  if (request === 'n8n-workflow') {{
    return {{ NodeConnectionTypes: {{ Main: 'main' }} }};
  }}
  return originalLoad(request, parent, isMain);
}};

global.fetch = async (_url, options) => {{
  process.stdout.write(options.body);
  return {{
    ok: true,
    text: async () => JSON.stringify({{ digest_text: 'ok', parse_mode: 'markdown_v2', delivery_chunks: ['ok'] }}),
  }};
}};

const {{ TelegramDigest }} = require({str(node_path)!r});

async function main() {{
  const node = new TelegramDigest();
  const context = {{
    getInputData() {{
      return [{{ json: {{ formatted_text: 'Hello world' }} }}];
    }},
    getNodeParameter(name) {{
      if (name === 'commandTemplate') return 'opencode run -m opencode/minimax-m2.5-free "{{prompt}}"';
      if (name === 'systemPrompt') return 'Create digest';
      if (name === 'outputFormat') return 'markdown_v2';
      if (name === 'includeTitle') return false;
      if (name === 'titleTemplate') return 'ignored';
      throw new Error(`unexpected node parameter ${{name}}`);
    }},
  }};
  await node.execute.call(context);
}}

main().catch((error) => {{
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
}});
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr or result.stdout
    assert '"title_text":""' in result.stdout
