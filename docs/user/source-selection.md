# Source Selection

## Supported sources in V1

- Channels
- Groups / supergroups
- 1:1 human contacts

## Exclusions

- Secret chats are excluded.
- Bot dialogs are excluded.
- Active delivery target cannot be selected as source.

## How sync works

- Source sync is refresh-based and can be re-run from the workflow.
- Include/exclude conflicts resolve with `exclude` taking priority.
- Source IDs are stable; titles may refresh on rename.

## n8n selector node

- Use `TG Dog Source Selector` inside a user-created workflow.
- The node stores selected dialog ids in workflow parameters.
- Labels refresh from live Telegram dialog metadata during execution.
- Workflow restart should not erase selected dialog ids because `n8n` persists workflow definitions in `n8n_data`.

## Downstream reader node

- `TG Dog Message Reader` consumes `selected_dialog_ids` from the selector output.
- It emits `1 item = 1 message`.
- Each item keeps `source_id`, `source_title`, and `source_kind`, so later grouping by source remains possible.
- `Include Media = false` skips attachment downloads for faster text-only runs.

## OCR node

- `TG Dog OCR` enriches message items after the reader step.
- It runs only on image attachments.
- OCR text is added back onto the same message item, so later filter/digest steps do not need a join step.

## Cleanup and posting

- `TG Dog Messages Cleanup` turns message items into reusable formatted text.
- `TG Dog Digest` consumes cleaned combined text and produces one digest output plus pre-split `delivery_chunks` prepared for Telegram-safe `MarkdownV2` bot delivery.
- `TG Dog Post Message` can send either cleaned text or digest text through your Telegram account or through a configured bot.
- `TG Dog Post Message` can also forward or copy the original Telegram message when the input item still carries `source_id` and `message_id`.
- In bot mode the target list reuses Telegram dialogs from your connected account, but bot delivery can still fail if the bot lacks access to the selected target.
