from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from redscribe.v2.blocks.constants import MAX_TEXT_LENGTH
from redscribe.v2.blocks.diff import block_signature
from redscribe.v2.blocks.markdown import (
    markdown_roundtrip,
    parse_blocks,
    parse_document,
    serialize_block,
    serialize_document,
)
from redscribe.v2.blocks.model import (
    Block,
    BlockDocument,
    Mention,
    clone_block,
    is_known_style,
    is_known_tone,
    is_known_type,
    make_block,
    make_document,
    new_id,
    valid_id,
)
from redscribe.v2.blocks.normalize import (
    normalize_block,
    normalize_document,
    normalize_items,
    normalize_table,
    normalize_text,
)
from redscribe.v2.blocks.types import (
    BLOCK_TYPES,
    CalloutTone,
    ListStyle,
    MentionKind,
)


@pytest.mark.parametrize("block_type", BLOCK_TYPES)
def test_make_block_applies_defaults_for_every_type(block_type: object) -> None:
    block = make_block(
        block_type,
        "body",
        block_id="fixed-id",
        level=5,
        language="python",
        items=["one", "two"],
        checked=[True, False],
        style=ListStyle.ORDERED,
        headers=["Name"],
        rows=[["value"]],
        tone=CalloutTone.WARNING,
        alt="diagram",
        source="/assets/diagram.png",
    )
    assert block.id == "fixed-id"
    assert block.type is block_type
    assert block.text == "body"
    assert block.level == (5 if block_type.value == "heading" else 1)
    assert block.language == ("python" if block_type.value == "code" else "")
    assert block.items == (("one", "two") if block_type.value == "list" else ())
    assert block.checked == ((True, False) if block_type.value == "list" else ())
    assert block.style is ListStyle.ORDERED
    assert block.headers == (("Name",) if block_type.value == "table" else ())
    assert block.rows == ((("value",),) if block_type.value == "table" else ())
    assert block.tone is CalloutTone.WARNING
    assert block.alt == ("diagram" if block_type.value == "image" else "")
    assert block.source == ("/assets/diagram.png" if block_type.value == "image" else "")


def test_plain_text_covers_geometry_blocks() -> None:
    assert make_block("paragraph", "hello world").plain_text == "hello world"
    assert make_block("list", items=["one", "two"]).plain_text == "one\ntwo"
    table = make_block("table", headers=["A", "B"], rows=[["1", "2"], ["3", "4"]])
    assert table.plain_text == "A | B\n1 | 2\n3 | 4"
    assert make_block("divider").plain_text == ""
    image = make_block("image", alt="diagram", source="/diagram.png")
    assert image.plain_text == "diagram /diagram.png"


def test_document_helpers_track_positions_and_revisions() -> None:
    first = make_block("heading", "Block notes", block_id="b1", level=1)
    second = make_block("paragraph", "alpha beta", block_id="b2")
    document = make_document("doc-1", "Block notes", [first, second], tags=["ctf"])
    assert document.block_ids == ("b1", "b2")
    assert document.index_of("b2") == 1
    assert document.index_of("missing") == -1
    assert document.find("b1") is first
    assert document.find("missing") is None
    assert document.word_count == 4
    assert document.with_blocks([second]).revision == 0
    advanced = document.advanced()
    assert advanced.revision == 1
    assert advanced.updated_at
    explicit = document.advanced(9)
    assert explicit.revision == 9


def test_document_dict_roundtrip_preserves_values() -> None:
    block = Mention(MentionKind.FINDING, "F-12", "LFI", 0, 24, "b1")
    document = make_document("doc-1", "Report", [make_block("paragraph", "x", mentions=[block])])
    decoded = BlockDocument.from_dict(document.as_dict())
    assert decoded.id == document.id
    assert decoded.title == document.title
    assert decoded.revision == document.revision
    assert decoded.tags == document.tags
    assert decoded.metadata == document.metadata
    assert decoded.blocks[0].mentions[0].target == "F-12"
    assert Block.from_dict(decoded.blocks[0]) == decoded.blocks[0]


