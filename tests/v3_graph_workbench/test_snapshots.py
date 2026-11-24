"""Tests for graph snapshots, diffs, and round-trips."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.graph_workbench.snapshots import (
    GraphSnapshot,
    SnapshotStore,
    UnknownSnapshotError,
    diff_snapshots,
    graph_digest,
)
from tests.v3_graph_workbench import build_graph, build_service


def test_graph_digest_is_stable_and_content_sensitive() -> None:
    graph = build_graph()
    digest = graph_digest(graph)
    assert digest == graph_digest(graph)
    assert len(digest) == 64
    changed = graph.copy()
    changed.node("note:root").with_updates(title="Renamed")
    renamed = graph.copy()
    from redscribe.v3.graph_workbench.model import WorkbenchNode

    original = renamed.node("note:root")
    renamed.nodes["note:root"] = WorkbenchNode(
        ref=original.ref,
        title="Renamed",
        kind=original.kind,
        tags=original.tags,
        severity=original.severity,
        status=original.status,
        metadata=dict(original.metadata),
        timestamp=original.timestamp,
        version=original.version,
    )
    assert graph_digest(renamed) != digest
    assert graph_digest(changed) == digest


def test_capture_and_list_snapshots() -> None:
    store = SnapshotStore(clock=FixedClock(1000.0))
    graph = build_graph()
    first = store.capture(graph, label="before")
    second = store.capture(graph, label="after")
    assert first.meta.id != second.meta.id
    assert first.meta.sequence == 1
    assert first.meta.node_count == 4
    assert first.meta.edge_count == 3
    assert first.meta.created_at.endswith("Z")
    assert store.list()[0].meta.id == second.meta.id
    assert store.latest() == second
    assert store.payload(limit=1)["count"] == 2


def test_snapshot_restore_and_roundtrip() -> None:
    store = SnapshotStore(clock=FixedClock(10.0))
    graph = build_graph()
    snapshot = store.capture(graph)
    restored = store.restore(snapshot.meta.id)
    assert restored.as_dict() == graph.as_dict()
    serialized = snapshot.as_dict(include_records=True)
    revived = GraphSnapshot.from_dict(serialized)
    assert revived.meta == snapshot.meta
    assert revived.to_graph().as_dict() == snapshot.to_graph().as_dict()
    assert snapshot.as_dict()["meta"]["id"] == snapshot.meta.id


def test_snapshot_diff_detects_changes() -> None:
    store = SnapshotStore(clock=FixedClock(5.0))
    graph = build_graph()
    left = store.capture(graph)
    graph.remove_node("target:host-01")
    from redscribe.v3.entities import EntityId, EntityKind, EntityLink, LinkKind
    from redscribe.v3.graph_workbench.model import WorkbenchEdge

    graph.upsert_edge(
        WorkbenchEdge.from_link(
            EntityLink(
                EntityId(EntityKind.NOTE, "note"),
                EntityId(EntityKind.NOTE, "extra"),
                LinkKind.RELATES,
            )
        )
    )
    right = store.capture(graph)
    diff = store.compare(left.meta.id, right.meta.id)
    assert diff.changed
    assert diff.removed_nodes == ("target:host-01",)
    assert ("note:note", "note:extra", "relates") in diff.added_edges
    assert diff.total_changes >= 2
    assert diff.as_dict()["changed"] is True
    assert diff_snapshots(left, left).total_changes == 0


def test_snapshot_diff_detects_metadata_changes() -> None:
    store = SnapshotStore(clock=FixedClock(2.0))
    graph = build_graph()
    left = store.capture(graph)
    original = graph.node("note:root")
    from redscribe.v3.graph_workbench.model import WorkbenchNode

    graph.nodes["note:root"] = WorkbenchNode(
        ref=original.ref,
        title=original.title,
        kind=original.kind,
        tags=original.tags,
        severity=original.severity,
        status=original.status,
        owner=original.owner,
        summary=original.summary,
        metadata=dict(original.metadata),
        timestamp=original.timestamp,
        version=original.version + 1,
    )
    diff = store.compare(left.meta.id, store.capture(graph).meta.id)
    assert diff.changed_nodes == ("note:root",)


def test_snapshot_store_capacity_and_errors() -> None:
    store = SnapshotStore(capacity=2, clock=FixedClock(1.0))
    for index in range(4):
        store.capture(build_graph(), label=f"s{index}")
    assert store.payload()["count"] == 2
    oldest = store.list(limit=5)[-1]
    assert oldest.meta.label == "s2"
    assert store.delete(oldest.meta.id) is True
    assert store.delete(oldest.meta.id) is False
    with pytest.raises(UnknownSnapshotError):
        store.require("missing")
    with pytest.raises(ValueError, match="capacity"):
        SnapshotStore(capacity=0)
    assert store.list(limit=0) == ()


def test_service_capture_roundtrip_through_entity_changes() -> None:
    from redscribe.v3.graph_workbench.service import GraphWorkbench

    workbench = GraphWorkbench(build_service(), clock=FixedClock(0.0))
    before = workbench.capture(label="start")
    workbench.connect("note:root", "evidence:cap-01", label="new")
    after = workbench.capture(label="end")
    diff = workbench.compare(before.meta.id, after.meta.id)
    assert diff.changed
    assert len(diff.added_edges) == 1
    restored = workbench.snapshots.restore(before.meta.id)
    assert len(restored.edges) == 3
