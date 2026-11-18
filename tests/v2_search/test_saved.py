from __future__ import annotations

import pytest

from redscribe.storage.db import Vault
from redscribe.v2.search.saved import (
    MAX_SAVED_QUERIES,
    SavedQueryStore,
    normalize_tags,
    validate_saved_query,
)


def clock() -> str:
    return "2026-01-02T12:00:00Z"


def test_validate_saved_query_normalizes_and_rejects() -> None:
    assert validate_saved_query("  Weekly   review ", "  nmap  ") == (
        "Weekly review",
        "nmap",
    )
    with pytest.raises(ValueError):
        validate_saved_query(" ", "nmap")
    with pytest.raises(ValueError):
        validate_saved_query("Name", " ")
    with pytest.raises(ValueError):
        validate_saved_query("x" * 81, "nmap")
    with pytest.raises(ValueError):
        validate_saved_query("Name", "x" * 501)


def test_normalize_tags_deduplicates_and_limits() -> None:
    assert normalize_tags("web, Web, recon, ,   ") == ("web", "recon")
    assert normalize_tags(["a", "A", "b" * 41]) == ("a",)
    assert len(normalize_tags([f"tag{i}" for i in range(30)])) == 12


def make_store(vault: Vault) -> SavedQueryStore:
    return SavedQueryStore(vault, clock=clock)


def test_create_get_list_and_duplicate_ids(vault: Vault) -> None:
    store = make_store(vault)
    first = store.create(
        "Weekly review",
        "nmap tag:web",
        description="  scan   review ",
        tags="web,recon",
        pinned=True,
        saved_id="sq_fixed",
    )
    assert first.id == "sq_fixed"
    assert first.description == "scan review"
    assert store.get("sq_fixed") == first
    assert store.get("missing") is None
    with pytest.raises(ValueError):
        store.create("Other", "ssh", saved_id="sq_fixed")
    assert [item.id for item in store.list()] == ["sq_fixed"]
    clone = store.duplicate("sq_fixed", name="Copy")
    assert clone is not None
    assert clone.id != first.id
    assert clone.query == first.query
    assert store.duplicate("missing") is None


def test_list_filters_and_sorting(vault: Vault) -> None:
    store = make_store(vault)
    store.create("Alpha", "nmap", tags="web")
    store.create("Beta", "ssh", tags="recon", pinned=True)
    store.create("Gamma", "nmap ssh", tags="web,recon")
    assert [item.name for item in store.list(search="nmap")] == ["Alpha", "Gamma"]
    assert [item.name for item in store.list(tag="recon")] == ["Beta", "Gamma"]
    assert [item.name for item in store.list(limit=1)] == ["Beta"]
    assert store.list(limit=-1) == []


def test_update_delete_and_use(vault: Vault) -> None:
    store = make_store(vault)
    item = store.create("Original", "nmap")
    updated = store.update(item.id, name="Renamed", pinned=True, tags="web")
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.pinned is True
    assert updated.tags == ("web",)
    assert store.update("missing", name="X") is None
    used = store.record_use(item.id)
    assert used is not None
    assert used.use_count == 1
    assert store.record_use("missing") is None
    assert store.toggle_pin(item.id) is not None
    assert store.toggle_pin("missing") is None
    assert store.delete(item.id) is True
    assert store.delete(item.id) is False


def test_import_export_and_replace(vault: Vault) -> None:
    store = make_store(vault)
    first = store.create("Alpha", "nmap", saved_id="sq_a")
    payload = store.export_payload()
    assert payload[0]["id"] == "sq_a"
    assert store.import_items(payload) == 1
    assert len(store.list()) == 2
    assert store.import_items([{"id": "bad"}]) == 0
    assert store.import_items(payload, replace=True) == 1
    assert len(store.list()) == 1
    second = store.create("Beta", "ssh", saved_id="sq_b")
    assert second.id == "sq_b"
    assert first.name == "Alpha"


def test_save_cap_is_enforced(vault: Vault) -> None:
    store = make_store(vault)
    for index in range(MAX_SAVED_QUERIES + 10):
        store.create(f"Query {index}", f"term{index}", saved_id=f"sq_{index:04}")
    assert len(store.list(limit=1000)) == MAX_SAVED_QUERIES


def test_malformed_settings_are_ignored(vault: Vault) -> None:
    vault.set_json_setting("v2.search.saved_queries", {"not": "a list"})
    assert make_store(vault).list() == []
    vault.set_json_setting("v2.search.saved_queries", [1, "bad", {}])
    assert make_store(vault).list() == []
