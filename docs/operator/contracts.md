# Operator Contract Map

## Canonical Telegram Message Item

The main content-processing path uses one canonical message shape.

Primary sources:
- `api/schemas.py`
- `services/shared/contracts/message.py`

Core fields:
- `schema_version`
- `source_kind`
- `source_id`
- `source_title`
- `message_id`
- `message_timestamp`
- `author_id`
- `author_title`
- `text`
- `reply_to_message_id`
- `forwarded_from_source_id`
- `is_outbound`
- `is_from_self`
- `is_service_message`
- `media_items`
- `ingestion_meta`

Invariants:
- one item = one Telegram message
- media stays attached to that same message item
- OCR enrichment stays on that same item
- downstream nodes should not need a join step to reconnect OCR output

## Media Item Rules

Current media item fields:
- `media_kind`
- `file_ref`
- `mime_type`
- `size_bytes`
- `ocr_status`
- `ocr_text`
- `ocr_confidence_hint`
- `ocr_error_code`
- `ocr_error_message`

Current runtime truth:
- image media is the OCR input path
- supported GIF-style media can flow through random read and repost paths
- non-image OCR is not implemented

## Cleanup Contract

`POST /messages/cleanup` returns:
- `mode`
- `output_format`
- `message_count`
- `combined_text`
- `formatted_messages`

This is the formatting boundary between canonical Telegram items and text-oriented downstream steps.

## AI Text Contract

`POST /digest/messages` accepts:
- `formatted_text`
- `command_template`
- `system_prompt`
- `output_format`
- `title_text` (optional)

`POST /digest/messages` returns:
- `digest_text`
- `format`
- `parse_mode`
- `delivery_chunks`
- `provider_id`
- `provider_attempts`
- `message_count`
- `source_count`
- `raw_output`

Despite the node name `TG Dog Digest`, this is the current general worker-backed AI text-processing response shape.

Important behavior:
- output can be plain text or `markdown_v2`
- delivery shaping happens here
- when `title_text` is set, the digest title is prepended in bold for `markdown_v2`
- multi-part digests add `(частина N/total)` to each chunk title automatically
- `delivery_chunks` are already split for downstream Telegram delivery

## Trigger Contracts

### User-message trigger

`TG Dog Message Trigger` delivers canonical Telegram message items to `n8n`.

### Bot-command trigger

`TG Dog Bot Command Trigger` uses a different trigger payload shape.

Key fields:
- `schema_version`
- `trigger_kind`
- `workflow_id`
- `node_id`
- `command`
- `command_text`
- `chat_id`
- `chat_type`
- `message_id`
- `message_timestamp`
- `user_id`
- `username`
- `first_name`
- `last_name`
- `raw_update`

Do not distort canonical Telegram message items to look like bot-command payloads, and do not distort bot-command payloads to look canonical unless you are explicitly adding a normalizer step.

## Large Payload Rules

- Large runtime payloads should move by file reference, not giant inline blobs.
- Artifact helpers under `services/shared/runtime/` are the operational truth.
- Preserve previous output refs for downstream steps instead of mutating old artifacts in place.

## Legacy Contracts Still In Repo

The repo still contains contract files for heuristic/classification and older CLI-oriented flows.

Current stance:
- they are real code paths in `services/`
- they are not the main current `n8n` product path
- do not present them as the default UX without fresh verification
