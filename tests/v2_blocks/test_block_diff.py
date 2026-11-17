from __future__ import annotations

import pytest

from redscribe.v2.blocks.autosave import (
    AutosaveBatch,
    AutosaveCoalescer,
    batch_for_document,
    coalesce_batches,
    next_flush_delay,
    with_label,
)
from redscribe.v2.blocks.diff import (
    BlockPatch,
    PatchEntry,
    PatchError,
    PatchOperation,
    apply_patch,
    block_signature,
    diff_documents,
    make_patch,
    merge_entries,
    patch_from_diff,
    patch_summary,
)
from redscribe.v2.blocks.model import make_block, make_document
from redscribe.v2.blocks.revisions import (
    RevisionConflictError,
    RevisionManager,
    decode_token,
    encode_token,
    issue_token,
    token_is_current,
    token_revisions,
    verify_token,
)
from redscribe.v2.blocks.types import MentionKind


def _block(block_id: str, text: str = "text") -> object:
    return make_block("paragraph", text, block_id=block_id)


def _insert(block_id: str, text: str = "text", index: int = 0) -> PatchEntry:
    return PatchEntry(
        PatchOperation.INSERT,
        block_id,
        block=make_block("paragraph", text, block_id=block_id),
        index=index,
    )


def test_diff_reports_add_and_remove() -> None:
    first = make_block("paragraph", "one", block_id="b1")
    second = make_block("paragraph", "two", block_id="b2")
    left = make_document("doc-1", blocks=[first])
    right = make_document("doc-1", blocks=[first, second])
    added = diff_documents(left, right)
    assert added.changed
    assert added.counts()["add"] == 1
    assert added.entries[0].block_id == "b2"
    assert added.entries[0].index == 1
    assert added.entries[0].block is not None
    assert added.block_ids() == ["b2"]
    removed = diff_documents(right, left)
    assert removed.counts()["remove"] == 1
    assert removed.entries[0].block_id == "b2"


def test_diff_reports_content_change_as_replace() -> None:
    left = make_document(
        "doc-1",
        blocks=[make_block("paragraph", "old", block_id="b1")],
    )
    right = make_document(
        "doc-1",
        blocks=[make_block("paragraph", "new", block_id="b1")],
    )
    result = diff_documents(left, right)
    assert result.counts()["replace"] == 1
    assert result.counts()["remove"] == 0
    assert result.entries[0].previous_index == 0
    assert result.entries[0].block is not None
    assert result.entries[0].block.text == "new"


def test_diff_reports_move_when_signature_is_unchanged() -> None:
    first = make_block("paragraph", "one", block_id="b1")
    second = make_block("paragraph", "two", block_id="b2")
    left = make_document("doc-1", blocks=[first, second])
    right = make_document("doc-1", blocks=[second, first])
    result = diff_documents(left, right)
    assert result.counts() == {"add": 0, "remove": 0, "replace": 0, "move": 1}
    assert result.entries[0].block_id == "b2"
    assert result.entries[0].previous_index == 1
    assert result.entries[0].index == 0


def test_diff_reports_id_change_as_replace() -> None:
    left = make_document("doc-1", blocks=[make_block("paragraph", "same", block_id="old")])
    right = make_document("doc-1", blocks=[make_block("paragraph", "same", block_id="new")])
    result = diff_documents(left, right)
    assert result.counts()["replace"] == 1
    assert result.entries[0].block_id == "old"
    assert result.entries[0].block is not None
    assert result.entries[0].block.id == "new"


def test_patch_from_diff_applies_content_changes() -> None:
    left = make_document(
        "doc-1",
        blocks=[
            make_block("paragraph", "old", block_id="b1"),
            make_block("paragraph", "keep", block_id="b2"),
        ],
    )
    right = left.with_blocks(
        [
            make_block("paragraph", "new", block_id="b1"),
            left.blocks[1],
        ]
    )
    patch = patch_from_diff(left, right)
    assert [entry.operation for entry in patch.entries] == [PatchOperation.UPDATE]
    applied = apply_patch(left, patch)
    assert applied.blocks[0].text == "new"
    assert applied.block_ids == right.block_ids
    assert applied.revision == 1


