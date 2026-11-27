"""Tests for the codec, differ, autosave manager, and validator."""

from __future__ import annotations

from dataclasses import replace
from datetime import timezone

import pytest
from tests.v4_blocks_pro.fixtures import (
    clock_factory,
    id_factory,
    make_block,
    make_document,
    sample_blocks,
    sample_document,
    simple_document,
)

from redscribe.v4.blocks_pro.service import (
    AutosaveManager,
    BlockDiff,
    BlockValidator,
    CodecError,
    DiffError,
    DocumentInvalidError,
    MarkdownCodec,
    SnapshotError,
    apply_mark,
    markdown_summary,
    parse_timestamp,
    strip_markdown,
)
from redscribe.v4.blocks_pro.types import (
    BlockDocument,
    BlockKind,
    BlockOp,
    EditOperation,
    InlineMark,
    ValidationSeverity,
)


def codec() -> MarkdownCodec:
    return MarkdownCodec(id_factory=id_factory(*(f"x{i}" for i in range(40))))


def test_codec_encodes_all_block_kinds() -> None:
    markdown = codec().encode(sample_document())
    assert markdown.startswith("# All block kinds\n")
    assert "<!-- block:b1 -->" in markdown
    assert "## Section heading" in markdown
    assert "```python\nprint('hello')\n```" in markdown
    assert "- first\n- second" in markdown
    assert "> Quoted line one\n> Quoted line two" in markdown
    assert "| Name | Value |\n| --- | --- |" in markdown
    assert markdown.rstrip().endswith("---")


def test_codec_round_trips_every_block_kind() -> None:
    for block in sample_blocks():
        document = make_document("d1", "Kinds", (block,))
        restored = codec().round_trip(document)
        assert restored == document
        assert restored.blocks[0] == block


def test_codec_round_trips_full_document_with_ids() -> None:
    document = sample_document()
    restored = codec().round_trip(document)
    assert restored == document
    assert restored.block_ids == document.block_ids
    assert restored.checksum() == document.checksum()


def test_codec_without_annotations_generates_fresh_ids() -> None:
    plain = codec().with_annotations(False)
    markdown = plain.encode(make_document("d1", "T", (make_block("b1", text="hello"),)))
    assert "<!--" not in markdown
    decoded = plain.decode(markdown)
    assert decoded.blocks[0].id.startswith("x")
    assert decoded.blocks[0].text == "hello"


def test_codec_decode_preserves_external_document_id() -> None:
    markdown = codec().encode(sample_document())
    decoded = codec().decode_with_id(markdown, "external-id")
    assert decoded.id == "external-id"
    assert decoded.title == "All block kinds"
    assert decoded.block_ids == tuple(block.id for block in sample_blocks())


def test_codec_decodes_unannotated_markdown_with_injected_ids() -> None:
    markdown = "# Notes\n\nfirst paragraph\n\n## Heading\n\n- one\n- two\n"
    decoded = codec().decode(markdown)
    assert decoded.title == "Notes"
    assert [block.kind for block in decoded.blocks] == [
        BlockKind.PARAGRAPH,
        BlockKind.HEADING,
        BlockKind.LIST,
    ]
    assert decoded.blocks[2].attr("style") == "bullet"
    assert decoded.blocks[0].id == "x0"


def test_codec_decodes_task_and_ordered_lists() -> None:
    markdown = "# Tasks\n\n- [x] done\n- [ ] todo\n\n1. first\n2. second\n"
    decoded = codec().decode(markdown)
    assert decoded.blocks[0].attr("style") == "task"
    assert decoded.blocks[0].items == ("[x] done", "[ ] todo")
    assert decoded.blocks[1].attr("style") == "ordered"
    assert decoded.blocks[1].items == ("first", "second")


def test_codec_decodes_divider_variants_and_code_without_language() -> None:
    decoded = codec().decode("# T\n\n***\n\n```\nraw\n```\n")
    assert decoded.blocks[0].kind is BlockKind.DIVIDER
    assert decoded.blocks[1].kind is BlockKind.CODE
    assert decoded.blocks[1].language == "text"
    assert decoded.blocks[1].text == "raw"


def test_codec_rejects_malformed_markdown() -> None:
    with pytest.raises(CodecError, match="markdown must be a string"):
        codec().decode(42)
    with pytest.raises(CodecError, match="unterminated fenced"):
        codec().decode("# T\n\n```python\nnever closed")
    with pytest.raises(CodecError, match="table must contain"):
        codec().decode("# T\n\n| A | B |\nsome text\n")


