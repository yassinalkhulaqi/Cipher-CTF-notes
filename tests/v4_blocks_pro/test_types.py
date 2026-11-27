"""Tests for v4 block editor value types and their invariants."""

from __future__ import annotations

import pytest
from tests.v4_blocks_pro.fixtures import id_factory, make_block, sample_document

from redscribe.v4.blocks_pro.types import (
    ALL_BLOCK_KINDS,
    ALL_BLOCK_OPS,
    ALL_INLINE_MARKS,
    MAX_HEADING_LEVEL,
    MIN_HEADING_LEVEL,
    SLASH_ORDER,
    Block,
    BlockDocument,
    BlockKind,
    BlockOp,
    EditOperation,
    InlineMark,
    ValidationIssue,
    ValidationSeverity,
    attr_pairs,
    canonical_checksum,
    new_block,
    new_document,
    normalize_text,
)


def test_block_kind_catalog_and_parsing() -> None:
    assert len(ALL_BLOCK_KINDS) == 7
    assert {kind.value for kind in ALL_BLOCK_KINDS} == {
        "paragraph",
        "heading",
        "code",
        "list",
        "quote",
        "table",
        "divider",
    }
    assert BlockKind.parse(" HEADING ") is BlockKind.HEADING
    assert BlockKind.parse("divider") is BlockKind.DIVIDER
    assert BlockKind.CODE.label == "Code"
    assert len(SLASH_ORDER) == 7
    with pytest.raises(ValueError, match="Unknown block kind"):
        BlockKind.parse("image")


def test_block_kind_capability_flags() -> None:
    assert BlockKind.PARAGRAPH.supports_text
    assert BlockKind.CODE.supports_language
    assert not BlockKind.DIVIDER.supports_text
    assert BlockKind.TABLE.supports_items
    assert BlockKind.LIST.supports_items
    assert BlockKind.HEADING.supports_level
    assert not BlockKind.PARAGRAPH.supports_level
    assert not BlockKind.QUOTE.supports_items


def test_inline_mark_catalog_and_application() -> None:
    assert len(ALL_INLINE_MARKS) == 4
    assert InlineMark.parse("Bold") is InlineMark.BOLD
    assert InlineMark.BOLD.marker == "**"
    assert InlineMark.ITALIC.marker == "*"
    assert InlineMark.CODE.marker == "`"
    assert InlineMark.LINK.marker == "]"
    assert InlineMark.BOLD.apply("hello world", "world") == "hello **world**"
    assert InlineMark.ITALIC.apply("hello world", "hello") == "*hello* world"
    assert InlineMark.CODE.apply("run make", "make") == "run `make`"
    assert (
        InlineMark.LINK.apply("see docs", "docs", "https://example.test")
        == "see [docs](https://example.test)"
    )
    with pytest.raises(ValueError, match="selection not present"):
        InlineMark.BOLD.apply("text", "missing")
    with pytest.raises(ValueError, match="link mark requires"):
        InlineMark.LINK.apply("see docs", "docs")
    with pytest.raises(ValueError, match="Unknown inline mark"):
        InlineMark.parse("underline")


def test_block_op_catalog() -> None:
    assert len(ALL_BLOCK_OPS) == 4
    assert {item.value for item in ALL_BLOCK_OPS} == {
        "insert",
        "update",
        "delete",
        "move",
    }
    assert BlockOp.parse("INSERT") is BlockOp.INSERT
    assert BlockOp.MOVE.is_structural
    assert not BlockOp.UPDATE.is_structural
    with pytest.raises(ValueError, match="Unknown block operation"):
        BlockOp.parse("swap")


def test_validation_issue_round_trip() -> None:
    issue = ValidationIssue(
        "blocks[0].id", "block.duplicate_id", "duplicate", ValidationSeverity.WARNING
    )
    data = issue.to_dict()
    assert data["severity"] == "warning"
    assert ValidationIssue.from_dict(data) == issue
    assert ValidationIssue.from_dict({"path": "x", "code": "y", "message": "z"}).severity is (
        ValidationSeverity.ERROR
    )


