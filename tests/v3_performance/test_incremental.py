"""Incremental index behavior: generations, caching, and coherence."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityId, EntityKind, EntityRef
from redscribe.v3.performance.incremental import IncrementalIndex
from redscribe.v3.performance.meter import Meter
from redscribe.v3.performance.models import IndexDelta, IndexDocument, QuerySpec
from redscribe.v3.performance.queryplan import plan_step_names


def doc(key: str, *tokens: str, version: int = 1) -> IndexDocument:
    entity_id = EntityId(EntityKind.NOTE, key)
    return IndexDocument(EntityRef(entity_id, key), key, tokens, version)


def test_add_and_query_return_bounded_results() -> None:
    index = IncrementalIndex()
    assert index.generation == 0
    assert index.add(doc("a", "alpha", "shared")) == 1
    index.add(doc("b", "beta", "shared"))
    assert index.size == 2
    result = index.query(QuerySpec(tokens=("shared",), limit=1))
    assert len(result.refs) == 1
    assert result.candidates == 2
    assert result.cache_hit is False
    assert result.generation == 2
    assert result.plan is not None
    assert plan_step_names(result.plan) == (
        "cache_lookup",
        "posting_lookup",
        "posting_union",
        "candidate_score",
        "rank_window",
    )


def test_second_query_is_a_cached_hit() -> None:
    index = IncrementalIndex()
    index.apply(IndexDelta(upserts=(doc("a", "alpha"), doc("b", "beta"))))
    first = index.query(QuerySpec(tokens=("alpha",), limit=5))
    second = index.query(QuerySpec(tokens=("alpha",), limit=5))
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.refs == first.refs
    assert second.plan is not None
    assert second.plan.cache_hit
    assert plan_step_names(second.plan) == ("cache_lookup", "cache_hit")


def test_unrelated_edit_keeps_cache_and_related_edit_evicts() -> None:
    index = IncrementalIndex()
    index.apply(IndexDelta(upserts=(doc("a", "alpha"),)))
    spec = QuerySpec(tokens=("alpha",), limit=5)
    assert index.query(spec).cache_hit is False

    index.add(doc("b", "beta"))
    assert index.generation == 2
    assert index.query(spec).cache_hit is True

    index.add(doc("c", "alpha", "gamma"))
    assert index.generation == 3
    assert index.query(spec).cache_hit is False
    stats = index.stats()
    assert stats["cache_evictions"] == 1
    assert stats["cache_entries"] == 1


def test_remove_invalidates_and_updates_postings() -> None:
    index = IncrementalIndex()
    index.apply(IndexDelta(upserts=(doc("a", "alpha"), doc("b", "alpha"))))
    spec = QuerySpec(tokens=("alpha",), limit=5)
    assert len(index.query(spec).refs) == 2
    assert "note:a" in index.postings_for("alpha")

    index.remove("note:a")
    assert "note:a" not in index.postings_for("alpha")
    assert len(index.query(spec).refs) == 1
    assert index.query(spec).cache_hit is True


def test_empty_delta_does_not_change_generation() -> None:
    index = IncrementalIndex()
    assert index.apply(IndexDelta()) == 0
    assert index.add(doc("a", "alpha")) == 1
    assert index.apply(IndexDelta(removals=("unknown",))) == 2
    assert index.size == 1


def test_require_all_intersection() -> None:
    index = IncrementalIndex()
    index.apply(
        IndexDelta(
            upserts=(
                doc("a", "alpha"),
                doc("b", "beta"),
                doc("c", "alpha", "beta"),
            )
        )
    )
    any_result = index.query(QuerySpec(tokens=("alpha", "beta"), limit=10))
    all_result = index.query(QuerySpec(tokens=("alpha", "beta"), limit=10, require_all=True))
    assert any_result.candidates == 3
    assert all_result.candidates == 1
    assert [str(ref.entity_id) for ref in all_result.refs] == ["note:c"]


def test_incremental_index_matches_full_rebuild() -> None:
    index = IncrementalIndex()
    for batch in range(4):
        documents = tuple(doc(f"n{batch}-{item}", "shared", f"topic{item}") for item in range(10))
        index.apply(IndexDelta(upserts=documents))
    assert index.is_consistent()
    index.apply(IndexDelta(removals=("note:n1-3",)))
    assert index.is_consistent()
    assert index.stats()["rebuilds"] == 2


def test_fingerprint_tracks_versions() -> None:
    index = IncrementalIndex()
    index.add(doc("a", "alpha"))
    first = index.fingerprint()
    index.add(doc("a", "alpha", version=2))
    assert index.fingerprint() != first
    assert index.fingerprint() == index.fingerprint()


def test_meter_counts_are_recorded() -> None:
    meter = Meter()
    index = IncrementalIndex(meter=meter)
    index.apply(IndexDelta(upserts=(doc("a", "alpha"), doc("b", "beta"))))
    assert meter.count("index_mutation") == 2
    index.query(QuerySpec(tokens=("alpha",), limit=5))
    assert meter.count("posting_lookup") == 1
    assert meter.count("rank_window") == 0
    assert meter.modeled_ms > 0


def test_documents_are_returned_in_stable_order() -> None:
    index = IncrementalIndex()
    index.apply(IndexDelta(upserts=(doc("b"), doc("a"), doc("c"))))
    assert [item.key for item in index.documents()] == ["note:a", "note:b", "note:c"]


def test_query_spec_fingerprint_separates_cache_entries() -> None:
    index = IncrementalIndex()
    index.add(doc("a", "alpha", "shared"))
    first = index.query(QuerySpec(tokens=("alpha",), limit=5))
    second = index.query(QuerySpec(tokens=("shared",), limit=5))
    assert first.cache_hit is False
    assert second.cache_hit is False
    assert index.stats()["cache_entries"] == 2


def test_missing_token_returns_empty_result() -> None:
    index = IncrementalIndex()
    index.add(doc("a", "alpha"))
    result = index.query(QuerySpec(tokens=("missing",), limit=5))
    assert result.refs == ()
    assert result.candidates == 0


def test_index_postings_for_unknown_token() -> None:
    index = IncrementalIndex()
    assert index.postings_for("unknown") == ()
    with pytest.raises(ValueError, match="limit"):
        QuerySpec(tokens=("alpha",), limit=0)
