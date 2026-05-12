from services.shared.telegram.markdown_v2 import split_html_chunks


def test_split_html_chunks_reopens_inline_tags_across_chunks() -> None:
    chunks = split_html_chunks("<i>Hello brave new world</i>", chunk_size=18)

    assert chunks == ["<i>Hello brave</i>", "<i>new world</i>"]


def test_split_html_chunks_preserves_nested_tags() -> None:
    chunks = split_html_chunks("<b><i>Hello world again</i></b>", chunk_size=19)

    assert chunks == ["<b><i>Hello</i></b>", "<b><i>world</i></b>", "<b><i>again</i></b>"]


def test_split_html_chunks_keeps_anchor_valid() -> None:
    chunks = split_html_chunks('<a href="https://example.com">alpha beta gamma</a>', chunk_size=44)

    assert chunks == [
        '<a href="https://example.com">alpha beta</a>',
        '<a href="https://example.com">gamma</a>',
    ]
