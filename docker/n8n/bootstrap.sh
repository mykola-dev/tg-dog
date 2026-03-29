#!/bin/sh
set -eu

n8n &
N8N_PID=$!

node - <<'NODE'
const deadline = Date.now() + 120000;
const url = 'http://127.0.0.1:5678/healthz';

async function waitForHealth() {
  let lastError = 'healthz not ready';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `unexpected status ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(`n8n health check failed: ${lastError}`);
}

waitForHealth().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
NODE

/bootstrap/reseed_owner_if_needed.sh

wait "$N8N_PID"
