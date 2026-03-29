from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import json
import mimetypes
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl import types as telethon_types
    from telethon.errors import (
        FloodWaitError,
        PasswordHashInvalidError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        SessionPasswordNeededError,
        SlowModeWaitError,
    )
except Exception:  # pragma: no cover
    TelegramClient = None
    StringSession = None
    telethon_types = None
    FloodWaitError = None
    PasswordHashInvalidError = None
    PhoneCodeExpiredError = Exception
    PhoneCodeInvalidError = Exception
    SessionPasswordNeededError = Exception
    SlowModeWaitError = None

from services.shared.telegram.errors import TelegramAuthError, TelegramDeliveryError, TelegramOperationalError
from services.shared.telegram.markdown_v2 import MARKDOWN_V2_PARSE_MODE

DELIVERY_MODES = {"auto", "send", "forward", "copy"}

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _legacy_encrypt_secret(value: str) -> str:
    return f"enc:{value[::-1]}"


def _secret_fernet() -> Fernet:
    master_key = os.getenv("APP_MASTER_KEY")
    if not master_key:
        raise ValueError("MASTER_KEY_MISSING")
    derived_key = hashlib.sha256(master_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived_key))


def _encrypt_secret(value: str) -> str:
    token = _secret_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"fernet:{token}"