def test_patch_from_diff_applies_insert_delete_and_move() -> None:
    first = make_block("paragraph", "one", block_id="b1")
    second = make_block("paragraph", "two", block_id="b2")
    third = make_block("paragraph", "three", block_id="b3")
    left = make_document("doc-1", blocks=[first, second])
    right = make_document("doc-1", blocks=[second, third])
    patch = patch_from_diff(left, right)
    assert {entry.operation for entry in patch.entries} <= {
        PatchOperation.DELETE,
        PatchOperation.INSERT,
        PatchOperation.MOVE,
    }
    applied = apply_patch(left, patch)
    assert [block_signature(block) for block in applied.blocks] == [
        block_signature(block) for block in right.blocks
    ]


def test_invert_patch_restores_original_document() -> None:
    from redscribe.v2.blocks.diff import invert_patch

    left = make_document("doc-1", blocks=[make_block("paragraph", "old", block_id="b1")])
    right = make_document(
        "doc-1", blocks=[make_block("paragraph", "new", block_id="b1")]
    ).advanced()
    forward = patch_from_diff(left, right)
    backward = invert_patch(left, right)
    assert apply_patch(apply_patch(left, forward), backward).blocks == left.blocks


def test_apply_patch_checks_revision_and_identity() -> None:
    document = make_document("doc-1", blocks=[make_block("paragraph", "body", block_id="b1")])
    patch = make_patch(document, [PatchEntry(PatchOperation.DELETE, "b1")])
    wrong_id = make_patch(
        make_document("other", blocks=document.blocks),
        [PatchEntry(PatchOperation.DELETE, "b1")],
    )
    with pytest.raises(PatchError, match="different document"):
        apply_patch(document, wrong_id)
    stale = make_patch(document.advanced(), [PatchEntry(PatchOperation.DELETE, "b1")])
    with pytest.raises(PatchError, match="Revision conflict"):
        apply_patch(document, stale)
    assert apply_patch(document, patch, require_revision=False).blocks == ()


def test_apply_patch_rejects_invalid_operations() -> None:
    document = make_document("doc-1", blocks=[make_block("paragraph", "body", block_id="b1")])
    cases = [
        [PatchEntry(PatchOperation.INSERT, "b2")],
        [PatchEntry(PatchOperation.UPDATE, "b1")],
        [PatchEntry(PatchOperation.DELETE, "missing")],
        [PatchEntry(PatchOperation.INSERT, "b1", block=_block("b1"))],
    ]
    for entries in cases:
        with pytest.raises(PatchError):
            apply_patch(document, make_patch(document, entries))


def test_patch_dict_decoding_validates_shape() -> None:
    payload = {
        "document_id": "doc-1",
        "base_revision": 3,
        "label": "dict",
        "entries": [
            {
                "operation": "insert",
                "block_id": "b1",
                "block": make_block("paragraph", "body", block_id="b1").as_dict(),
                "index": 0,
            }
        ],
    }
    patch = BlockPatch.from_dict(payload)
    assert patch.document_id == "doc-1"
    assert patch.base_revision == 3
    assert patch.label == "dict"
    assert patch.as_dict()["entries"][0]["operation"] == "insert"
    with pytest.raises(PatchError, match="Unknown patch operation"):
        PatchEntry.from_dict({"operation": "explode", "block_id": "b1"})
    with pytest.raises(PatchError, match="integer"):
        BlockPatch.from_dict({"base_revision": "3"})
    with pytest.raises(PatchError, match="list"):
        BlockPatch.from_dict({"entries": "nope"})


def test_patch_summary_counts_operations() -> None:
    patch = make_patch(
        make_document("doc-1", blocks=[_block("b1")]),
        [
            PatchEntry(PatchOperation.DELETE, "b1"),
            _insert("b2"),
            PatchEntry(PatchOperation.MOVE, "b2", index=0),
        ],
    )
    assert patch_summary(patch) == {"insert": 1, "update": 0, "delete": 1, "move": 1}


