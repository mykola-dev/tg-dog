from services.shared.telegram.markdown_v2 import prepare_digest_delivery


def test_prepare_digest_delivery_normalizes_common_markdown_to_markdown_v2() -> None:
    prepared = prepare_digest_delivery(
        raw_text="# Title\n\n- Item with **bold** and __italic__ and [link](https://example.com/a_b)",
        output_format="markdown_v2",
    )

    assert prepared.text == "*Title*\n\n\\- Item with *bold* and _italic_ and [link](https://example.com/a_b)"
    assert prepared.chunks == [prepared.text]


def test_prepare_digest_delivery_preserves_existing_emphasis_markers() -> None:
    prepared = prepare_digest_delivery(
        raw_text=(
            "*🔴 БАВОВНА НА БАЛТІЙЦІ: ПОРТИ ГОРИМО, АГРОНІ В БІГАННЯХ*\n\n"
            "Дрони Сил оборони продовжують кошмарити ключові порти бидлостану.\n\n"
            "_Люботин, STERNENKO, Volodymyr Zolkin_"
        ),
        output_format="markdown_v2",
    )

    assert prepared.text.startswith("*🔴 БАВОВНА")
    assert "\\*🔴" not in prepared.text
    assert "_Люботин, STERNENKO, Volodymyr Zolkin_" in prepared.text
    assert "\\_Люботин" not in prepared.text


def test_prepare_digest_delivery_chunks_on_block_boundaries() -> None:
    raw_text = "\n\n".join(f"- Block {index}: {'text ' * 80}" for index in range(1, 6))

    prepared = prepare_digest_delivery(raw_text=raw_text, output_format="markdown_v2", chunk_size=220)

    assert len(prepared.chunks) > 1
    for chunk in prepared.chunks:
        assert len(chunk) <= 220
    assert prepared.chunks[0].startswith("\\-")
    assert all("Block" in chunk or "text text" in chunk for chunk in prepared.chunks)


def test_prepare_digest_delivery_code_blocks_stay_fenced_after_chunking() -> None:
    raw_text = "```python\n" + "print('hello world')\n" * 120 + "```"

    prepared = prepare_digest_delivery(raw_text=raw_text, output_format="markdown_v2", chunk_size=220)

    assert len(prepared.chunks) > 1
    assert all(chunk.startswith("```") and chunk.endswith("```") for chunk in prepared.chunks)


def test_prepare_digest_delivery_adds_bold_title_to_single_chunk() -> None:
    prepared = prepare_digest_delivery(
        raw_text="- Item one\n- Item two",
        output_format="markdown_v2",
        title_text="📰 ДАЙДЖЕСТ НОВИН ЗА 29 березня",
    )

    assert prepared.text.startswith("*📰 ДАЙДЖЕСТ НОВИН ЗА 29 березня*")
    assert prepared.text.split("\n\n", 1)[1].startswith("\\-")
    assert prepared.chunks == [prepared.text]


def test_prepare_digest_delivery_adds_part_labels_to_multi_chunk_title() -> None:
    raw_text = "\n\n".join(f"- Block {index}: {'text ' * 60}" for index in range(1, 6))

    prepared = prepare_digest_delivery(
        raw_text=raw_text,
        output_format="markdown_v2",
        title_text="📰 ДАЙДЖЕСТ НОВИН ЗА 29 березня",
        chunk_size=180,
    )

    assert len(prepared.chunks) > 1
    assert prepared.text.startswith("*📰 ДАЙДЖЕСТ НОВИН ЗА 29 березня*")
    assert prepared.chunks[0].startswith("*📰 ДАЙДЖЕСТ НОВИН ЗА 29 березня \\(частина 1/")
    assert prepared.chunks[-1].startswith(f"*📰 ДАЙДЖЕСТ НОВИН ЗА 29 березня \\(частина {len(prepared.chunks)}/{len(prepared.chunks)}\\)*")
    assert all(len(chunk) <= 180 for chunk in prepared.chunks)


def test_prepare_digest_delivery_adds_plain_text_part_labels() -> None:
    raw_text = " ".join("word" for _ in range(120))

    prepared = prepare_digest_delivery(
        raw_text=raw_text,
        output_format="plain_text",
        title_text="Дайджест новин за 29 березня",
        chunk_size=80,
    )

    assert len(prepared.chunks) > 1
    assert prepared.chunks[0].startswith("Дайджест новин за 29 березня (частина 1/")
    assert prepared.text.startswith("Дайджест новин за 29 березня\n\n")
