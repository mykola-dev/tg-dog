from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime

from services.shared.cli import build_error_envelope, build_success_envelope, emit_envelope
from services.shared.config import load_config
from services.shared.runtime.artifacts import artifact_path, safe_write_json
from services.shared.telegram.client import TelegramClientWrapper
from services.shared.telegram.source_index import SourceRecord


def filter_supported_sources(
    sources: list[SourceRecord],
    delivery_target_id: str | None,
) -> list[SourceRecord]:
    out: list[SourceRecord] = []
    for source in sources:
        if source.is_bot:
            continue
        if source.is_secret_chat:
            continue
        if delivery_target_id and source.source_id == delivery_target_id:
            continue
        out.append(source)
    return out
def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(UTC)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch adapter")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--payload-json", default="{}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    payload = json.loads(args.payload_json)

    raw_sources = payload.get("sources", [])
    delivery_target_id = payload.get("delivery_target_id")

    sources = [
        SourceRecord(
            source_id=entry["source_id"],
            source_kind=entry["source_kind"],
            source_title=entry["source_title"],
            is_bot=entry.get("is_bot", False),
            is_secret_chat=entry.get("is_secret_chat", False),
        )
        for entry in raw_sources
    ]
    selected = filter_supported_sources(sources, delivery_target_id)

    client = TelegramClientWrapper(config.telegram_session_path)
    source_refs = [item.source_id for item in selected]
    time_window_start = _parse_optional_datetime(payload.get("time_window_start"))
    time_window_end = _parse_optional_datetime(payload.get("time_window_end"))
    messages = client.fetch_messages(
        source_refs=source_refs,
        limit_per_source=int(payload.get("fetch_limit_per_source", 50)),
        time_window_start=time_window_start,
        time_window_end=time_window_end,
        workspace_path=config.workspace_path,
        run_id=args.run_id,
    )

    output = {
        "messages": messages,
        "source_snapshot": [asdict(item) for item in selected],
        "window_summary": {
            "mode": payload.get("window_mode", "last_n_hours"),
            "start": time_window_start.isoformat() if time_window_start else None,
            "end": time_window_end.isoformat() if time_window_end else None,
        },
        "checkpoint_suggestions": {
            source.source_id: {"latest_message_id": "1"} for source in selected
        },
    }

    output_path = artifact_path(config.workspace_path, args.run_id, "messages")
    safe_write_json(output_path, output)
    relative_ref = str(output_path.relative_to(config.workspace_path))

    emit_envelope(
        build_success_envelope(
            node_name="fetch",
            run_id=args.run_id,
            payload_ref=relative_ref,
            metrics={"source_count": len(selected), "message_count": len(messages)},
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        emit_envelope(
            build_error_envelope(
                node_name="fetch",
                run_id="unknown",
                code="FETCH_UNEXPECTED",
                message=str(exc),
                retryable=True,
                user_action_required=False,
            )
        )
        raise