def test_inline_mark_helpers() -> None:
    assert apply_mark("hello world", "bold", "world") == "hello **world**"
    assert apply_mark("hello world", InlineMark.ITALIC, "hello") == "*hello* world"
    with pytest.raises(ValueError, match="selection not present"):
        apply_mark("text", "code", "missing")
    assert strip_markdown("**bold** and `code` and [link](http://x)") == "bold and code and link"
    assert markdown_summary("# A\n\ntext\n\n```py\nx\n```\n") == {
        "lines": 8,
        "blank": 3,
        "headings": 1,
        "fences": 2,
    }


def test_parse_timestamp_accepts_z_and_offsets() -> None:
    parsed = parse_timestamp("2026-01-02T03:04:05.000Z")
    assert parsed.tzinfo is timezone.utc
    assert parse_timestamp("2026-01-02T03:04:05+00:00") == parsed
    assert parse_timestamp("2026-01-02T03:04:05") == parsed.replace(microsecond=0)
    with pytest.raises(ValueError, match="empty timestamp"):
        parse_timestamp("")
    with pytest.raises(ValueError):
        parse_timestamp("not a date")


def make_diff_document(ids: tuple[str, ...], texts: tuple[str, ...] | None = None) -> BlockDocument:
    values = texts or ids
    return make_document(
        "d1",
        "Diff",
        tuple(
            make_block(identifier, text=text) for identifier, text in zip(ids, values, strict=True)
        ),
    )


def test_diff_detects_pure_insert() -> None:
    left = make_diff_document(("a", "b", "c"))
    right = make_diff_document(("a", "x", "b", "c"))
    operations = BlockDiff().compare(left, right)
    kinds = [item.op for item in operations]
    assert kinds.count(BlockOp.INSERT) == 1
    assert [item.block_id for item in operations if item.op is BlockOp.INSERT] == ["x"]
    assert BlockDiff().apply(left, operations) == right


def test_diff_detects_pure_delete() -> None:
    left = make_diff_document(("a", "b", "c"))
    right = make_diff_document(("a", "c"))
    operations = BlockDiff().compare(left, right)
    assert [item.op for item in operations] == [BlockOp.DELETE]
    assert operations[0].block_id == "b"
    assert BlockDiff().apply(left, operations) == right


def test_diff_detects_update_when_content_changes() -> None:
    left = make_diff_document(("a", "b", "c"))
    right = make_diff_document(("a", "b", "c"), ("a", "B!", "c"))
    operations = BlockDiff().compare(left, right)
    assert [item.op for item in operations] == [BlockOp.UPDATE]
    assert operations[0].block is not None
    assert operations[0].block.text == "B!"
    assert BlockDiff().apply(left, operations) == right


def test_diff_detects_move() -> None:
    left = make_diff_document(("a", "b", "c"))
    right = make_diff_document(("c", "a", "b"))
    operations = BlockDiff().compare(left, right)
    assert [item.op for item in operations] == [BlockOp.MOVE]
    assert operations[0].block_id == "c"
    assert operations[0].target_index == 0
    assert BlockDiff().apply(left, operations) == right


def test_diff_handles_mixed_changes_and_replays_them() -> None:
    left = make_diff_document(("a", "b", "c"))
    right = make_diff_document(("x", "c", "b"), ("X", "C!", "b"))
    differ = BlockDiff()
    operations = differ.compare(left, right)
    summary = differ.summary(operations)
    assert summary["insert"] >= 1
    assert summary["delete"] >= 1
    assert summary["update"] >= 1
    assert sum(summary.values()) == len(operations)
    assert differ.apply(left, operations) == right


def test_diff_line_diff_and_summary() -> None:
    differ = BlockDiff()
    deltas = differ.line_diff("a\nb\nc\n", "a\nx\nc\n")
    assert [item.op for item in deltas] == ["remove", "add"]
    assert deltas[0].text == "b"
    assert deltas[1].text == "x"
    assert all(item.left_index >= 0 or item.right_index >= 0 for item in deltas)
    assert deltas[0].to_dict()["op"] == "remove"
    assert differ.summary(()) == {"insert": 0, "update": 0, "delete": 0, "move": 0}