def _decrypt_secret(value: str) -> str:
    if value.startswith("fernet:"):
        try:
            decrypted = _secret_fernet().decrypt(value.replace("fernet:", "", 1).encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError("SECRET_FORMAT_INVALID") from exc
        return decrypted.decode("utf-8")
    if value.startswith("enc:"):
        return value.replace("enc:", "", 1)[::-1]
    raise ValueError("SECRET_FORMAT_INVALID")


def _is_invalid_2fa_error(exc: Exception) -> bool:
    if isinstance(PasswordHashInvalidError, type) and isinstance(exc, PasswordHashInvalidError):
        return True
    exc_name = exc.__class__.__name__.lower()
    exc_message = str(exc).lower()
    return "passwordhashinvalid" in exc_name or "password hash invalid" in exc_message


def _build_last_auth_error(*, code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _to_source_kind(entity: Any) -> str:
    if getattr(entity, "broadcast", False):
        return "channel"
    if getattr(entity, "megagroup", False):
        return "group"
    if getattr(entity, "bot", False):
        return "contact"
    if hasattr(entity, "title"):
        return "group"
    return "contact"


def _entity_title(entity: Any) -> str:
    if getattr(entity, "is_self", False):
        return "Saved Messages"
    if getattr(entity, "title", None):
        return str(entity.title)
    first_name = getattr(entity, "first_name", None) or ""
    last_name = getattr(entity, "last_name", None) or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Unknown"


def _guess_media_extension(*, mime_type: str | None, media_kind: str | None) -> str:
    normalized_mime = (mime_type or "").strip().lower()
    normalized_kind = (media_kind or "").strip().lower()
    if normalized_kind == "gif":
        if normalized_mime == "video/mp4":
            return ".mp4"
        return ".gif"
    guessed = mimetypes.guess_extension(normalized_mime) if normalized_mime else None
    if guessed:
        return guessed
    if normalized_kind == "image":
        return ".jpg"
    return ".bin"

class TelegramClientWrapper:
    def __init__(self, session_root: Path) -> None:
        self.session_root = session_root
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.state_file = self.session_root / "auth_state.json"
        self.flow_file = self.session_root / "auth_flow.json"
        self.session_file_base = self.session_root / "telethon"

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _session_base_path(self, *, purpose: str | None = None) -> Path:
        if not purpose:
            return self.session_file_base
        safe_purpose = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in purpose.strip().lower()) or "default"
        return self.session_root / f"telethon-{safe_purpose}"

    def _save_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _persist_auth_state(
        self,
        *,
        account_state: str,
        api_id: str | None,
        api_hash_encrypted: str | None,
        last_successful_auth_at: str | None = None,
        last_auth_error: dict[str, str] | None = None,
        account_profile: dict[str, str] | None = None,
    ) -> None:
        self._save_json(
            self.state_file,
            {
                "account_state": account_state,
                "last_successful_auth_at": last_successful_auth_at,
                "last_auth_error": last_auth_error,
                "api_id": api_id,
                "api_hash_encrypted": api_hash_encrypted,
                "account_profile": account_profile,
            },
        )

    def _load_auth_flow(self, *, auth_flow_id: str) -> dict[str, Any]:
        flow = self._load_json(self.flow_file)
        if not flow or flow.get("auth_flow_id") != auth_flow_id:
            raise TelegramAuthError(code="AUTH_FLOW_NOT_FOUND")

        expires_at_raw = flow.get("expires_at")
        if not isinstance(expires_at_raw, str):
            raise TelegramAuthError(code="AUTH_FLOW_NOT_FOUND")

        expires_at = datetime.fromisoformat(expires_at_raw)
        if _utc_now() >= expires_at:
            self._persist_auth_state(
                account_state="error",
                api_id=flow.get("api_id"),
                api_hash_encrypted=flow.get("api_hash_encrypted"),
                last_auth_error=_build_last_auth_error(
                    code="AUTH_FLOW_EXPIRED",
                    message="Your login session expired. Start again from step 1.",
                ),
            )
            raise TimeoutError("AUTH_FLOW_EXPIRED")

        return flow

    def _build_client(self, api_id: str, api_hash: str, *, purpose: str | None = None):
        if TelegramClient is None:
            raise TelegramOperationalError(
                code="TELETHON_NOT_INSTALLED",
                message="Telethon is required for Telegram authentication but is not installed.",
            )
        return TelegramClient(str(self._session_base_path(purpose=purpose)), int(api_id), api_hash)

    def _copy_session_file(self, *, source_base: Path, target_base: Path) -> None:
        for suffix in (".session", ".session-journal"):
            source = Path(f"{source_base}{suffix}")
            target = Path(f"{target_base}{suffix}")
            if not source.exists():
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

    def prepare_event_session(self, *, purpose: str = "events") -> Path:
        source_base = self.session_file_base
        target_base = self._session_base_path(purpose=purpose)
        self._copy_session_file(source_base=source_base, target_base=target_base)
        return target_base

    async def _async_send_code(self, *, api_id: str, api_hash: str, phone_number: str) -> str:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            sent_code = await client.send_code_request(phone_number)
            phone_code_hash = getattr(sent_code, "phone_code_hash", None)
            if not isinstance(phone_code_hash, str) or not phone_code_hash:
                raise TelegramOperationalError(
                    code="AUTH_FLOW_INIT_FAILED",
                    message="Could not initialize Telegram login flow. Please try again.",
                )
            return phone_code_hash
        finally:
            await client.disconnect()

    async def _async_sign_in_with_code(
        self,
        *,
        api_id: str,
        api_hash: str,
        phone_number: str,
        login_code: str,
        phone_code_hash: str,
    ) -> dict[str, Any]:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            me = await client.sign_in(
                phone=phone_number,
                code=login_code,
                phone_code_hash=phone_code_hash,
            )
            if me is None:
                me = await client.get_me()
            return {
                "id": str(me.id) if me else None,
                "display_name": _entity_title(me) if me else "Unknown",
            }
        finally:
            await client.disconnect()

    async def _async_sign_in_with_password(
        self,
        *,
        api_id: str,
        api_hash: str,
        password: str,
    ) -> dict[str, Any]:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            me = await client.sign_in(password=password)
            if me is None:
                me = await client.get_me()
            return {
                "id": str(me.id) if me else None,
                "display_name": _entity_title(me) if me else "Unknown",
            }
        finally:
            await client.disconnect()

    async def _async_status(self, *, api_id: str, api_hash: str) -> dict[str, Any] | None:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            authorized = await client.is_user_authorized()
            if not authorized:
                return None
            me = await client.get_me()
            return {
                "id": str(me.id) if me else None,
                "display_name": _entity_title(me) if me else "Unknown",
            }
        finally:
            await client.disconnect()

    def _message_has_supported_image(self, message: Any) -> bool:
        if getattr(message, "photo", None) is not None:
            return True
        media = getattr(message, "media", None)
        if media is None:
            return False
        document = getattr(media, "document", None)
        if document is None:
            return False
        mime_type = str(getattr(document, "mime_type", "") or "").lower()
        return mime_type.startswith("image/") and mime_type != "image/gif"

    def _message_has_supported_gif(self, message: Any) -> bool:
        media = getattr(message, "media", None)
        if media is None:
            return False
        document = getattr(media, "document", None)
        if document is None:
            return False
        mime_type = str(getattr(document, "mime_type", "") or "").lower()
        if mime_type in {"image/gif", "video/mp4"}:
            return True
        for attribute in getattr(document, "attributes", []) or []:
            if attribute.__class__.__name__ == "DocumentAttributeAnimated":
                return True
        return False

    async def _async_collect_supported_media_items(
        self,
        *,
        client: Any,
        source_ref: str,
        message: Any,
        workspace_path: Path,
        run_id: str,
        include_gifs: bool = False,
    ) -> list[dict[str, Any]]:
        media_items: list[dict[str, Any]] = []
        media_dir = workspace_path / "runs" / run_id / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        if self._message_has_supported_image(message):
            media_path = media_dir / f"{source_ref}_{message.id}.jpg"
            downloaded = await client.download_media(message, file=str(media_path))
            if downloaded:
                media_items.append(
                    {
                        "media_kind": "image",
                        "file_ref": str(Path(downloaded).resolve()),
                        "mime_type": None,
                        "size_bytes": None,
                        "ocr_status": "pending",
                    }
                )
            return media_items

        if include_gifs and self._message_has_supported_gif(message):
            media = getattr(message, "media", None)
            document = getattr(media, "document", None) if media is not None else None
            mime_type = str(getattr(document, "mime_type", "") or "") or None
            size_bytes = getattr(document, "size", None)
            extension = _guess_media_extension(mime_type=mime_type, media_kind="gif")
            media_path = media_dir / f"{source_ref}_{message.id}{extension}"
            downloaded = await client.download_media(message, file=str(media_path))
            if downloaded:
                media_items.append(
                    {
                        "media_kind": "gif",
                        "file_ref": str(Path(downloaded).resolve()),
                        "mime_type": mime_type,
                        "size_bytes": int(size_bytes) if isinstance(size_bytes, int) else None,
                        "ocr_status": "skipped",
                    }
                )

        return media_items

    async def _async_build_canonical_message(
        self,
        *,
        client: Any,
        source_ref: str,
        entity: Any,
        message: Any,
        workspace_path: Path,
        run_id: str,
        include_media: bool = True,
        include_gifs: bool = False,
    ) -> dict[str, Any] | None:
        if message is None or message.date is None:
            return None

        message_ts = message.date.astimezone(timezone.utc)
        text_value = message.message or ""
        media_items: list[dict[str, Any]] = []
        if include_media:
            media_items = await self._async_collect_supported_media_items(
                client=client,
                source_ref=source_ref,
                message=message,
                workspace_path=workspace_path,
                run_id=run_id,
                include_gifs=include_gifs,
            )

        if not text_value and not media_items:
            return None

        return {
            "schema_version": "v1",
            "source_kind": _to_source_kind(entity),
            "source_id": str(source_ref),
            "source_title": _entity_title(entity),
            "message_id": str(message.id),
            "message_timestamp": message_ts.isoformat(),
            "author_id": str(getattr(message, "sender_id", "")) or None,
            "author_title": None,
            "text": text_value,
            "reply_to_message_id": str(message.reply_to_msg_id) if getattr(message, "reply_to_msg_id", None) else None,
            "forwarded_from_source_id": None,
            "is_outbound": bool(getattr(message, "out", False)),
            "is_from_self": bool(getattr(message, "out", False)),
            "is_service_message": bool(getattr(message, "action", None) is not None),
            "media_items": media_items,
            "ingestion_meta": {
                "telegram_peer_ref": str(source_ref),
            },
        }

    async def _async_fetch_messages(
        self,
        *,
        api_id: str,
        api_hash: str,
        source_refs: list[str],
        limit_per_source: int,
        time_window_start: datetime | None,
        time_window_end: datetime | None,
        workspace_path: Path,
        run_id: str,
        include_media: bool = True,
    ) -> list[dict[str, Any]]:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        out: list[dict[str, Any]] = []

        try:
            for source_ref in source_refs:
                try:
                    entity_ref: str | int
                    if source_ref.lstrip("-").isdigit():
                        entity_ref = int(source_ref)
                    else:
                        entity_ref = source_ref
                    entity = await client.get_entity(entity_ref)
                except Exception:
                    continue

                async for message in client.iter_messages(entity, limit=limit_per_source):
                    if message is None or message.date is None:
                        continue
                    message_ts = message.date.astimezone(timezone.utc)
                    if time_window_start and message_ts < time_window_start:
                        break
                    if time_window_end and message_ts >= time_window_end:
                        continue

                    canonical = await self._async_build_canonical_message(
                        client=client,
                        source_ref=str(source_ref),
                        entity=entity,
                        message=message,
                        workspace_path=workspace_path,
                        run_id=run_id,
                        include_media=include_media,
                        include_gifs=False,
                    )
                    if canonical:
                        out.append(canonical)
        finally:
            await client.disconnect()
        return out

    async def _async_pick_random_message(
        self,
        *,
        api_id: str,
        api_hash: str,
        source_ref: str,
        workspace_path: Path,
        run_id: str,
        skip_empty_text: bool,
        ignore_self: bool,
        ignore_service_messages: bool,
    ) -> dict[str, Any] | None:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            entity_ref: str | int
            if source_ref.lstrip("-").isdigit():
                entity_ref = int(source_ref)
            else:
                entity_ref = source_ref
            entity = await client.get_entity(entity_ref)

            history_probe = await client.get_messages(entity, limit=0)
            total_messages = int(getattr(history_probe, "total", 0) or 0)
            if total_messages <= 0:
                return None

            max_attempts = min(max(total_messages, 1), 50)
            tried_offsets: set[int] = set()

            for _ in range(max_attempts):
                offset = random.randint(0, max(total_messages - 1, 0))
                if offset in tried_offsets and len(tried_offsets) < total_messages:
                    continue
                tried_offsets.add(offset)

                batch = await client.get_messages(entity, limit=1, add_offset=offset)
                if not batch:
                    continue
                message = batch[0]
                if message is None or message.date is None:
                    continue
                if ignore_self and bool(getattr(message, "out", False)):
                    continue
                if ignore_service_messages and bool(getattr(message, "action", None) is not None):
                    continue

                canonical = await self._async_build_canonical_message(
                    client=client,
                    source_ref=str(source_ref),
                    entity=entity,
                    message=message,
                    workspace_path=workspace_path,
                    run_id=run_id,
                    include_gifs=True,
                )
                if not canonical:
                    continue
                if skip_empty_text and not str(canonical.get("text") or "").strip() and not canonical.get("media_items"):
                    continue

                return canonical

            return None
        finally:
            await client.disconnect()

    async def _async_open_event_client(self, *, api_id: str, api_hash: str):
        if TelegramClient is None or StringSession is None:
            raise TelegramOperationalError(
                code="TELETHON_NOT_INSTALLED",
                message="Telethon is required for Telegram realtime triggers but is not installed.",
            )

        source_client = self._build_client(api_id, api_hash)
        await source_client.connect()
        try:
            authorized = await source_client.is_user_authorized()
            if not authorized:
                raise TelegramAuthError(code="AUTH_REQUIRED", message="Telegram session is not authorized")
            session_string = StringSession.save(source_client.session)
        finally:
            await source_client.disconnect()

        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        await client.connect()
        authorized = await client.is_user_authorized()
        if not authorized:
            await client.disconnect()
            raise TelegramAuthError(code="AUTH_REQUIRED", message="Telegram session is not authorized")
        return client

    def _can_send_to_dialog(self, dialog: Any) -> bool:
        entity = getattr(dialog, "entity", None)
        if entity is None:
            return False
        if getattr(entity, "bot", False):
            return False
        if getattr(entity, "broadcast", False):
            return bool(getattr(entity, "creator", False) or getattr(entity, "admin_rights", None))
        return True

    async def _async_send_text_chunk(
        self,
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            authorized = await client.is_user_authorized()
            if not authorized:
                raise TelegramDeliveryError(
                    code="AUTH_REQUIRED",
                    message="Telegram session is not authorized",
                    retryable=False,
                )
            me = await client.get_me()
            if me is None or getattr(me, "id", None) is None:
                raise TelegramDeliveryError(
                    code="AUTH_REQUIRED",
                    message="Telegram account profile is unavailable",
                    retryable=False,
                )
            target_entity: Any
            if target_id == "self":
                target_entity = me
                target_chat_id = str(me.id)
            else:
                entity_ref: str | int = int(target_id) if target_id.lstrip("-").isdigit() else target_id
                try:
                    target_entity = await client.get_entity(entity_ref)
                except Exception as exc:
                    raise TelegramDeliveryError(
                        code="DELIVERY_TARGET_NOT_FOUND",
                        message=f"Telegram delivery target not found: {target_id}",
                        retryable=False,
                    ) from exc
                target_chat_id = str(getattr(target_entity, "id", target_id))

            send_kwargs: dict[str, Any] = {}
            message_payload = chunk_text
            if parse_mode == MARKDOWN_V2_PARSE_MODE:
                raise TelegramDeliveryError(
                    code="POST_MARKDOWN_V2_BOT_ONLY",
                    message="MarkdownV2 delivery is currently supported only for bot sender mode",
                    retryable=False,
                )
            if parse_mode == "markdown":
                send_kwargs["parse_mode"] = "md"

            if media_file_ref:
                force_document = media_kind not in {"image", "gif"}
                send_kwargs["force_document"] = force_document
                if media_mime_type:
                    send_kwargs["mime_type"] = media_mime_type
                if media_kind == "gif" and telethon_types is not None:
                    send_kwargs["attributes"] = [
                        telethon_types.DocumentAttributeFilename(Path(media_file_ref).name),
                        telethon_types.DocumentAttributeAnimated(),
                    ]
                if media_kind == "gif" and media_mime_type == "video/mp4":
                    send_kwargs["nosound_video"] = False
                sent_message = await client.send_file(
                    target_entity,
                    media_file_ref,
                    caption=message_payload or None,
                    **send_kwargs,
                )
            else:
                sent_message = await client.send_message(target_entity, message_payload, **send_kwargs)
            return {
                "chat_id": target_chat_id,
                "message_id": str(sent_message.id),
            }
        finally:
            await client.disconnect()

    async def _async_repost_message(
        self,
        *,
        api_id: str,
        api_hash: str,
        target_id: str,
        source_id: str,
        source_message_id: str,
        mode: str,
    ) -> dict[str, str]:
        if mode not in {"forward", "copy"}:
            raise TelegramDeliveryError(
                code="POST_DELIVERY_MODE_UNSUPPORTED",
                message=f"Unsupported Telegram repost mode: {mode}",
                retryable=False,
            )

        client = self._build_client(api_id, api_hash)
        await client.connect()
        try:
            authorized = await client.is_user_authorized()
            if not authorized:
                raise TelegramDeliveryError(
                    code="AUTH_REQUIRED",
                    message="Telegram session is not authorized",
                    retryable=False,
                )

            me = await client.get_me()
            if me is None or getattr(me, "id", None) is None:
                raise TelegramDeliveryError(
                    code="AUTH_REQUIRED",
                    message="Telegram account profile is unavailable",
                    retryable=False,
                )

            target_entity: Any
            if target_id == "self":
                target_entity = me
                target_chat_id = str(me.id)
            else:
                target_entity_ref: str | int = int(target_id) if target_id.lstrip("-").isdigit() else target_id
                try:
                    target_entity = await client.get_entity(target_entity_ref)
                except Exception as exc:
                    raise TelegramDeliveryError(
                        code="DELIVERY_TARGET_NOT_FOUND",
                        message=f"Telegram delivery target not found: {target_id}",
                        retryable=False,
                    ) from exc
                target_chat_id = str(getattr(target_entity, "id", target_id))

            source_entity_ref: str | int = int(source_id) if source_id.lstrip("-").isdigit() else source_id
            try:
                source_entity = await client.get_entity(source_entity_ref)
            except Exception as exc:
                raise TelegramDeliveryError(
                    code="DELIVERY_SOURCE_NOT_FOUND",
                    message=f"Telegram source not found for repost: {source_id}",
                    retryable=False,
                ) from exc

            try:
                message_id = int(source_message_id)
            except (TypeError, ValueError) as exc:
                raise TelegramDeliveryError(
                    code="DELIVERY_SOURCE_MESSAGE_INVALID",
                    message=f"Telegram source message id is invalid: {source_message_id}",
                    retryable=False,
                ) from exc

            if mode == "forward":
                sent_message = await client.forward_messages(
                    target_entity,
                    message_id,
                    from_peer=source_entity,
                )
            else:
                original_message = await client.get_messages(source_entity, ids=message_id)
                if original_message is None:
                    raise TelegramDeliveryError(
                        code="DELIVERY_SOURCE_MESSAGE_NOT_FOUND",
                        message=f"Telegram source message not found: {source_id}/{source_message_id}",
                        retryable=False,
                    )
                sent_message = await client.send_message(target_entity, original_message)

            return {
                "chat_id": target_chat_id,
                "message_id": str(sent_message.id),
            }
        finally:
            await client.disconnect()

    def _load_connected_auth(self) -> tuple[str, str]:
        try:
            state = self._load_json(self.state_file)
        except json.JSONDecodeError as exc:
            raise TelegramDeliveryError(
                code="AUTH_REQUIRED",
                message="Telegram authorization state is invalid and requires re-authentication",
                retryable=False,
            ) from exc
        if not isinstance(state, dict):
            raise TelegramDeliveryError(
                code="AUTH_REQUIRED",
                message="Telegram authorization state is invalid and requires re-authentication",
                retryable=False,
            )
        if state.get("account_state") != "connected":
            raise TelegramDeliveryError(
                code="AUTH_REQUIRED",
                message="Telegram authorization is required before delivery",
                retryable=False,
            )

        api_id = state.get("api_id")
        api_hash_encrypted = state.get("api_hash_encrypted")
        if not api_id or not api_hash_encrypted:
            raise TelegramDeliveryError(
                code="AUTH_REQUIRED",
                message="Telegram authorization is required before delivery",
                retryable=False,
            )
        try:
            normalized_api_id = str(int(str(api_id)))
        except (TypeError, ValueError) as exc:
            raise TelegramDeliveryError(
                code="AUTH_REQUIRED",
                message="Telegram authorization state is invalid and requires re-authentication",
                retryable=False,
            ) from exc
        try:
            api_hash = _decrypt_secret(str(api_hash_encrypted))
        except ValueError as exc:
            raise TelegramDeliveryError(
                code="AUTH_REQUIRED",
                message="Telegram authorization state is invalid and requires re-authentication",
                retryable=False,
            ) from exc
        return normalized_api_id, api_hash

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        telethon_wait_errors = tuple(
            err for err in (FloodWaitError, SlowModeWaitError) if isinstance(err, type) and err is not Exception
        )
        if telethon_wait_errors and isinstance(exc, telethon_wait_errors):
            return True
        exc_name = exc.__class__.__name__.lower()
        exc_message = str(exc).lower()
        return any(token in exc_name for token in ("floodwait", "slowmode", "ratelimit", "retryafter")) or any(
            token in exc_message for token in ("rate limit", "flood", "too many requests", "retry after")
        )

    def _is_auth_error(self, exc: Exception) -> bool:
        exc_name = exc.__class__.__name__.lower()
        exc_message = str(exc).lower()
        auth_tokens = (
            "auth_key_unregistered",
            "authkeyunregistered",
            "session_revoked",
            "session_expired",
            "unauthorized",
            "authorization",
            "not authorized",
            "auth required",
        )
        return any(token in exc_name for token in auth_tokens) or any(token in exc_message for token in auth_tokens)

    def _has_running_event_loop(self) -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    def _should_probe_status(self, state: dict[str, Any]) -> bool:
        account_state = str(state.get("account_state") or "")
        if account_state == "connected":
            return True
        if account_state != "reauth_required":
            return False
        last_auth_error = state.get("last_auth_error")
        if not isinstance(last_auth_error, dict):
            return False
        return str(last_auth_error.get("code") or "") == "STATUS_CHECK_FAILED"

    def start_login(
        self,
        *,
        api_id: str,
        api_hash: str,
        phone_number: str,
        ttl_seconds: int = 900,
    ) -> dict:
        now = _utc_now()
        flow_id = hashlib.sha256(f"{phone_number}:{now.isoformat()}".encode()).hexdigest()[:24]
        expires_at = now + timedelta(seconds=ttl_seconds)

        phone_code_hash = asyncio.run(
            self._async_send_code(
                api_id=api_id,
                api_hash=api_hash,
                phone_number=phone_number,
            )
        )

        flow = {
            "auth_flow_id": flow_id,
            "phone_number": phone_number,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "api_id": api_id,
            "api_hash_encrypted": _encrypt_secret(api_hash),
            "phone_code_hash": phone_code_hash,
        }
        self._save_json(self.flow_file, flow)
        self._persist_auth_state(
            account_state="awaiting_code",
            api_id=api_id,
            api_hash_encrypted=flow["api_hash_encrypted"],
        )
        masked = phone_number[:3] + "***" + phone_number[-2:]
        return {
            "auth_flow_id": flow_id,
            "account_state": "awaiting_code",
            "expires_at": expires_at,
            "masked_phone_number": masked,
        }

    def submit_code(self, *, auth_flow_id: str, login_code: str) -> dict:
        flow = self._load_auth_flow(auth_flow_id=auth_flow_id)
        phone_code_hash = flow.get("phone_code_hash")
        if not isinstance(phone_code_hash, str) or not phone_code_hash:
            self._persist_auth_state(
                account_state="error",
                api_id=flow.get("api_id"),
                api_hash_encrypted=flow.get("api_hash_encrypted"),
                last_auth_error=_build_last_auth_error(
                    code="AUTH_FLOW_EXPIRED",
                    message="Your login session expired. Start again from step 1.",
                ),
            )
            raise TimeoutError("AUTH_FLOW_EXPIRED")

        try:
            profile = asyncio.run(
                self._async_sign_in_with_code(
                    api_id=str(flow["api_id"]),
                    api_hash=_decrypt_secret(flow["api_hash_encrypted"]),
                    phone_number=str(flow["phone_number"]),
                    login_code=login_code,
                    phone_code_hash=phone_code_hash,
                )
            )
        except SessionPasswordNeededError:
            self._persist_auth_state(
                account_state="awaiting_2fa",
                api_id=flow.get("api_id"),
                api_hash_encrypted=flow.get("api_hash_encrypted"),
            )
            return {"account_state": "awaiting_2fa", "account_profile": None}
        except PhoneCodeExpiredError:
            self._persist_auth_state(
                account_state="error",
                api_id=flow.get("api_id"),
                api_hash_encrypted=flow.get("api_hash_encrypted"),
                last_auth_error=_build_last_auth_error(
                    code="AUTH_FLOW_EXPIRED",
                    message="Your login session expired. Start again from step 1.",
                )
            )
            raise TimeoutError("AUTH_FLOW_EXPIRED")
        except PhoneCodeInvalidError as exc:
            raise TelegramAuthError(code="INVALID_CODE") from exc

        self._persist_auth_state(
            account_state="connected",
            api_id=flow.get("api_id"),
            api_hash_encrypted=flow.get("api_hash_encrypted"),
            last_successful_auth_at=_utc_now().isoformat(),
            account_profile=profile,
        )
        if self.flow_file.exists():
            self.flow_file.unlink()
        return {
            "account_state": "connected",
            "account_profile": profile,
        }

    def submit_2fa(self, *, auth_flow_id: str, two_factor_password: str) -> dict:
        flow = self._load_auth_flow(auth_flow_id=auth_flow_id)
        if not two_factor_password:
            raise TelegramAuthError(code="INVALID_2FA")

        try:
            profile = asyncio.run(
                self._async_sign_in_with_password(
                    api_id=str(flow["api_id"]),
                    api_hash=_decrypt_secret(flow["api_hash_encrypted"]),
                    password=two_factor_password,
                )
            )
        except Exception as exc:
            if _is_invalid_2fa_error(exc):
                raise TelegramAuthError(code="INVALID_2FA") from exc
            raise

        self._persist_auth_state(
            account_state="connected",
            api_id=flow.get("api_id"),
            api_hash_encrypted=flow.get("api_hash_encrypted"),
            last_successful_auth_at=_utc_now().isoformat(),
            account_profile=profile,
        )
        if self.flow_file.exists():
            self.flow_file.unlink()
        return {
            "account_state": "connected",
            "account_profile": profile,
        }

    def status(self) -> dict:
        state = self._load_json(self.state_file)
        revoked_flag = self.session_root / "session_revoked.flag"
        if revoked_flag.exists() and state.get("account_state") == "connected":
            state["account_state"] = "reauth_required"
            state["last_auth_error"] = _build_last_auth_error(
                code="SESSION_REVOKED",
                message="Session was revoked and re-auth is required",
            )
            self._save_json(self.state_file, state)

        if self._should_probe_status(state):
            api_id = state.get("api_id")
            api_hash_encrypted = state.get("api_hash_encrypted")
            if api_id and api_hash_encrypted:
                if self._has_running_event_loop():
                    return {
                        "account_state": state.get("account_state", "disconnected"),
                        "account_profile": state.get("account_profile"),
                        "last_successful_auth_at": state.get("last_successful_auth_at"),
                        "last_auth_error": state.get("last_auth_error"),
                    }
                try:
                    profile = asyncio.run(
                        self._async_status(
                            api_id=str(api_id),
                            api_hash=_decrypt_secret(str(api_hash_encrypted)),
                        )
                    )
                    if profile is None:
                        state["account_state"] = "reauth_required"
                        state["last_auth_error"] = _build_last_auth_error(
                            code="SESSION_EXPIRED",
                            message="Telethon session is not authorized",
                        )
                    else:
                        state["account_state"] = "connected"
                        state["account_profile"] = profile
                        state["last_auth_error"] = None
                except Exception as exc:
                    state["account_state"] = "reauth_required"
                    state["last_auth_error"] = _build_last_auth_error(
                        code="STATUS_CHECK_FAILED",
                        message=str(exc),
                    )
                self._save_json(self.state_file, state)

        return {
            "account_state": state.get("account_state", "disconnected"),
            "account_profile": state.get("account_profile"),
            "last_successful_auth_at": state.get("last_successful_auth_at"),
            "last_auth_error": state.get("last_auth_error"),
        }

    def disconnect(self) -> dict:
        for suffix in [".session", ".session-journal"]:
            session_file = Path(f"{self.session_file_base}{suffix}")
            if session_file.exists():
                session_file.unlink()
        self._persist_auth_state(
            account_state="disconnected",
            api_id=None,
            api_hash_encrypted=None,
        )
        return {"account_state": "disconnected"}

    def reset_account(self) -> dict:
        for name in ["auth_state.json", "auth_flow.json", "session_revoked.flag"]:
            path = self.session_root / name
            if path.exists():
                path.unlink()
        for suffix in [".session", ".session-journal"]:
            session_file = Path(f"{self.session_file_base}{suffix}")
            if session_file.exists():
                session_file.unlink()
        return {"account_state": "disconnected", "reset": True}

    async def _async_list_dialogs(self, *, api_id: str, api_hash: str) -> list[dict[str, Any]]:
        client = self._build_client(api_id, api_hash)
        dialogs: list[dict[str, Any]] = []
        async with client:
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                raw_date = getattr(dialog, "date", None)
                dialogs.append({
                    "id": str(dialog.id),
                    "name": _entity_title(entity),
                    "kind": _to_source_kind(entity),
                    "username": getattr(entity, "username", None) or "",
                    "last_message_date": raw_date.isoformat() if raw_date else None,
                    "can_send": self._can_send_to_dialog(dialog),
                })
        return dialogs

    def list_dialogs(self) -> list[dict[str, Any]]:
        """Return all Telegram dialogs for the authenticated account."""
        try:
            api_id, api_hash = self._load_connected_auth()
        except TelegramDeliveryError as exc:
            raise TelegramAuthError(code=exc.code, message=exc.message) from exc
        return asyncio.run(self._async_list_dialogs(api_id=api_id, api_hash=api_hash))

    def fetch_messages(
        self,
        *,
        source_refs: list[str],
        limit_per_source: int,
        time_window_start: datetime | None,
        time_window_end: datetime | None,
        workspace_path: Path,
        run_id: str,
        include_media: bool = True,
    ) -> list[dict[str, Any]]:
        if TelegramClient is None:
            raise TelegramOperationalError(
                code="TELETHON_NOT_INSTALLED",
                message="Telethon is required for Telegram message reads but is not installed.",
            )

        api_id, api_hash = self._load_connected_auth()

        return asyncio.run(
            self._async_fetch_messages(
                api_id=api_id,
                api_hash=api_hash,
                source_refs=source_refs,
                limit_per_source=limit_per_source,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
                workspace_path=workspace_path,
                run_id=run_id,
                include_media=include_media,
            )
        )

    def pick_random_message(
        self,
        *,
        source_ref: str,
        workspace_path: Path,
        run_id: str,
        skip_empty_text: bool = True,
        ignore_self: bool = False,
        ignore_service_messages: bool = True,
    ) -> dict[str, Any] | None:
        if TelegramClient is None:
            raise TelegramOperationalError(
                code="TELETHON_NOT_INSTALLED",
                message="Telethon is required for Telegram message reads but is not installed.",
            )

        api_id, api_hash = self._load_connected_auth()

        return asyncio.run(
            self._async_pick_random_message(
                api_id=api_id,
                api_hash=api_hash,
                source_ref=source_ref,
                workspace_path=workspace_path,
                run_id=run_id,
                skip_empty_text=skip_empty_text,
                ignore_self=ignore_self,
                ignore_service_messages=ignore_service_messages,
            )
        )

    def send_text_chunk(
        self,
        *,
        target_id: str,
        chunk_text: str,
        parse_mode: str = "plain_text",
        media_file_ref: str | None = None,
        media_mime_type: str | None = None,
        media_kind: str | None = None,
    ) -> dict[str, str]:
        api_id, api_hash = self._load_connected_auth()

        try:
            return asyncio.run(
                self._async_send_text_chunk(
                    api_id=api_id,
                    api_hash=api_hash,
                    target_id=target_id,
                    chunk_text=chunk_text,
                    parse_mode=parse_mode,
                    media_file_ref=media_file_ref,
                    media_mime_type=media_mime_type,
                    media_kind=media_kind,
                )
            )
        except TelegramDeliveryError:
            raise
        except Exception as exc:
            if self._is_auth_error(exc):
                raise TelegramDeliveryError(
                    code="AUTH_REQUIRED",
                    message=str(exc) or "Telegram authorization is required before delivery",
                    retryable=False,
                ) from exc
            if self._is_rate_limit_error(exc):
                raise TelegramDeliveryError(
                    code="RATE_LIMIT",
                    message=str(exc) or "Telegram rate limit encountered during delivery",
                    retryable=True,
                ) from exc
            raise TelegramDeliveryError(
                code="DELIVERY_SEND_FAILED",
                message=str(exc) or "Telegram delivery failed",
                retryable=True,
            ) from exc

    def repost_message(
        self,
        *,
        target_id: str,
        source_id: str,
        source_message_id: str,
        mode: str,
    ) -> dict[str, str]:
        if mode not in DELIVERY_MODES - {"auto", "send"}:
            raise TelegramDeliveryError(
                code="POST_DELIVERY_MODE_UNSUPPORTED",
                message=f"Unsupported Telegram repost mode: {mode}",
                retryable=False,
            )

        api_id, api_hash = self._load_connected_auth()

        try:
            return asyncio.run(
                self._async_repost_message(
                    api_id=api_id,
                    api_hash=api_hash,
                    target_id=target_id,
                    source_id=source_id,
                    source_message_id=source_message_id,
                    mode=mode,
                )
            )
        except TelegramDeliveryError:
            raise
        except Exception as exc:
            if self._is_auth_error(exc):
                raise TelegramDeliveryError(
                    code="AUTH_REQUIRED",
                    message=str(exc) or "Telegram authorization is required before delivery",
                    retryable=False,
                ) from exc
            if self._is_rate_limit_error(exc):
                raise TelegramDeliveryError(
                    code="RATE_LIMIT",
                    message=str(exc) or "Telegram rate limit encountered during delivery",
                    retryable=True,
                ) from exc
            raise TelegramDeliveryError(
                code="DELIVERY_SEND_FAILED",
                message=str(exc) or "Telegram delivery failed",
                retryable=True,
            ) from exc