def test_block_construction_and_defaults() -> None:
    block = make_block("b1", BlockKind.HEADING, "Title", level=3)
    assert block.id == "b1"
    assert block.kind is BlockKind.HEADING
    assert block.level == 3
    assert block.language == ""
    assert block.items == ()
    assert block.attrs == ()
    assert not block.is_empty
    assert block.word_count == 1
    assert Block("b2", BlockKind.DIVIDER).is_empty


def test_block_rejects_malformed_identity_and_shapes() -> None:
    with pytest.raises(ValueError, match="invalid block id"):
        Block("bad id!", BlockKind.PARAGRAPH)
    with pytest.raises(ValueError, match="invalid block id"):
        Block("", BlockKind.PARAGRAPH)
    with pytest.raises(TypeError, match="block kind must be"):
        Block("b1", "paragraph")
    with pytest.raises(TypeError, match="block text must be"):
        Block("b1", BlockKind.PARAGRAPH, 42)
    with pytest.raises(ValueError, match="block text exceeds"):
        Block("b1", BlockKind.PARAGRAPH, "x" * 20_001)
    with pytest.raises(TypeError, match="block level must be"):
        Block("b1", BlockKind.HEADING, "x", True)
    with pytest.raises(ValueError, match="block level must be between"):
        Block("b1", BlockKind.HEADING, "x", MAX_HEADING_LEVEL + 1)
    with pytest.raises(ValueError, match="block level must be between"):
        Block("b1", BlockKind.HEADING, "x", MIN_HEADING_LEVEL - 1)
    with pytest.raises(ValueError, match="block has more than"):
        Block("b1", BlockKind.LIST, items=tuple("x" for _ in range(501)))
    with pytest.raises(ValueError, match="block items must be bounded"):
        Block("b1", BlockKind.LIST, items=(1,))
    with pytest.raises(ValueError, match="block language must be"):
        Block("b1", BlockKind.CODE, language="x" * 61)


def test_attribute_validation_and_normalization() -> None:
    assert attr_pairs({"b": "2", "a": "1"}) == (("a", "1"), ("b", "2"))
    assert attr_pairs((("z", "9"), ("a", "1"))) == (("a", "1"), ("z", "9"))
    assert attr_pairs(None) == ()
    with pytest.raises(ValueError, match="strings to strings"):
        attr_pairs({1: "x"})
    with pytest.raises(ValueError, match="invalid attribute key"):
        attr_pairs({"Bad Key": "x"})
    with pytest.raises(ValueError, match="attribute value too long"):
        attr_pairs({"note": "x" * 501})
    with pytest.raises(ValueError, match="more than 24 attributes"):
        attr_pairs({f"k{i}": "v" for i in range(25)})


def test_block_immutable_updates_preserve_identity() -> None:
    original = make_block("b1", BlockKind.HEADING, "Old", level=1)
    assert original.with_text("New").text == "New"
    assert original.with_level(4).level == 4
    assert original.with_language("markdown").language == "markdown"
    assert original.with_items(("a",)).items == ("a",)
    assert original.with_attrs({"style": "ordered"}).attr("style") == "ordered"
    assert original.text == "Old"
    assert original.attr("missing", "default") == "default"
    assert original.attrs_dict() == {}


def test_block_dict_round_trip() -> None:
    block = make_block(
        "b1",
        BlockKind.TABLE,
        items=("a|1",),
        attrs={"header": "Name|Value"},
    )
    data = block.to_dict()
    assert data["kind"] == "table"
    assert data["items"] == ["a|1"]
    assert Block.from_dict(data) == block
    assert Block.from_dict({**data, "attrs": [("header", "Name|Value")]}) == block
    with pytest.raises(ValueError, match="block items must be a list"):
        Block.from_dict({**data, "items": "a|1"})


def test_block_checksum_is_stable_and_content_sensitive() -> None:
    block = make_block("b1", text="hello")
    assert block.checksum() == make_block("b1", text="hello").checksum()
    assert block.checksum() != make_block("b1", text="hello!").checksum()
    assert len(block.checksum()) == 24