def test_merge_entries_coalesces_delete_insert_update_and_move() -> None:
    block = make_block("paragraph", "new", block_id="b1")
    replacement = merge_entries(
        [
            PatchEntry(PatchOperation.DELETE, "b1", previous_index=2),
            PatchEntry(PatchOperation.INSERT, "b1", block=block, index=0),
        ]
    )
    assert len(replacement) == 1
    assert replacement[0].operation is PatchOperation.UPDATE
    assert replacement[0].index == 0
    assert replacement[0].previous_index == 2

    latest = block.with_changes(text="latest")
    inserted = merge_entries(
        [
            _insert("b2", "first", 1),
            PatchEntry(PatchOperation.UPDATE, "b2", block=latest),
        ]
    )
    assert inserted[0].operation is PatchOperation.INSERT
    assert inserted[0].index == 1
    assert inserted[0].block is not None
    assert inserted[0].block.text == "latest"

    moved = merge_entries(
        [
            _insert("b3"),
            PatchEntry(PatchOperation.MOVE, "b3", index=4),
        ]
    )
    assert len(moved) == 1
    assert moved[0].operation is PatchOperation.MOVE
    assert moved[0].index == 4


def test_revision_token_roundtrip_and_verification() -> None:
    document = make_document("doc-1", blocks=[make_block("paragraph", "body", block_id="b1")])
    token = issue_token(document)
    encoded = encode_token(token)
    assert encoded.startswith("rev1.")
    assert decode_token(encoded) == token
    verify_token(document, encoded)
    assert token_is_current(document, token)
    changed = document.with_blocks([make_block("paragraph", "different", block_id="b1")]).advanced()
    with pytest.raises(RevisionConflictError, match="stale revision"):
        verify_token(changed, token)
    assert not token_is_current(changed, token)
    with pytest.raises(ValueError, match="Malformed revision token"):
        decode_token("rev1.not-base64")


def test_revision_tokens_bind_secret_and_document() -> None:
    document = make_document("doc-1", blocks=[make_block("paragraph", "body", block_id="b1")])
    token = issue_token(document, secret="top-secret")
    with pytest.raises(RevisionConflictError, match="content digest mismatch"):
        verify_token(document, token)
    verify_token(document, token, secret="top-secret")
    other = make_document("doc-2", blocks=document.blocks)
    with pytest.raises(RevisionConflictError, match="document id mismatch"):
        verify_token(other, token, secret="top-secret")


def test_revision_manager_advances_and_bounds_history() -> None:
    manager = RevisionManager(history_size=2)
    document = make_document("doc-1", blocks=[make_block("paragraph", "body", block_id="b1")])
    token = manager.issue(document)
    advanced = manager.advance(document, token)
    assert advanced.revision == 1
    assert len(manager.history) == 2
    manager.issue(advanced.advanced())
    assert len(manager.history) == 2
    assert token_revisions(manager.history) == [1, 2]
    explicit = manager.set_revision(document, 9)
    assert explicit.revision == 9
    manager.clear()
    assert manager.history == ()


def test_revision_conflict_as_dict_is_transport_ready() -> None:
    error = RevisionConflictError(2, 5, document_id="doc-1", reason="stale revision")
    payload = error.as_dict()
    assert payload["code"] == "revision_conflict"
    assert payload["expected"] == 2
    assert payload["actual"] == 5
    assert payload["document_id"] == "doc-1"
    assert payload["reason"] == "stale revision"


def test_autosave_coalescer_queues_due_and_flushes() -> None:
    clock = [0.0]
    coalescer = AutosaveCoalescer(interval_ms=100, max_wait_ms=300, clock=lambda: clock[0])
    document = make_document("doc-1", blocks=[_block("b1")])
    assert coalescer.record(document, [_insert("b2")]) is None
    assert coalescer.record(document, [_insert("b3")]) is None
    assert coalescer.pending[0].size == 2
    assert coalescer.pending[0].merged_from == 2
    assert coalescer.has_pending("doc-1")
    assert not coalescer.has_pending("other")
    assert coalescer.due(at_ms=50) == ()
    due = coalescer.due(at_ms=150)
    assert len(due) == 1
    assert due[0].size == 2
    clock[0] = 150
    flushed = coalescer.flush()
    assert len(flushed) == 1
    assert not coalescer.has_pending()