def test_blocks_are_immutable() -> None:
    block = make_block("paragraph", "original", block_id="b1")
    with pytest.raises(FrozenInstanceError):
        block.text = "changed"


def test_from_dict_tolerates_partial_and_invalid_fields() -> None:
    block = Block.from_dict(
        {
            "type": "HEADING",
            "level": 9,
            "items": ["one", 3],
            "checked": [True, False, True],
            "rows": [["a", 2]],
            "mentions": [{"kind": "bad", "target": "x", "start": -4}],
            "attrs": {"a": 1},
        }
    )
    assert block.type.value == "heading"
    assert block.id
    assert block.level == 9
    assert block.items == ("one",)
    assert block.checked == (True,)
    assert block.rows == (("a",),)
    assert block.mentions[0].kind is MentionKind.NOTE
    assert block.mentions[0].start == 0
    assert block.attrs == {"a": ""}


def test_identifiers_and_helpers_are_consistent() -> None:
    generated = new_id("My Prefix")
    assert generated.startswith("myprefix-")
    assert valid_id(generated)
    assert not valid_id("bad id!")
    assert is_known_type("paragraph")
    assert not is_known_type("canvas")
    assert is_known_style("tasks")
    assert not is_known_style("numbered")
    assert is_known_tone("danger")
    assert not is_known_tone("alarming")


def test_clone_block_detaches_identity_and_mentions() -> None:
    mention = Mention(MentionKind.NOTE, "vault", "Vault", 0, 10, "old")
    block = make_block("paragraph", "text", block_id="old", mentions=[mention], attrs={"a": "b"})
    cloned = clone_block(block)
    assert cloned.id != block.id
    assert cloned.mentions == ()
    assert cloned.attrs == {"a": "b"}
    assert cloned.text == block.text


def test_mention_token_roundtrip() -> None:
    mention = Mention(MentionKind.EVIDENCE, "ev-4", "Screenshot", 2, 30, "b7")
    token = mention.token
    assert token == "@[Screenshot](evidence:ev-4)"
    decoded = Mention.from_dict(mention.as_dict())
    assert decoded == mention
    assert decoded.block_id == "b7"


def test_normalize_text_cleans_whitespace_and_caps_length() -> None:
    assert normalize_text(" Café\u00a0noise\u200b  here \n\n\nnext  \r\n") == (
        "Café noise here\n\nnext"
    )
    assert normalize_text("abcdef", max_length=3) == "abc"
    assert normalize_text("a  b\tc") == "a b\tc"


def test_normalize_items_and_table_enforce_shape() -> None:
    assert normalize_items([" one ", "", "two", "three"]) == ("one", "two", "three")
    headers, rows = normalize_table([" A ", "B"], [["1"], ["2", "3", "4"]])
    assert headers == ("A", "B")
    assert rows == (("1", ""), ("2", "3"))


def test_normalize_block_refreshes_geometry_and_mentions() -> None:
    token = "@[vault](note:vault)"
    block = make_block("heading", token + "  ", block_id="b!", level=99, mentions=())
    normalized = normalize_block(block)
    assert normalized.id != "b!"
    assert normalized.text == token
    assert normalized.level == 6
    assert normalized.mentions[0].target == "vault"
    assert normalized.mentions[0].block_id == normalized.id
    assert normalized.mentions[0].end == len(token)
    paragraph = normalize_block({"type": "paragraph", "text": "plain"})
    assert paragraph.level == 1
    assert paragraph.mentions == ()


def test_normalize_document_deduplicates_ids_and_tags() -> None:
    first = make_block("paragraph", "one", block_id="same")
    second = make_block("paragraph", "two", block_id="same")
    document = make_document("doc!", " Title ", [first, second], tags=["Web", "web", " CTF "])
    normalized = normalize_document(document)
    assert normalized.id != "doc!"
    assert normalized.title == "Title"
    assert normalized.block_ids[0] == "same"
    assert normalized.block_ids[1] != "same"
    assert normalized.tags == ("web", "ctf")
    assert normalize_document({"id": "empty", "blocks": []}, require_blocks=False).blocks == ()
    assert len(normalize_document({"id": "empty", "blocks": []}).blocks) == 1


