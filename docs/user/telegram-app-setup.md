# Telegram App Setup

## What this is for

TG-Dog logs in through Telegram's client API, so you need your own `api_id` and `api_hash` from `https://my.telegram.org/apps`.

You are not publishing a public mobile app here. You are creating credentials for this self-hosted Telegram digest client to read your selected chats and send digests back to your account.

## Before you start

- Use the Telegram account you want this project to read from.
- Sign in at `https://my.telegram.org` with the same phone number as that Telegram account.
- Telegram sends the developer portal login code inside Telegram itself, not necessarily by SMS.
- You are done with this page only after you have copied both `api_id` and `api_hash`.

## Confirmed for this project

- Open `https://my.telegram.org`, then go to `API development tools`.
- Telegram will show a `Create new application` form if you do not already have an app for this phone number.
- When the form succeeds, Telegram shows `api_id` and `api_hash`.
- Telethon's current docs say there is no need to enter a `URL`, so leaving `URL` empty is the default starting point in this guide.
- `api_hash` is secret. Do not post it in chats, screenshots, tickets, or commits.

## Fill in the application form

Use plain, boring values first. Fancy names and punctuation cause a lot of avoidable failures.

- **App title:** use a short plain name with normal letters and digits.
  - Good examples: `Digest Reader`, `Local Digest`, `Channel Digest`
  - Safer fallback examples: `DigestReader1`, `LocalDigest1`
- **Short name:** use a compact lowercase identifier with letters and digits only.
  - Good examples: `digestreader`, `localdigest`, `channeldigest1`
  - Avoid spaces, underscores, hyphens, emoji, and decorative punctuation.
- **URL:** leave it empty first.
  - If Telegram suddenly starts requiring a value for your account/session, see the fallback section below instead of inventing a fake official rule.
- **Platform:** start with `Desktop`.
  - This is a practical recommendation for a local self-hosted client, not a Telegram requirement.
- **Description:** paste a plain English sentence.
  - Suggested text: `Local self-hosted Telegram digest client for reading selected chats and sending summaries back to my account.`

## Observed Telegram portal behavior (2026-03-22)

- `incorrect app title` or `Incorrect app name!` often means Telegram rejected the short name, not only the full title.
- Short names with only lowercase letters and digits are more reliable than names with spaces, underscores, or punctuation.
- `Platform: Desktop` is a commonly working choice, but some users report that `Web` worked better in their specific setup. Treat platform choice as a workaround lever, not a guaranteed fix.
- Telegram's form can fail for reasons unrelated to your values: ad blockers, VPN/IP mismatch, browser session issues, or just portal instability.
- Leaving `URL` empty often works, but if Telegram currently forces a value for your account/session, use a simple homepage URL you control or another benign project URL that matches your environment. Do not assume one universal placeholder always works.

## If Telegram rejects the form

Try these in order. Change one thing at a time so you know what actually fixed it.

| Portal response | Try this next |
| --- | --- |
| `incorrect app title` / `Incorrect app name!` | Change both names to plain alphanumeric values like `DigestReader1` and `digestreader1`. |
| Generic `ERROR` | Retry with simpler names, then refresh the page and submit again. |
| Form submits and nothing useful happens | Re-open `https://my.telegram.org/apps`, refill the form, and try again in a fresh session. |

If the first attempt fails, use this fallback sequence:

1. Simplify `App title` to letters and digits only.
2. Simplify `Short name` to lowercase letters and digits only.
3. Remove decorative punctuation and brand-like words from both names.
4. Retry in a fresh browser session or private/incognito window.
5. Disable ad blockers or privacy extensions for `my.telegram.org`.
6. If you are using a VPN or proxy, retry without it or from a network closer to your phone number's country.
7. If Telegram currently requires a `URL`, paste a simple real-looking homepage URL instead of a random placeholder.
8. If the portal is still flaky, retry from a phone browser.

This is the shortest safe version of the fallback logic: use letters and digits only, use lowercase letters and digits only for the short name, remove decorative punctuation, drop brand-like words, retry in a fresh browser session or private/incognito window, disable ad blockers, and only add a `URL` if Telegram currently requires one.

## After creation

Copy and save:

- `api_id`
- `api_hash`

Secret handling:

- `api_id` can be stored as normal config.
- `api_hash` is treated as a secret and is persisted in the `telegram_sessions` Docker volume encrypted with `APP_MASTER_KEY` for newly stored sessions.
- Login code and 2FA password are ephemeral and not stored after auth completion.

Next step:

- Continue to `docs/user/connect-account.md`.