def test_diff_rejects_duplicate_ids_and_bad_replay() -> None:
    differ = BlockDiff()
    duplicated = make_document(
        "d1",
        "Dupes",
        (make_block("a", text="one"), make_block("a", text="two")),
    )
    with pytest.raises(DiffError, match="duplicate block id"):
        differ.compare(duplicated, duplicated)
    left = make_diff_document(("a", "b"))
    with pytest.raises(DiffError, match="cannot delete"):
        differ.apply(
            left,
            (EditOperation(BlockOp.DELETE, "missing", index=0),),
        )
    with pytest.raises(DiffError, match="cannot move missing"):
        differ.apply(left, (EditOperation(BlockOp.MOVE, "x", index=0, target_index=1),))
    with pytest.raises(DiffError, match="cannot update missing"):
        differ.apply(
            left,
            (EditOperation(BlockOp.UPDATE, "x", index=0, block=make_block("x")),),
        )


def test_diff_ignore_level_option() -> None:
    left = make_document(
        "d1",
        "Headings",
        (make_block("h1", BlockKind.HEADING, "Title", level=1),),
    )
    right = make_document(
        "d1",
        "Headings",
        (make_block("h1", BlockKind.HEADING, "Title", level=3),),
    )
    assert BlockDiff().compare(left, right)
    assert BlockDiff(ignore_level=True).compare(left, right) == ()


def test_autosave_creates_snapshots_with_sequential_revisions() -> None:
    manager = AutosaveManager(
        id_factory=id_factory("s1", "s2"),
        clock=clock_factory("2026-01-01T00:00:00.000Z", "2026-01-01T01:00:00.000Z"),
    )
    document = simple_document()
    first = manager.create(document, "manual")
    second = manager.create(document.with_title("Renamed"), "autosave")
    assert first.revision == 1
    assert second.revision == 2
    assert first.id == "s1"
    assert second.created_at == "2026-01-01T01:00:00.000Z"
    assert manager.count() == 2
    assert manager.latest("doc1") == second
    assert manager.list_for("missing") == ()
    assert manager.latest("missing") is None


def test_autosave_verify_restore_and_staleness() -> None:
    manager = AutosaveManager(
        id_factory=id_factory("s1"), clock=clock_factory("2026-01-01T00:00:00Z")
    )
    document = simple_document()
    snapshot = manager.create(document)
    assert manager.verify(snapshot)
    assert manager.restore(snapshot, snapshot.checksum) == document
    with pytest.raises(SnapshotError, match="stale"):
        manager.restore(snapshot, "other-checksum")
    tampered = replace(snapshot, checksum="deadbeef")
    assert not manager.verify(tampered)
    with pytest.raises(SnapshotError, match="does not match"):
        manager.restore(tampered)


def test_autosave_snapshot_dict_round_trip() -> None:
    manager = AutosaveManager(
        id_factory=id_factory("s1"), clock=clock_factory("2026-01-01T00:00:00Z")
    )
    snapshot = manager.create(simple_document(), "checkpoint")
    restored = type(snapshot).from_dict(snapshot.to_dict())
    assert restored == snapshot
    with pytest.raises(SnapshotError, match="must be a mapping"):
        type(snapshot).from_dict({"document": "not a dict"})


def test_autosave_prunes_by_age_and_count() -> None:
    clock = clock_factory("2026-01-10T00:00:00Z")
    manager = AutosaveManager(id_factory=id_factory(*(f"s{i}" for i in range(8))), clock=clock)
    document = simple_document()
    timestamps = [
        "2026-01-09T00:00:00Z",
        "2026-01-09T01:00:00Z",
        "2026-01-09T02:00:00Z",
        "2026-01-09T03:00:00Z",
    ]
    for stamp in timestamps:
        snapshot = manager.create(document)
        object.__setattr__(snapshot, "created_at", stamp)
    kept, removed = manager.prune(
        manager.list_for("doc1"),
        max_count=2,
        max_age_hours=48,
        now="2026-01-10T00:00:00Z",
    )
    assert len(kept) == 2
    assert len(removed) == 2
    assert {item.created_at for item in removed} == {
        "2026-01-09T00:00:00Z",
        "2026-01-09T01:00:00Z",
    }


def test_autosave_prune_all_remove_and_clear() -> None:
    manager = AutosaveManager(
        id_factory=id_factory(*(f"s{i}" for i in range(6))),
        clock=clock_factory("2026-01-01T00:00:00Z"),
    )
    manager.create(simple_document())
    manager.create(make_document("doc2", "Two"))
    kept, removed = manager.prune_all(max_count=5, max_age_hours=1, now="2026-01-01T00:30:00Z")
    assert len(kept) + len(removed) == 2
    assert manager.remove("s1") or manager.remove("s2")
    assert manager.count() == 1
    manager.clear()
    assert manager.count() == 0
    manager.create(simple_document())
    manager.clear("doc1")
    assert manager.count() == 0