def test_document_identity_lookup_and_immutability() -> None:
    document = sample_document()
    assert len(document.blocks) == 7
    assert document.block_ids == tuple(block.id for block in document.blocks)
    assert document.get("b3") is document.blocks[2]
    assert document.get("missing") is None
    assert document.index_of("b7") == 6
    assert document.index_of("missing") == -1
    assert document.word_count > 5
    assert document.with_title("Renamed").title == "Renamed"
    assert document.title == "All block kinds"
    assert len(document.with_blocks(document.blocks[:2]).blocks) == 2


def test_document_dict_round_trip_and_checksum() -> None:
    document = sample_document()
    data = document.to_dict()
    assert data["id"] == "doc1"
    assert len(data["blocks"]) == 7
    assert BlockDocument.from_dict(data) == document
    assert document.checksum() == BlockDocument.from_dict(data).checksum()
    assert document.checksum() != document.with_title("Other").checksum()
    with pytest.raises(ValueError, match="document blocks must be a list"):
        BlockDocument.from_dict({"id": "d", "title": "t", "blocks": "bad"})


def test_document_rejects_malformed_shapes() -> None:
    with pytest.raises(ValueError, match="invalid document id"):
        BlockDocument("bad id", "title")
    with pytest.raises(ValueError, match="document title must be"):
        BlockDocument("d1", "x" * 241)
    with pytest.raises(TypeError, match="document blocks must be"):
        BlockDocument("d1", "title", ("not a block",))
    with pytest.raises(ValueError, match="more than 2000 blocks"):
        BlockDocument("d1", "title", tuple(make_block(f"b{i}") for i in range(2001)))


def test_edit_operation_validation_and_round_trip() -> None:
    block = make_block("b1", text="hello")
    insert = EditOperation(BlockOp.INSERT, "b1", index=2, block=block, note="add")
    assert insert.label == "insert:b1"
    assert EditOperation.from_dict(insert.to_dict()) == insert
    delete_dict = EditOperation(BlockOp.DELETE, "b1", index=1).to_dict()
    assert "block" not in delete_dict
    move = EditOperation(BlockOp.MOVE, "b1", index=0, target_index=3)
    assert EditOperation.from_dict(move.to_dict()) == move
    with pytest.raises(TypeError, match="operation must be a BlockOp"):
        EditOperation("insert", "b1", block=block)
    with pytest.raises(ValueError, match="invalid operation block id"):
        EditOperation(BlockOp.DELETE, "bad id!")
    with pytest.raises(ValueError, match="index must be non-negative"):
        EditOperation(BlockOp.DELETE, "b1", index=-1)
    with pytest.raises(ValueError, match="target index must be non-negative"):
        EditOperation(BlockOp.MOVE, "b1", target_index=-1)


def test_edit_operation_requires_consistent_payload() -> None:
    block = make_block("b1")
    with pytest.raises(ValueError, match="insert operation requires a block"):
        EditOperation(BlockOp.INSERT, "b1")
    with pytest.raises(ValueError, match="update operation requires a block"):
        EditOperation(BlockOp.UPDATE, "b1")
    with pytest.raises(ValueError, match="delete operation must not carry"):
        EditOperation(BlockOp.DELETE, "b1", block=block)
    with pytest.raises(ValueError, match="move operation requires"):
        EditOperation(BlockOp.MOVE, "b1")
    with pytest.raises(ValueError, match="note exceeds"):
        EditOperation(BlockOp.DELETE, "b1", note="x" * 241)


def test_factories_use_injected_identifiers() -> None:
    factory = id_factory("b7", "d9")
    block = new_block("paragraph", "hi", id_factory=factory)
    document = new_document("title", (block,), id_factory=factory)
    assert block.id == "b7"
    assert document.id == "d9"
    assert new_block(BlockKind.LIST, id_factory=factory).kind is BlockKind.LIST


def test_text_normalization_collapses_blank_runs() -> None:
    assert normalize_text("  a  \r\n\r\n\r\nb\n\n") == "  a\n\nb"
    assert normalize_text("x\n\n\n\ny") == "x\n\ny"
    assert normalize_text("") == ""


def test_canonical_checksum_ignores_key_order() -> None:
    assert canonical_checksum({"a": 1, "b": 2}) == canonical_checksum({"b": 2, "a": 1})
