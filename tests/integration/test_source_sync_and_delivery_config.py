from services.shared.telegram.source_index import SourceRecord


def test_source_sync_excludes_bot_dialogs_and_secret_chats() -> None:
    from services.fetch.main import filter_supported_sources

    sources = [
        SourceRecord(source_id="1", source_kind="channel", source_title="Normal"),
        SourceRecord(source_id="2", source_kind="contact", source_title="Bot", is_bot=True),
        SourceRecord(source_id="3", source_kind="group", source_title="Secret", is_secret_chat=True),
    ]

    filtered = filter_supported_sources(sources, delivery_target_id=None)
    assert [s.source_id for s in filtered] == ["1"]


def test_delivery_target_cannot_also_be_selected_as_source() -> None:
    from services.fetch.main import filter_supported_sources

    sources = [
        SourceRecord(source_id="dlg-1", source_kind="channel", source_title="A"),
        SourceRecord(source_id="dlg-2", source_kind="group", source_title="B"),
    ]
    filtered = filter_supported_sources(sources, delivery_target_id="dlg-2")
    assert [s.source_id for s in filtered] == ["dlg-1"]
