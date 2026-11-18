"""Versioned graph snapshots for reproducible analysis and diffs."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from redscribe.v2.graph.model import GraphEdge, GraphModel, GraphNode

DEFAULT_CAPACITY = 12


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]) -> str:
    payload = {
        "nodes": [[node.id, node.label, node.kind, sorted(node.tag_set)] for node in nodes],
        "edges": [[edge.source, edge.target, edge.kind, edge.weight] for edge in edges],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
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
    source: str = "vault"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "digest": self.digest,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """An immutable copy of a graph at one point in time."""

    meta: SnapshotMeta
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def to_model(self) -> GraphModel:
        """Restore the snapshot as a mutable model."""
        return GraphModel.from_records(list(self.nodes), list(self.edges))

    def as_dict(self, *, include_records: bool = False) -> dict[str, Any]:
        """Return a JSON-serializable view of this snapshot."""
        data: dict[str, Any] = {"meta": self.meta.as_dict()}
        if include_records:
            data["nodes"] = [node.as_dict() for node in self.nodes]
            data["edges"] = [edge.as_dict() for edge in self.edges]
        return data


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """The structural delta between two snapshots."""

    left_id: str
    right_id: str
    added_nodes: tuple[int, ...]
    removed_nodes: tuple[int, ...]
    added_edges: tuple[tuple[int, int, str], ...]
    removed_edges: tuple[tuple[int, int, str], ...]

    @property
    def changed(self) -> bool:
        """Whether any node or edge differs."""
        return bool(
            self.added_nodes or self.removed_nodes or self.added_edges or self.removed_edges
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "added_nodes": list(self.added_nodes),
            "removed_nodes": list(self.removed_nodes),
            "added_edges": [list(key) for key in self.added_edges],
            "removed_edges": [list(key) for key in self.removed_edges],
            "changed": self.changed,
        }


def diff_snapshots(left: GraphSnapshot, right: GraphSnapshot) -> SnapshotDiff:
    """Compare two snapshots by vertex and edge identity."""
    left_nodes = {node.id for node in left.nodes}
    right_nodes = {node.id for node in right.nodes}
    left_edges = {edge.key for edge in left.edges}
    right_edges = {edge.key for edge in right.edges}
    return SnapshotDiff(
        left_id=left.meta.id,
        right_id=right.meta.id,
        added_nodes=tuple(sorted(right_nodes - left_nodes)),
        removed_nodes=tuple(sorted(left_nodes - right_nodes)),
        added_edges=tuple(sorted(right_edges - left_edges)),
        removed_edges=tuple(sorted(left_edges - right_edges)),
    )


@dataclass(slots=True)
class SnapshotStore:
    """Bounded in-memory history of graph snapshots."""

    capacity: int = DEFAULT_CAPACITY
    _snapshots: dict[str, GraphSnapshot] = field(default_factory=dict)
    _order: deque[str] = field(default_factory=deque)
    _counter: int = 0

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be positive")

    def capture(
        self,
        model: GraphModel,
        *,
        label: str = "",
        source: str = "vault",
        created_at: str | None = None,
    ) -> GraphSnapshot:
        """Capture, store, and return a snapshot of ``model``."""
        nodes = tuple(model.nodes[node_id] for node_id in sorted(model.nodes))
        edges = tuple(model.edges[key] for key in sorted(model.edges))
        digest = _digest(nodes, edges)
        self._counter += 1
        snapshot_id = f"snap_{self._counter:06d}_{digest[:8]}"
        meta = SnapshotMeta(
            id=snapshot_id,
            label=label or f"Snapshot {self._counter}",
            created_at=created_at or _timestamp(),
            node_count=len(nodes),
            edge_count=len(edges),
            digest=digest,
            source=source,
        )
        snapshot = GraphSnapshot(meta=meta, nodes=nodes, edges=edges)
        self._snapshots[snapshot_id] = snapshot
        self._order.append(snapshot_id)
        self.prune()
        return snapshot

    def get(self, snapshot_id: str) -> GraphSnapshot | None:
        """Return one snapshot by id."""
        return self._snapshots.get(snapshot_id)

    def require(self, snapshot_id: str) -> GraphSnapshot:
        """Return a snapshot or raise a value error."""
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")
        return snapshot

    def list(self, *, limit: int = 20) -> tuple[GraphSnapshot, ...]:
        """Return snapshots newest first."""
        if limit < 1:
            return ()
        ids = list(self._order)[::-1][:limit]
        return tuple(self._snapshots[snapshot_id] for snapshot_id in ids)

    def latest(self) -> GraphSnapshot | None:
        """Return the newest stored snapshot."""
        snapshots = self.list(limit=1)
        return snapshots[0] if snapshots else None

    def restore(self, snapshot_id: str) -> GraphModel:
        """Restore one snapshot into a fresh model."""
        return self.require(snapshot_id).to_model()

    def delete(self, snapshot_id: str) -> bool:
        """Delete one snapshot by id."""
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
        """Return a JSON-serializable history payload."""
        snapshots = self.list(limit=limit)
        return {
            "count": len(self._order),
            "snapshots": [snapshot.meta.as_dict() for snapshot in snapshots],
            "latest_id": snapshots[0].meta.id if snapshots else None,
        }