def test_autosave_max_wait_returns_batch_immediately() -> None:
    clock = [0.0]
    coalescer = AutosaveCoalescer(interval_ms=100, max_wait_ms=200, clock=lambda: clock[0])
    document = make_document("doc-1", blocks=[_block("b1")])
    coalescer.record(document, [_insert("b2")])
    clock[0] = 250
    batch = coalescer.record(document, [_insert("b3")])
    assert batch is not None
    assert batch.size == 2
    assert batch.merged_from == 2
    assert batch.age_ms == 250
    assert not coalescer.has_pending("doc-1")


def test_autosave_revision_change_resets_bucket() -> None:
    coalescer = AutosaveCoalescer(interval_ms=100, max_wait_ms=500, clock=lambda: 0.0)
    first = make_document("doc-1", blocks=[_block("b1")])
    second = first.advanced()
    coalescer.record(first, [_insert("b2")], label="first")
    coalescer.record(second, [_insert("b3")], label="second")
    pending = coalescer.pending[0]
    assert pending.base_revision == 1
    assert pending.size == 1
    assert pending.merged_from == 1
    assert pending.label == "second"


def test_autosave_acknowledge_cancel_and_flush_all() -> None:
    coalescer = AutosaveCoalescer(clock=lambda: 0.0)
    document = make_document("doc-1", blocks=[_block("b1")])
    coalescer.record(document, [_insert("b2")], token="rev")
    assert coalescer.acknowledge("doc-1", -1) is False
    assert coalescer.acknowledge("doc-1", 0) is True
    assert not coalescer.has_pending()
    coalescer.record(document, [_insert("b3")])
    assert coalescer.flush_document("doc-1") is not None
    assert coalescer.flush_document("missing") is None
    coalescer.record(document, [_insert("b4")])
    assert len(coalescer.flush_all()) == 1
    coalescer.record(document, [_insert("b5")])
    assert coalescer.cancel("doc-1") is True
    assert coalescer.cancel("doc-1") is False
    coalescer.record(document, [_insert("b6")])
    coalescer.clear()
    assert not coalescer.has_pending()


def test_autosave_state_and_delay_reporting() -> None:
    coalescer = AutosaveCoalescer(interval_ms=100, max_wait_ms=500, clock=lambda: 0.0)
    document = make_document("doc-1", blocks=[_block("b1")])
    coalescer.record(document, [_insert("b2")], label="edit")
    state = coalescer.state()
    assert state["pending"] == 1
    assert state["document_ids"] == ["doc-1"]
    assert state["operations"] == 1
    assert state["merged_edits"] == 1
    assert state["next_flush_ms"] == 100
    assert next_flush_delay(state) == 101
    assert next_flush_delay({"next_flush_ms": -2}) == 0
    assert next_flush_delay({}) == 1


def test_coalesce_batches_merges_by_document() -> None:
    first = AutosaveBatch("doc-1", 0, (_insert("b2"),), 1, 0.0, 0.0, token="rev", label="one")
    second = AutosaveBatch("doc-1", 0, (_insert("b3"),), 2, 10.0, 10.0, token="", label="two")
    third = AutosaveBatch("doc-2", 0, (), 1, 5.0, 5.0)
    merged = coalesce_batches([first, second, third])
    assert [batch.document_id for batch in merged] == ["doc-1", "doc-2"]
    assert merged[0].size == 2
    assert merged[0].merged_from == 3
    assert merged[0].token == "rev"
    assert merged[0].label == "two"
    found = batch_for_document(merged, "doc-2")
    assert found is not None
    assert found.document_id == third.document_id
    assert found.base_revision == third.base_revision
    assert batch_for_document(merged, "missing") is None
    assert with_label(first, "renamed").label == "renamed"


def test_autosave_coalescer_validates_limits() -> None:
    with pytest.raises(ValueError, match="interval"):
        AutosaveCoalescer(interval_ms=-1)
    with pytest.raises(ValueError, match="max wait"):
        AutosaveCoalescer(max_wait_ms=999_999)


def test_mention_kind_values_are_exposed_for_suggestions() -> None:
    assert {item.value for item in MentionKind} >= {"note", "user", "target", "finding"}