def test_normalize_text_respects_shared_limit() -> None:
    assert len(normalize_text("x" * (MAX_TEXT_LENGTH + 50))) == MAX_TEXT_LENGTH


def test_parse_blocks_recognizes_every_core_shape() -> None:
    markdown = "\n\n".join(
        [
            "# Heading",
            "plain paragraph",
            "```python\nprint('x')\n```",
            "> quoted line",
            "- [ ] open task\n- [x] done task",
            "1. first\n2. second",
            "| A | B |\n| --- | --- |\n| 1 | 2 |",
            "> [!WARNING] be careful",
            "---",
            "![diagram](/diagram.png)",
        ]
    )
    blocks = parse_blocks(markdown)
    assert [block.type.value for block in blocks] == [
        "heading",
        "paragraph",
        "code",
        "quote",
        "list",
        "list",
        "table",
        "callout",
        "divider",
        "image",
    ]
    assert blocks[0].level == 1
    assert blocks[2].language == "python"
    assert blocks[2].text == "print('x')"
    assert blocks[4].items == ("open task", "done task")
    assert blocks[4].checked == (False, True)
    assert blocks[4].style.value == "tasks"
    assert blocks[5].style.value == "ordered"
    assert blocks[6].headers == ("A", "B")
    assert blocks[6].rows == (("1", "2"),)
    assert blocks[7].tone is CalloutTone.WARNING
    assert blocks[8].type.value == "divider"
    assert blocks[9].alt == "diagram"


def test_parse_blocks_escapes_literal_markers() -> None:
    blocks = parse_blocks("\\- not a list\n\\# not a heading")
    assert [block.type.value for block in blocks] == ["paragraph", "paragraph"]
    assert [block.text for block in blocks] == ["- not a list", "# not a heading"]


@pytest.mark.parametrize(
    ("block", "marker"),
    [
        (make_block("heading", "Title", level=2), "## Title"),
        (make_block("code", "x=1", language="python"), "```python"),
        (make_block("quote", "line"), "> line"),
        (make_block("list", items=["a"], style=ListStyle.TASKS, checked=[True]), "- [x] a"),
        (make_block("table", headers=["A"], rows=[["1"]]), "| A |"),
        (make_block("callout", "note", tone=CalloutTone.TIP), "> [!TIP]"),
        (make_block("divider"), "---"),
        (make_block("image", alt="a", source="/a.png"), "![a](/a.png)"),
    ],
)
def test_serialize_block_emits_expected_marker(block: object, marker: str) -> None:
    assert not isinstance(block, str)
    assert marker in serialize_block(block)


def test_parse_document_prepends_missing_title_heading() -> None:
    document = parse_document("body text", document_id="doc-1", title="Report")
    assert document.id == "doc-1"
    assert document.title == "Report"
    assert document.blocks[0].type.value == "heading"
    assert document.blocks[0].text == "Report"
    assert document.blocks[1].text == "body text"


def test_document_markdown_roundtrip_preserves_block_signatures() -> None:
    blocks = [
        make_block("heading", "Report", block_id="b1", level=1),
        make_block("paragraph", "body text", block_id="b2"),
        make_block(
            "list",
            block_id="b3",
            items=["one", "two"],
            checked=[False, True],
            style=ListStyle.TASKS,
        ),
        make_block("code", "print(1)", block_id="b4", language="python"),
        make_block("divider", block_id="b5"),
    ]
    document = make_document("doc-1", "Report", blocks)
    serialized = serialize_document(document)
    reparsed = parse_document(serialized, document_id="doc-1")
    assert [block_signature(block) for block in reparsed.blocks] == [
        block_signature(block) for block in blocks
    ]
    assert markdown_roundtrip(document) == serialized
