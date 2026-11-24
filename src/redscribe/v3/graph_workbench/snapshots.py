"""Versioned graph snapshots, diffs, and deterministic round-trips."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.clock import Clock, SystemClock, iso_from_timestamp
from redscribe.v3.graph_workbench.model import WorkbenchEdge, WorkbenchGraph, WorkbenchNode

DEFAULT_CAPACITY = 16


def _canonical_payload(graph: WorkbenchGraph) -> dict[str, Any]:
    """Return the minimal structural payload used for digests."""
    return {
        "nodes": [
            {
                "id": node_id,
                "title": graph.node(node_id).title,
                "kind": graph.node(node_id).kind,
                "severity": graph.node(node_id).severity,
                "tags": list(graph.node(node_id).tags),
                "version": graph.node(node_id).version,
            }
            for node_id in graph.node_ids
        ],
        "edges": [
            {
                "key": list(key),
                "weight": graph.edges[key].weight,
                "label": graph.edges[key].label,
            }
            for key in graph.edge_keys
        ],
    }


def graph_digest(graph: WorkbenchGraph) -> str:
    """Return a stable SHA-256 digest of graph content."""
    raw = json.dumps(
        _canonical_payload(graph), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    """Transport metadata for one captured graph."""

    id: str
    label: str
    created_at: str
    node_count: int
    edge_count: int
    digest: str
    source: str = "workbench"
    sequence: int = 1

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "digest": self.digest,
            "source": self.source,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """An immutable graph state that can be restored or exported later."""

    meta: SnapshotMeta
    nodes: tuple[WorkbenchNode, ...] = ()
    edges: tuple[WorkbenchEdge, ...] = ()

    def to_graph(self) -> WorkbenchGraph:
        """Restore a fresh workbench graph from this snapshot."""
        graph = WorkbenchGraph()
        for node in self.nodes:
            graph.upsert_node(node)
        for edge in self.edges:
            graph.upsert_edge(edge)
        return graph

    def as_dict(self, *, include_records: bool = False) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload: dict[str, Any] = {"meta": self.meta.as_dict()}
        if include_records:
            payload["nodes"] = [node.as_dict() for node in self.nodes]
            payload["edges"] = [edge.as_dict() for edge in self.edges]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphSnapshot:
        """Restore a complete snapshot from its serialized form."""
        meta_data = dict(data.get("meta", {}))
        meta = SnapshotMeta(
            id=str(meta_data.get("id", "")),
            label=str(meta_data.get("label", "")),
            created_at=str(meta_data.get("created_at", "")),
            node_count=int(meta_data.get("node_count", 0)),
            edge_count=int(meta_data.get("edge_count", 0)),
            digest=str(meta_data.get("digest", "")),
            source=str(meta_data.get("source", "workbench")),
            sequence=int(meta_data.get("sequence", 1)),
        )
        nodes = tuple(WorkbenchNode.from_dict(dict(item)) for item in data.get("nodes", ()))
        edges = tuple(WorkbenchEdge.from_dict(dict(item)) for item in data.get("edges", ()))
        return cls(meta=meta, nodes=nodes, edges=edges)


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """The structural delta between two snapshots."""

    left_id: str
    right_id: str
    added_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()
    changed_nodes: tuple[str, ...] = ()
    added_edges: tuple[tuple[str, str, str], ...] = ()
    removed_edges: tuple[tuple[str, str, str], ...] = ()
    changed_edges: tuple[tuple[str, str, str], ...] = ()

    @property
    def changed(self) -> bool:
        """Return whether the two snapshots differ."""
        return bool(
            self.added_nodes
            or self.removed_nodes
            or self.changed_nodes
            or self.added_edges
            or self.removed_edges
            or self.changed_edges
        )

    @property
    def total_changes(self) -> int:
        """Return the number of individual differences."""
        return sum(
            len(items)
            for items in (
                self.added_nodes,
                self.removed_nodes,
                self.changed_nodes,
                self.added_edges,
                self.removed_edges,
                self.changed_edges,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "added_nodes": list(self.added_nodes),
            "removed_nodes": list(self.removed_nodes),
            "changed_nodes": list(self.changed_nodes),
            "added_edges": [list(key) for key in self.added_edges],
            "removed_edges": [list(key) for key in self.removed_edges],
            "changed_edges": [list(key) for key in self.changed_edges],
            "changed": self.changed,
            "total_changes": self.total_changes,
        }


def diff_snapshots(left: GraphSnapshot, right: GraphSnapshot) -> SnapshotDiff:
    """Compare two snapshots by node identity and typed edge identity."""
    left_graph = left.to_graph()
    right_graph = right.to_graph()
    left_nodes = set(left_graph.nodes)
    right_nodes = set(right_graph.nodes)
    left_edges = set(left_graph.edges)
    right_edges = set(right_graph.edges)
    changed_nodes = tuple(
        sorted(
            node_id
            for node_id in left_nodes & right_nodes
            if left_graph.nodes[node_id].as_dict() != right_graph.nodes[node_id].as_dict()
        )
    )
    changed_edges = tuple(
        sorted(
            key
            for key in left_edges & right_edges
            if left_graph.edges[key].as_dict() != right_graph.edges[key].as_dict()
        )
    )
    return SnapshotDiff(
        left_id=left.meta.id,
        right_id=right.meta.id,
        added_nodes=tuple(sorted(right_nodes - left_nodes)),
        removed_nodes=tuple(sorted(left_nodes - right_nodes)),
        changed_nodes=changed_nodes,
        added_edges=tuple(sorted(right_edges - left_edges)),
        removed_edges=tuple(sorted(left_edges - right_edges)),
        changed_edges=changed_edges,
    )


class UnknownSnapshotError(KeyError):
    """Raised when a snapshot id is not present in a store."""


@dataclass(slots=True)
class SnapshotStore:
    """Bounded in-memory history of workbench graph snapshots."""

    capacity: int = DEFAULT_CAPACITY
    clock: Clock = field(default_factory=SystemClock)
    _snapshots: dict[str, GraphSnapshot] = field(default_factory=dict)
    _order: deque[str] = field(default_factory=deque)
    _sequence: int = 0

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("Snapshot capacity must be positive")

    def capture(
        self,
        graph: WorkbenchGraph,
        *,
        label: str = "",
        source: str = "workbench",
    ) -> GraphSnapshot:
        """Capture, store, and return a snapshot of a graph."""
        self._sequence += 1
        digest = graph_digest(graph)
        snapshot_id = f"gws_{self._sequence:06d}_{digest[:8]}"
        meta = SnapshotMeta(
            id=snapshot_id,
            label=label or f"Snapshot {self._sequence}",
            created_at=iso_from_timestamp(self.clock.now_timestamp()),
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            digest=digest,
            source=source,
            sequence=self._sequence,
        )
        nodes = tuple(graph.node(node_id) for node_id in graph.node_ids)
        edges = tuple(graph.edges[key] for key in graph.edge_keys)
        snapshot = GraphSnapshot(meta=meta, nodes=nodes, edges=edges)
        self._snapshots[snapshot_id] = snapshot
        self._order.append(snapshot_id)
        self.prune()
        return snapshot

    def get(self, snapshot_id: str) -> GraphSnapshot | None:
        """Return one snapshot by id."""
        return self._snapshots.get(snapshot_id)

    def require(self, snapshot_id: str) -> GraphSnapshot:
        """Return one snapshot or raise :class:`UnknownSnapshotError`."""
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            raise UnknownSnapshotError(f"Unknown snapshot: {snapshot_id}")
        return snapshot

    def list(self, *, limit: int = 20) -> tuple[GraphSnapshot, ...]:
        """Return snapshots newest first."""
        if limit < 1:
            return ()
        ordered = list(self._order)[::-1][:limit]
        return tuple(self._snapshots[item] for item in ordered if item in self._snapshots)

    def latest(self) -> GraphSnapshot | None:
        """Return the newest stored snapshot."""
        snapshots = self.list(limit=1)
        return snapshots[0] if snapshots else None

    def restore(self, snapshot_id: str) -> WorkbenchGraph:
        """Restore one snapshot into a fresh workbench graph."""
        return self.require(snapshot_id).to_graph()

    def delete(self, snapshot_id: str) -> bool:
        """Delete one snapshot, returning whether it existed."""
        if snapshot_id not in self._snapshots:
            return False
        del self._snapshots[snapshot_id]
        self._order = deque(item for item in self._order if item != snapshot_id)
        return True

    def prune(self) -> int:
        """Drop the oldest snapshots beyond capacity."""
        removed = 0
        while len(self._order) > self.capacity:
            snapshot_id = self._order.popleft()
            self._snapshots.pop(snapshot_id, None)
            removed += 1
        return removed

    def compare(self, left_id: str, right_id: str) -> SnapshotDiff:
        """Diff two stored snapshots."""
        return diff_snapshots(self.require(left_id), self.require(right_id))

    def payload(self, *, limit: int = 20) -> dict[str, Any]:
        """Return a JSON-safe history payload."""
        snapshots = self.list(limit=limit)
        return {
            "count": len(self._order),
            "capacity": self.capacity,
            "snapshots": [snapshot.meta.as_dict() for snapshot in snapshots],
            "latest_id": snapshots[0].meta.id if snapshots else None,
        }
