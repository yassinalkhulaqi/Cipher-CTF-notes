"""Pure helper functions used by the incremental index and harness."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityId, EntityKind, EntityRef
from redscribe.v3.events.types import DomainEvent, EventRecord
from redscribe.v3.performance.models import IndexDocument
from redscribe.v3.performance.workers import (
    apply_delta_postings,
    build_postings,
    chunk,
    estimate_event_bytes,
    event_fingerprint,
    merge_postings,
    paginate_refs,
    rank_refs,
    score_candidates,
    tokenize,
    visible_range,
)


def doc(key: str, *tokens: str) -> IndexDocument:
    entity_id = EntityId(EntityKind.NOTE, key)
    return IndexDocument(EntityRef(entity_id, key), key, tokens)


def test_tokenize_is_stable_and_deduplicated() -> None:
    assert tokenize("Alpha, beta ALPHA 7 x") == ("alpha", "beta")
    assert tokenize("A B C", min_length=2) == ()
    assert tokenize("") == ()


def test_build_postings_is_sorted_and_complete() -> None:
    documents = (doc("b", "beta", "shared"), doc("a", "alpha", "shared"))
    postings = build_postings(documents)
    assert postings["shared"] == ("note:a", "note:b")
    assert postings["alpha"] == ("note:a",)
    assert tuple(postings) == ("alpha", "beta", "shared")


def test_merge_postings_union_and_intersection() -> None:
    postings = {"a": ("1", "2"), "b": ("2", "3")}
    assert merge_postings(postings, ("a", "b")) == ("1", "2", "3")
    assert merge_postings(postings, ("a", "b"), require_all=True) == ("2",)
    assert merge_postings(postings, ("missing",)) == ()


def test_score_candidates_counts_overlap() -> None:
    postings = {"a": ("1", "2"), "b": ("2",)}
    scores = score_candidates(("1", "2", "3"), ("a", "b"), postings)
    assert scores == {"1": 1, "2": 2, "3": 0}


def test_rank_refs_is_bounded_and_deterministic() -> None:
    documents = {item.key: item for item in (doc("a"), doc("b"), doc("c"))}
    refs = rank_refs({"note:a": 1, "note:b": 2, "note:c": 2}, documents, 2)
    assert [str(ref.entity_id) for ref in refs] == ["note:b", "note:c"]
    assert rank_refs({}, documents, 5) == ()
    with pytest.raises(ValueError, match="positive"):
        rank_refs({}, documents, 0)


def test_apply_delta_postings_is_pure() -> None:
    original = {"a": ("note:a", "note:b"), "b": ("note:b",)}
    updated = apply_delta_postings(
        original,
        (doc("c", "a", "c"),),
        ("note:b",),
    )
    assert updated == {"a": ("note:a", "note:c"), "c": ("note:c",)}
    assert original["a"] == ("note:a", "note:b")
    assert "b" not in updated


def test_chunk_handles_empty_and_partial() -> None:
    assert chunk((), 4) == ()
    assert chunk((1, 2, 3, 4, 5), 2) == ((1, 2), (3, 4), (5,))
    with pytest.raises(ValueError, match="positive"):
        chunk((1,), 0)


def test_visible_range_clamps_to_bounds() -> None:
    assert visible_range(1000, 320, 160, 32, overscan=2) == (8, 18)
    assert visible_range(10, 0, 640, 32, overscan=4) == (0, 10)
    assert visible_range(0, 100, 100, 32) == (0, 0)
    assert visible_range(10, 10000, 100, 32, overscan=0)[1] == 10


def test_paginate_refs_returns_window_and_more_flag() -> None:
    refs = tuple(EntityRef(EntityId(EntityKind.NOTE, f"n{i}")) for i in range(5))
    window, more = paginate_refs(refs, 2, 2)
    assert [str(ref.entity_id) for ref in window] == ["note:n2", "note:n3"]
    assert more is True
    window, more = paginate_refs(refs, 4, 2)
    assert len(window) == 1
    assert more is False
    with pytest.raises(ValueError, match="valid"):
        paginate_refs(refs, -1, 2)


def _record(sequence: int) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        event=DomainEvent(kind="note.indexed", payload={"topic": "alpha"}),
        timestamp=float(sequence),
    )


def test_event_fingerprint_is_sequence_sensitive() -> None:
    first = event_fingerprint((_record(1), _record(2)))
    second = event_fingerprint((_record(1), _record(2)))
    third = event_fingerprint((_record(2), _record(1)))
    assert first == second
    assert first != third
    assert event_fingerprint(()) == event_fingerprint(())


def test_estimate_event_bytes_scales_with_payload() -> None:
    small = estimate_event_bytes((_record(1),))
    large = estimate_event_bytes(
        (
            EventRecord(
                sequence=1,
                event=DomainEvent(
                    kind="note.indexed",
                    payload={"topic": "x" * 100},
                ),
                timestamp=1.0,
            ),
        )
    )
    assert large > small
    assert estimate_event_bytes(()) == 0
