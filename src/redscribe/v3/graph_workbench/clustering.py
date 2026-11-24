"""Deterministic clustering for tag, kind, and severity dimensions.

Clusters are computed on demand from the shared :class:`WorkbenchGraph`. A node
has one primary cluster per dimension, which keeps chip counts, filters, and
exported group boundaries consistent.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.graph_workbench.layout import Point
from redscribe.v3.graph_workbench.model import Severity, WorkbenchGraph

CLUSTER_PALETTE: tuple[str, ...] = (
    "#38bdf8",
    "#a78bfa",
    "#f472b6",
    "#fb7185",
    "#34d399",
    "#fbbf24",
    "#f59e0b",
    "#60a5fa",
    "#94a3b8",
    "#22d3ee",
    "#c084fc",
    "#4ade80",
)


class ClusterDimension(str, Enum):
    """Supported clustering dimensions."""

    TAG = "tag"
    KIND = "kind"
    SEVERITY = "severity"

    @classmethod
    def parse(cls, value: str) -> ClusterDimension:
        """Parse a dimension name with a stable error."""
        normalized = value.strip().casefold()
        for dimension in cls:
            if dimension.value == normalized:
                return dimension
        raise ValueError(
            f"Unknown cluster dimension '{value}'; "
            f"available: {', '.join(item.value for item in cls)}"
        )


CLUSTER_DIMENSIONS: tuple[str, ...] = tuple(item.value for item in ClusterDimension)


def cluster_color(key: str) -> str:
    """Map a cluster key to a stable color from the workbench palette."""
    value = 0
    for char in key:
        value = (value * 31 + ord(char)) & 0xFFFFFFFF
    return CLUSTER_PALETTE[value % len(CLUSTER_PALETTE)]


@dataclass(frozen=True, slots=True)
class Cluster:
    """One named group of vertices."""

    key: str
    label: str
    dimension: str
    node_ids: tuple[str, ...] = ()
    color: str = ""
    kind_counts: dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        """Return the number of member vertices."""
        return len(self.node_ids)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "label": self.label,
            "dimension": self.dimension,
            "node_ids": list(self.node_ids),
            "color": self.color,
            "size": self.size,
            "kind_counts": dict(sorted(self.kind_counts.items())),
        }


@dataclass(frozen=True, slots=True)
class ClusterResult:
    """Clusters and assignments for one dimension."""

    dimension: str
    clusters: tuple[Cluster, ...] = ()
    assignments: dict[str, str] = field(default_factory=dict)
    unassigned: tuple[str, ...] = ()

    def __len__(self) -> int:
        """Return the number of clusters."""
        return len(self.clusters)

    def cluster_for(self, node_id: str) -> Cluster | None:
        """Return the cluster containing a vertex, if any."""
        key = self.assignments.get(node_id)
        if key is None:
            return None
        return next((cluster for cluster in self.clusters if cluster.key == key), None)

    def key_for(self, node_id: str) -> str:
        """Return the cluster key of a vertex or an empty string."""
        return self.assignments.get(node_id, "")

    def keys(self) -> tuple[str, ...]:
        """Return stable cluster keys."""
        return tuple(cluster.key for cluster in self.clusters)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "dimension": self.dimension,
            "clusters": [cluster.as_dict() for cluster in self.clusters],
            "assignments": dict(sorted(self.assignments.items())),
            "unassigned": list(self.unassigned),
        }


def _label_for(dimension: ClusterDimension, key: str, graph: WorkbenchGraph) -> str:
    """Build a human-friendly chip label."""
    if dimension is ClusterDimension.KIND:
        spec = graph.registry.get(key)
        return spec.plural or spec.label
    if dimension is ClusterDimension.SEVERITY:
        return key.replace("_", " ").title()
    return key


def cluster_graph(
    graph: WorkbenchGraph,
    dimension: ClusterDimension | str = ClusterDimension.TAG,
    *,
    tag_prefix: str = "",
    max_clusters: int = 48,
) -> ClusterResult:
    """Group vertices into deterministic clusters along one dimension."""
    parsed = (
        dimension if isinstance(dimension, ClusterDimension) else ClusterDimension.parse(dimension)
    )
    if max_clusters < 1:
        raise ValueError("max_clusters must be positive")
    prefix = tag_prefix.strip().casefold().lstrip("#")
    assignments: dict[str, str] = {}
    for node_id in graph.node_ids:
        node = graph.node(node_id)
        if parsed is ClusterDimension.TAG:
            candidates = sorted(
                tag for tag in node.tag_set if tag.startswith(prefix) and (prefix or ":" not in tag)
            )
            if candidates:
                assignments[node_id] = candidates[0]
        elif parsed is ClusterDimension.KIND:
            assignments[node_id] = node.kind
        else:
            assignments[node_id] = Severity.parse(node.severity).value
    grouped: dict[str, list[str]] = defaultdict(list)
    for node_id, key in assignments.items():
        grouped[key].append(node_id)
    unassigned = tuple(node_id for node_id in graph.node_ids if node_id not in assignments)
    selected = sorted(grouped, key=lambda key: (-len(grouped[key]), key))
    if len(selected) > max_clusters:
        kept = set(selected[: max_clusters - 1])
        for node_id, key in tuple(assignments.items()):
            if key not in kept:
                assignments[node_id] = "other"
        grouped = defaultdict(list)
        for node_id, key in assignments.items():
            grouped[key].append(node_id)
        selected = sorted(grouped, key=lambda key: (-len(grouped[key]), key))[:max_clusters]
    clusters: list[Cluster] = []
    for key in selected:
        counts: dict[str, int] = defaultdict(int)
        for node_id in grouped[key]:
            counts[graph.node(node_id).kind] += 1
        clusters.append(
            Cluster(
                key=key,
                label=_label_for(parsed, key, graph),
                dimension=parsed.value,
                node_ids=tuple(sorted(grouped[key])),
                color=cluster_color(key),
                kind_counts=dict(sorted(counts.items())),
            )
        )
    return ClusterResult(
        dimension=parsed.value,
        clusters=tuple(clusters),
        assignments=dict(sorted(assignments.items())),
        unassigned=unassigned,
    )


def all_clusters(
    graph: WorkbenchGraph, *, tag_prefix: str = "", max_clusters: int = 48
) -> dict[str, ClusterResult]:
    """Compute clusterings along every supported dimension."""
    return {
        dimension: cluster_graph(graph, dimension, tag_prefix=tag_prefix, max_clusters=max_clusters)
        for dimension in CLUSTER_DIMENSIONS
    }


def cluster_chips(result: ClusterResult, *, selected: str = "") -> tuple[dict[str, Any], ...]:
    """Return chip descriptors for a cluster result."""
    return tuple(
        {
            "key": cluster.key,
            "label": cluster.label,
            "count": cluster.size,
            "color": cluster.color,
            "dimension": result.dimension,
            "selected": cluster.key == selected,
        }
        for cluster in result.clusters
    )


def filter_by_cluster(
    graph: WorkbenchGraph,
    result: ClusterResult,
    key: str,
) -> WorkbenchGraph:
    """Return the subgraph of one cluster, or the full graph for an empty key."""
    if not key:
        return graph.copy()
    members = {node_id for node_id, value in result.assignments.items() if value == key}
    return graph.induced(members)


def cluster_centroids(
    result: ClusterResult,
    positions: dict[str, Point],
) -> dict[str, Point]:
    """Return the mean position of each cluster for minimap overlays."""
    centroids: dict[str, Point] = {}
    for cluster in result.clusters:
        points = [positions[node_id] for node_id in cluster.node_ids if node_id in positions]
        if not points:
            continue
        centroids[cluster.key] = Point(
            sum(point.x for point in points) / len(points),
            sum(point.y for point in points) / len(points),
        )
    return centroids


def cluster_summary(graph: WorkbenchGraph, *, tag_prefix: str = "") -> dict[str, Any]:
    """Return a compact dashboard payload for all cluster dimensions."""
    results = all_clusters(graph, tag_prefix=tag_prefix)
    return {
        "dimensions": CLUSTER_DIMENSIONS,
        "counts": {dimension: len(result.clusters) for dimension, result in results.items()},
        "largest": {
            dimension: result.clusters[0].label if result.clusters else ""
            for dimension, result in results.items()
        },
        "unassigned": {dimension: len(result.unassigned) for dimension, result in results.items()},
    }
