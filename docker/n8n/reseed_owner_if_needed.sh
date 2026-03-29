#!/bin/sh
set -eu

SETTINGS_JSON=$(node - <<'NODE'
const deadline = Date.now() + 120000;
const url = 'http://127.0.0.1:5678/rest/settings';

async function waitForSettings() {
  let lastError = 'settings not ready';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        lastError = `settings request failed with ${response.status}`;
      } else {
        const text = await response.text();
        JSON.parse(text);
        process.stdout.write(text);
        return;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(`settings endpoint did not become ready: ${lastError}`);
}

waitForSettings().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
NODE
)

SHOW_SETUP=$(SETTINGS_JSON="$SETTINGS_JSON" node - <<'NODE'
const payload = JSON.parse(process.env.SETTINGS_JSON || '{}');
const showSetup = payload?.data?.userManagement?.showSetupOnFirstLoad;
process.stdout.write(String(showSetup));
NODE
)

if [ "$SHOW_SETUP" != "true" ]; then
  exit 0
fi

n8n user-management:reset

node - <<'NODE'
const body = {
  email: process.env.N8N_BOOTSTRAP_OWNER_EMAIL,
  firstName: process.env.N8N_BOOTSTRAP_OWNER_FIRST_NAME,
  lastName: process.env.N8N_BOOTSTRAP_OWNER_LAST_NAME,
  password: process.env.N8N_BOOTSTRAP_OWNER_PASSWORD,
};

async function main() {
  const response = await fetch('http://127.0.0.1:5678/rest/owner/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`owner setup failed with ${response.status}: ${await response.text()}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
NODE
