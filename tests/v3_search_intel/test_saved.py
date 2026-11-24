"""Saved searches and facet sets with round-trip persistence."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.search_intel.saved import (
    SavedFacetSetStore,
    SavedSearchStore,
    make_item_id,
    normalize_tags,
    sort_searches,
    validate_facet_set,
    validate_saved_search,
)


def test_validate_saved_search_normalizes() -> None:
    assert validate_saved_search("  My  Search ", " kind:finding ") == (
        "My Search",
        "kind:finding",
    )


def test_validate_saved_search_rejects_empty() -> None:
    with pytest.raises(ValueError, match="name is required"):
        validate_saved_search("  ", "kind:finding")
    with pytest.raises(ValueError, match="query is required"):
        validate_saved_search("Name", "  ")


def test_validate_saved_search_rejects_long_values() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        validate_saved_search("x" * 81, "kind:finding")
    with pytest.raises(ValueError, match="exceeds"):
        validate_saved_search("Name", "x" * 501)


def test_normalize_tags_dedupes_and_limits() -> None:
    assert normalize_tags("Web, web, RECON") == ("Web", "RECON")
    assert normalize_tags(["", "x" * 50]) == ()
    assert len(normalize_tags([f"t{i}" for i in range(20)])) == 12


def test_make_item_id_is_deterministic() -> None:
    assert make_item_id("q", "Name", "kind:finding") == make_item_id("q", "name", "KIND:FINDING")


def test_create_and_get_saved_search() -> None:
    store = SavedSearchStore(clock=FixedClock(start=100.0))
    item = store.create("Critical", "kind:finding severity:critical", tags=("triage",))
    assert store.get(item.id) == item
    assert item.created_at == 100.0
    assert item.updated_at == 100.0
    assert "q_" in item.id


def test_duplicate_saved_search_id_is_rejected() -> None:
    store = SavedSearchStore(clock=FixedClock(start=100.0))
    store.create("A", "kind:note", saved_id="custom")
    with pytest.raises(ValueError, match="already exists"):
        store.create("B", "kind:finding", saved_id="custom")


def test_update_bumps_version_and_timestamp() -> None:
    store = SavedSearchStore(clock=FixedClock(start=100.0, step=5.0))
    item = store.create("A", "kind:note")
    updated = store.update(item.id, name="B", pinned=True)
    assert updated.name == "B"
    assert updated.pinned
    assert updated.updated_at == 105.0
    assert updated.created_at == 100.0


def test_update_unknown_id_raises() -> None:
    store = SavedSearchStore()
    with pytest.raises(KeyError):
        store.update("missing", name="X")


def test_touch_increments_use_count() -> None:
    store = SavedSearchStore(clock=FixedClock(start=1.0))
    item = store.create("A", "kind:note")
    assert store.touch(item.id) is not None
    found = store.get(item.id)
    assert found is not None
    assert found.use_count == 1
    assert store.touch("missing") is None


def test_delete_saved_search() -> None:
    store = SavedSearchStore()
    item = store.create("A", "kind:note")
    assert store.delete(item.id)
    assert not store.delete(item.id)
    assert len(store) == 0


def test_list_filters_and_sorts() -> None:
    store = SavedSearchStore(clock=FixedClock(start=1.0, step=1.0))
    pinned = store.create("Pinned", "kind:finding", pinned=True, tags=("triage",))
    other = store.create("Other", "kind:note", tags=("notes",))
    store.touch(other.id)
    assert store.list()[0].id == pinned.id
    assert store.list(tag="notes")[0].id == other.id
    assert store.list(search="Pinned")[0].id == pinned.id
    assert store.list(limit=1)[0].id == pinned.id


def test_sort_searches_is_stable() -> None:
    store = SavedSearchStore(clock=FixedClock(start=1.0))
    first = store.create("A", "kind:note")
    second = store.create("B", "kind:finding")
    assert sort_searches([second, first]) == sort_searches([first, second])


def test_saved_search_round_trip() -> None:
    store = SavedSearchStore(clock=FixedClock(start=1.0))
    item = store.create("A", "kind:note", description="desc", tags=("x",))
    payload = store.to_dict()
    restored = SavedSearchStore()
    assert restored.load(payload) == 1
    assert restored.get(item.id) == item
    assert restored.to_dict() == payload


def test_import_skips_malformed_entries() -> None:
    store = SavedSearchStore()
    count = store.import_items(
        [
            {"name": "Good", "query": "kind:note"},
            {"name": "", "query": "kind:note"},
            {"name": "Bad", "query": ""},
        ]
    )
    assert count == 1
    assert len(store) == 1


def test_facet_set_validation() -> None:
    assert validate_facet_set(" My Set ", ["KIND", "tag", "kind"]) == (
        "My Set",
        ("kind", "tag"),
    )
    with pytest.raises(ValueError, match="at least one field"):
        validate_facet_set("X", [])


def test_facet_set_store_round_trip() -> None:
    store = SavedFacetSetStore(clock=FixedClock(start=10.0))
    item = store.create("Triage", ("kind", "severity"))
    assert store.get(item.id) == item
    payload = store.to_dict()
    restored = SavedFacetSetStore()
    assert restored.load(payload) == 1
    assert restored.to_dict() == payload
    assert restored.delete(item.id)
    assert not restored.delete(item.id)