def test_autosave_rejects_bad_parameters_and_bad_timestamps() -> None:
    manager = AutosaveManager(
        id_factory=id_factory("s1"), clock=clock_factory("2026-01-01T00:00:00Z")
    )
    with pytest.raises(SnapshotError, match="reason must be"):
        manager.create(simple_document(), "")
    with pytest.raises(SnapshotError, match="max_count must be"):
        manager.prune((), max_count=0)
    with pytest.raises(SnapshotError, match="max_age_hours must be"):
        manager.prune((), max_age_hours=-1)
    snapshot = manager.create(simple_document())
    bad = replace(snapshot, created_at="invalid")
    kept, removed = manager.prune((bad,), now="2026-01-01T00:00:00Z")
    assert kept == []
    assert removed == [bad]


def test_validator_accepts_well_formed_document() -> None:
    document = sample_document()
    validator = BlockValidator()
    assert validator.validate(document) == ()
    assert validator.is_valid(document)
    validator.require_valid(document)


def test_validator_reports_duplicate_ids_and_empty_title() -> None:
    blocks = (make_block("a"), make_block("a"))
    issues = BlockValidator().validate(make_document("d1", " ", blocks))
    codes = {issue.code for issue in issues}
    assert "title.empty" in codes
    assert "block.duplicate_id" in codes
    with pytest.raises(DocumentInvalidError):
        BlockValidator().require_valid(make_document("d1", " ", blocks))


def test_validator_checks_headings_codes_lists_tables_and_dividers() -> None:
    blocks = (
        make_block("h", BlockKind.HEADING, "", level=6),
        make_block("c", BlockKind.CODE, "x", language="brainfuck"),
        make_block("l", BlockKind.LIST, items=(), attrs={"style": "magic"}),
        make_block("t", BlockKind.TABLE, items=("one",), attrs={"header": "A|B"}),
        make_block("d", BlockKind.DIVIDER, "unexpected"),
        make_block("p", BlockKind.PARAGRAPH, "a\n\nb"),
    )
    issues = BlockValidator(max_heading_level=4).validate(make_document("d1", "T", blocks))
    codes = {issue.code for issue in issues}
    assert {
        "heading.level",
        "heading.empty",
        "code.language_unknown",
        "list.empty",
        "list.style",
        "table.width",
        "divider.content",
        "paragraph.break",
    } <= codes
    assert any(issue.severity is ValidationSeverity.WARNING for issue in issues)
    assert not BlockValidator().is_valid(make_document("d1", "T", blocks))


def test_validator_table_requires_header() -> None:
    issue_codes = {
        issue.code
        for issue in BlockValidator().validate(
            make_document("d1", "T", (make_block("t", BlockKind.TABLE, items=("a",)),))
        )
    }
    assert "table.header" in issue_codes


def test_validator_rejects_illegal_max_heading_level() -> None:
    with pytest.raises(ValueError, match="legal heading level"):
        BlockValidator(max_heading_level=9)


def test_validator_checks_operations_and_conflicts() -> None:
    document = simple_document()
    validator = BlockValidator()
    insert = EditOperation(BlockOp.INSERT, "x", index=99, block=make_block("x"))
    duplicate = EditOperation(BlockOp.INSERT, "a", index=0, block=make_block("a"))
    delete = EditOperation(BlockOp.DELETE, "missing", index=0)
    move = EditOperation(BlockOp.MOVE, "a", index=0, target_index=99)
    assert {issue.code for issue in validator.validate_operation(insert, document)} == {
        "operation.index"
    }
    assert "operation.duplicate" in {
        issue.code for issue in validator.validate_operation(duplicate, document)
    }
    assert "operation.missing" in {
        issue.code for issue in validator.validate_operation(delete, document)
    }
    assert "operation.target" in {
        issue.code for issue in validator.validate_operation(move, document)
    }
    conflicts = validator.validate_operations(
        (
            EditOperation(BlockOp.DELETE, "a", index=0),
            EditOperation(BlockOp.MOVE, "a", index=0, target_index=1),
        ),
        document,
    )
    assert any(issue.code == "operation.conflict" for issue in conflicts)
    assert validator.validate_operations((), document) == ()


def test_validator_accepts_well_formed_operations() -> None:
    document = simple_document()
    validator = BlockValidator()
    update = EditOperation(
        BlockOp.UPDATE,
        "a",
        index=0,
        block=make_block("a", text="replacement"),
    )
    insert = EditOperation(BlockOp.INSERT, "x", index=3, block=make_block("x"))
    assert validator.validate_operation(update, document) == ()
    assert validator.validate_operation(insert, document) == ()
    assert validator.validate_operations((update, insert), document) == ()
