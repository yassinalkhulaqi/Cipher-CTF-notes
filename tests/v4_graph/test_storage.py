from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from redscribe.v4.graph_v4.storage import (
    GraphStore,
    GraphStoreError,
    InMemoryGraphRepository,
    SqliteGraphRepository,
)
from redscribe.v4.graph_v4.types import (
    EntityKind,
    GraphData,
    GraphEdge,
    GraphFilter,
    GraphNode,
    GraphSnapshot,
    LayoutKind,
)

from .conftest import NODE_A, NODE_B


@pytest.fixture
def sqlite_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    try:
        yield connection
    finally:
        connection.close()


def sample_data() -> GraphData:
    return GraphData(
        nodes=(
            GraphNode(id=NODE_A, kind=EntityKind.NOTE, label="Alpha"),
            GraphNode(id=NODE_B, kind=EntityKind.TARGET, label="Beta"),
        ),
        edges=(GraphEdge(source=NODE_A, target=NODE_B, relation="linked_to", weight=0.8),),
    )


def fixed_clock() -> str:
    return "2026-02-02T12:00:00.000Z"


def test_name_validation() -> None:
    store = GraphStore(clock=fixed_clock)
    for bad in ("Bad Name", "", "a" * 65, "bad!name"):
        with pytest.raises(GraphStoreError, match="invalid snapshot name"):
            store.save(bad, sample_data())


def test_in_memory_save_load_and_names() -> None:
    store = GraphStore(clock=fixed_clock)
    assert store.names == ()
    assert not store.exists("alpha")
    snapshot = store.save("Alpha", sample_data())
    assert snapshot.name == "alpha"
    assert snapshot.created_at == fixed_clock()
    assert store.exists("alpha")
    assert store.names == ("alpha",)
    assert store.load("alpha") == snapshot
    with pytest.raises(GraphStoreError, match="already exists"):
        store.save("alpha", sample_data())


def test_in_memory_delete_and_missing_lookup() -> None:
    store = GraphStore(clock=fixed_clock)
    store.save("alpha", sample_data())
    assert store.delete("alpha")
    assert not store.delete("alpha")
    with pytest.raises(GraphStoreError, match="not found"):
        store.load("alpha")
    with pytest.raises(GraphStoreError, match="not found"):
        store.load_filter("missing")


def test_filter_index_round_trip() -> None:
    store = GraphStore(clock=fixed_clock)
    note_filter = GraphFilter().with_kind(EntityKind.NOTE)
    store.save_filter("notes", note_filter)
    store.save_filter("targets", GraphFilter().with_kind(EntityKind.TARGET))
    assert store.load_filter("notes") == note_filter
    assert set(store.filters()) == {"notes", "targets"}
    assert tuple(InMemoryGraphRepository().filter_names()) == ()


def test_export_contains_serialized_filters() -> None:
    store = GraphStore(clock=fixed_clock)
    store.save("alpha", sample_data(), GraphFilter().with_label("alpha"), LayoutKind.GRID)
    store.save_filter("notes", GraphFilter().with_kind(EntityKind.NOTE))
    payload = store.export("alpha")
    assert payload["name"] == "alpha"
    assert payload["layout"] == "grid"
    assert payload["filter"]["label_contains"] == "alpha"
    assert payload["filter_index"]["notes"]["kinds"] == ["note"]
    assert len(store.export_all()) == 1


def test_import_snapshot_and_errors() -> None:
    store = GraphStore(clock=fixed_clock)
    original = store.save("alpha", sample_data(), tags=("primary", "reviewed"))
    payload = original.to_dict()
    other = GraphStore(clock=fixed_clock)
    imported = other.import_snapshot(payload)
    assert imported == original
    assert other.names == ("alpha",)
    with pytest.raises(GraphStoreError, match="already exists"):
        other.import_snapshot(payload)
    with pytest.raises(GraphStoreError, match="invalid snapshot payload"):
        other.import_snapshot({"name": 123, "data": "bad"})
    with pytest.raises(GraphStoreError, match="invalid snapshot name"):
        other.import_snapshot({**payload, "name": "INVALID NAME"})


def test_clone_uses_new_timestamp_and_keeps_data() -> None:
    store = GraphStore(clock=fixed_clock)
    original = store.save("alpha", sample_data(), GraphFilter().with_min_weight(0.5))
    clone = store.clone("alpha", "alpha-copy")
    assert clone.name == "alpha-copy"
    assert clone.created_at == fixed_clock()
    assert clone.data == original.data
    assert clone.filter == original.filter
    assert store.names == ("alpha", "alpha-copy")
    with pytest.raises(GraphStoreError, match="already exists"):
        store.clone("alpha", "alpha-copy")


def test_clear_removes_all_snapshots() -> None:
    store = GraphStore(clock=fixed_clock)
    store.save("alpha", sample_data())
    store.save("beta", sample_data())
    store.clear()
    assert store.names == ()


def test_repository_direct_usage() -> None:
    repository = InMemoryGraphRepository()
    snapshot = GraphSnapshot(
        name="direct",
        data=sample_data(),
        filter=GraphFilter(),
        layout=LayoutKind.FORCE,
        created_at=fixed_clock(),
    )
    repository.save("direct", snapshot)
    assert repository.load("direct") == snapshot
    assert repository.names() == ("direct",)
    repository.clear()
    assert repository.load("direct") is None


def test_sqlite_repository_round_trip(sqlite_connection: sqlite3.Connection) -> None:
    repository = SqliteGraphRepository(sqlite_connection)
    store = GraphStore(repository=repository, clock=fixed_clock)
    store.save(
        "alpha",
        sample_data(),
        GraphFilter().with_kind(EntityKind.NOTE),
        LayoutKind.CIRCULAR,
        ("tag-one",),
    )
    loaded = store.load("alpha")
    assert loaded.layout is LayoutKind.CIRCULAR
    assert loaded.tags == ("tag-one",)
    assert loaded.filter.kinds == (EntityKind.NOTE,)
    assert store.names == ("alpha",)
    store.save_filter("notes", GraphFilter().with_relation("linked_to"))
    assert store.load_filter("notes").relations == ("linked_to",)
    assert store.export("alpha")["data"]["nodes"][0]["id"] == NODE_A
    assert store.delete("alpha")
    assert store.names == ()


def test_sqlite_schema_is_idempotent(sqlite_connection: sqlite3.Connection) -> None:
    first = SqliteGraphRepository(sqlite_connection)
    second = SqliteGraphRepository(sqlite_connection)
    first.save_filter("shared", GraphFilter().with_min_weight(0.25))
    assert second.load_filter("shared") == GraphFilter().with_min_weight(0.25)
    assert second.filter_names() == ("shared",)


def test_sqlite_missing_snapshot(sqlite_connection: sqlite3.Connection) -> None:
    store = GraphStore(repository=SqliteGraphRepository(sqlite_connection), clock=fixed_clock)
    with pytest.raises(GraphStoreError, match="not found"):
        store.load("absent")
    assert store.exists("absent") is False
