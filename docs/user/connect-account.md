# Connect Telegram Account

## Before you start

- Have these values ready:
  - `api_id` and `api_hash` from https://my.telegram.org (see `docs/user/telegram-app-setup.md`)
  - Your phone number in international format, for example `+380...`

## First run

On the first `make up`, the setup wizard starts automatically in your terminal:

```
=== TG-Dog — Account Setup ===

No connected Telegram account found. Starting setup wizard.

Telegram API ID: _
Telegram API Hash: _
Phone number (with country code, e.g. +380501234567): _

Sending login code to +380*****567...
Enter the login code from Telegram: _

Connected as "Your Name"

Setup complete. The bot is ready.
```

If your account has two-factor authentication, an extra prompt appears for your 2FA password.

## Subsequent runs

On restart, stored credentials are reused automatically:

```
Telegram account connected (Your Name). Skipping setup.
```

## Detached mode

If you run `docker compose up -d` on first run, the container cannot prompt interactively. It will print:

```
No connected Telegram account found.
Run 'make onboard' to complete setup.
```

Then run `make onboard` to start the wizard manually.

## Re-setup

To re-run the wizard at any time:

```
make onboard
```

To disconnect and clear credentials:

```
make disconnect
```

The next startup will trigger the wizard again.

## Common errors during setup

- **Invalid login code**: re-enter the latest code from Telegram (up to 3 attempts).
- **Invalid 2FA password**: re-enter your password (up to 3 attempts).
- **Login flow expired**: the wizard restarts automatically — enter credentials again.
- **Could not start login**: check your API ID and API Hash at https://my.telegram.org.

## Secret handling

- `api_hash` is persisted in `auth_state.json` inside the `telegram_sessions` Docker volume, encrypted with `APP_MASTER_KEY` for newly stored sessions, and should always be treated as sensitive runtime state.
- Login codes and 2FA passwords are never stored.
- Telethon session files stay in the `telegram_sessions` volume.
