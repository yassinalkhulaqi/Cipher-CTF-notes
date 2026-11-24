"""Facade service composing every graph-workbench subsystem."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from redscribe.v3.capabilities import CAP_GRAPH, Capabilities
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities import EntityId, EntityService
from redscribe.v3.events import EventBus, make_event
from redscribe.v3.graph_workbench.analysis import (
    PathResult,
    articulation_points,
    bridges,
    connected_components,
    neighborhood,
    shortest_path,
    structural_summary,
)
from redscribe.v3.graph_workbench.clustering import (
    CLUSTER_DIMENSIONS,
    ClusterResult,
    all_clusters,
    cluster_chips,
    cluster_graph,
    filter_by_cluster,
)
from redscribe.v3.graph_workbench.editor import EditRecord, RelationshipEditor
from redscribe.v3.graph_workbench.exports import ExportResult, export_graph
from redscribe.v3.graph_workbench.layout import (
    LayoutOptions,
    LayoutResult,
    available_layouts,
    compute_layout,
)
from redscribe.v3.graph_workbench.model import (
    WorkbenchGraph,
    graph_from_entity_snapshot,
)
from redscribe.v3.graph_workbench.snapshots import (
    GraphSnapshot,
    SnapshotDiff,
    SnapshotStore,
)


@dataclass(frozen=True, slots=True)
class WorkbenchFilters:
    """Declarative filters for the active graph view."""

    kinds: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    severities: tuple[str, ...] = ()
    query: str = ""
    max_nodes: int = 0
    cluster_dimension: str = ""
    cluster_key: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> WorkbenchFilters:
        """Build validated filters from a wire payload."""
        if not data:
            return cls()

        def values(key: str) -> tuple[str, ...]:
            raw = data.get(key, ())
            if raw is None:
                return ()
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, (list, tuple)):
                raise ValueError(f"{key} must be a list of strings")
            result: list[str] = []
            for item in raw:
                if not isinstance(item, str):
                    raise ValueError(f"{key} must be a list of strings")
                if item.strip():
                    result.append(item.strip().casefold())
            return tuple(sorted(set(result)))

        max_nodes = data.get("max_nodes", 0) or 0
        if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 0:
            raise ValueError("max_nodes must be a non-negative integer")
        query = data.get("query", "") or ""
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        dimension = str(data.get("cluster_dimension", "") or "").casefold()
        if dimension and dimension not in CLUSTER_DIMENSIONS:
            raise ValueError(f"Unknown cluster dimension: {dimension}")
        return cls(
            kinds=values("kinds"),
            tags=tuple(value.lstrip("#") for value in values("tags")),
            severities=values("severities"),
            query=query.strip().casefold(),
            max_nodes=max_nodes,
            cluster_dimension=dimension,
            cluster_key=str(data.get("cluster_key", "") or ""),
        )

    def apply(self, graph: WorkbenchGraph) -> WorkbenchGraph:
        """Return the filtered subgraph."""
        if self.cluster_dimension and self.cluster_key:
            graph = filter_by_cluster(
                graph, cluster_graph(graph, self.cluster_dimension), self.cluster_key
            )
        keep: list[str] = []
        for node_id in graph.node_ids:
            node = graph.node(node_id)
            if self.kinds and node.kind not in self.kinds:
                continue
            if self.severities and node.severity not in self.severities:
                continue
            if self.tags and not set(self.tags) & set(node.tag_set):
                continue
            if (
                self.query
                and self.query not in " ".join((node.title, node.summary, *node.tags)).casefold()
            ):
                continue
            keep.append(node_id)
        if self.max_nodes:
            keep = keep[: self.max_nodes]
        return graph.induced(frozenset(keep)) if len(keep) != len(graph) else graph

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "kinds": list(self.kinds),
            "tags": list(self.tags),
            "severities": list(self.severities),
            "query": self.query,
            "max_nodes": self.max_nodes,
            "cluster_dimension": self.cluster_dimension,
            "cluster_key": self.cluster_key,
        }


class GraphWorkbench:
    """Application service for analytical graph operations."""

    def __init__(
        self,
        entities: EntityService,
        *,
        bus: EventBus | None = None,
        capabilities: Capabilities | None = None,
        clock: Clock | None = None,
        snapshot_capacity: int = 16,
    ) -> None:
        self.entities = entities
        self.bus = bus
        self.capabilities = capabilities or Capabilities()
        self.clock: Clock = clock or SystemClock()
        self.editor = RelationshipEditor(
            entities,
            bus=bus,
            capabilities=self.capabilities,
            clock=self.clock,
        )
        self.snapshots = SnapshotStore(capacity=snapshot_capacity, clock=self.clock)

    def _require_capability(self) -> None:
        """Reject calls when the graph capability is disabled."""
        self.capabilities.require(CAP_GRAPH)

    def _emit(self, kind: str, **payload: Any) -> None:
        """Emit a workbench event when a bus is attached."""
        if self.bus is not None:
            self.bus.publish(make_event(kind, None, **payload))

    def graph(self, *, filters: WorkbenchFilters | None = None) -> WorkbenchGraph:
        """Build the current workbench graph, optionally filtered."""
        self._require_capability()
        graph = graph_from_entity_snapshot(self.entities.snapshot())
        return filters.apply(graph) if filters is not None else graph

    def layout(
        self,
        name: str = "force",
        *,
        options: LayoutOptions | None = None,
        filters: WorkbenchFilters | None = None,
    ) -> LayoutResult:
        """Compute a deterministic layout for the current graph."""
        graph = self.graph(filters=filters)
        result = compute_layout(graph, name, options)
        self._emit(
            "graph.layout.computed",
            strategy=result.strategy,
            seed=result.seed,
            nodes=len(result),
        )
        return result

    def clusters(
        self,
        dimension: str = "tag",
        *,
        tag_prefix: str = "",
        filters: WorkbenchFilters | None = None,
    ) -> ClusterResult:
        """Cluster the current graph along one dimension."""
        return cluster_graph(self.graph(filters=filters), dimension, tag_prefix=tag_prefix)

    def cluster_dashboard(self, *, filters: WorkbenchFilters | None = None) -> dict[str, Any]:
        """Return summary chips for every clustering dimension."""
        graph = self.graph(filters=filters)
        results = all_clusters(graph)
        return {
            "dimensions": list(CLUSTER_DIMENSIONS),
            "chips": {
                dimension: [dict(chip) for chip in cluster_chips(result)]
                for dimension, result in results.items()
            },
            "assignments": {dimension: result.assignments for dimension, result in results.items()},
        }

    def path(
        self,
        source: EntityId | str,
        target: EntityId | str,
        *,
        directed: bool = False,
        weighted: bool = False,
        max_hops: int | None = None,
        filters: WorkbenchFilters | None = None,
    ) -> PathResult:
        """Explain the shortest relationship path between two entities."""
        source_ref = str(source)
        target_ref = str(target)
        graph = self.graph(filters=filters)
        result = shortest_path(
            graph,
            source_ref,
            target_ref,
            directed=directed,
            weighted=weighted,
            max_hops=max_hops,
        )
        self._emit(
            "graph.path.explored",
            source=source_ref,
            target=target_ref,
            found=result.found,
            hops=result.hops,
        )
        return result

    def articulation(self, *, filters: WorkbenchFilters | None = None) -> dict[str, Any]:
        """Return cut vertices, bridges, and structural metrics."""
        graph = self.graph(filters=filters)
        return {
            "cut_vertices": [item.as_dict() for item in articulation_points(graph)],
            "bridges": [item.as_dict() for item in bridges(graph)],
            "components": [item.as_dict() for item in connected_components(graph)],
            "summary": structural_summary(graph),
        }

    def neighborhood(
        self,
        node_id: str,
        *,
        depth: int = 1,
        filters: WorkbenchFilters | None = None,
    ) -> dict[str, Any]:
        """Return the bounded neighborhood of one vertex."""
        return neighborhood(self.graph(filters=filters), node_id, depth=depth)

    def inspect(self, node_id: str) -> dict[str, Any]:
        """Return universal entity metadata for the inspector panel."""
        self._require_capability()
        graph = self.graph()
        node = graph.node(node_id)
        record = self.entities.get(node.entity_id)
        cluster_memberships: dict[str, str] = {}
        for dimension, result in all_clusters(graph).items():
            cluster_memberships[dimension] = result.key_for(node_id)
        return {
            "node": node.as_dict(),
            "entity": record.as_dict(),
            "degree": graph.degree(node_id),
            "neighbors": [
                {"id": key, "label": graph.node(key).label} for key in graph.neighbors(node_id)
            ],
            "clusters": cluster_memberships,
        }

    def overview(self, *, filters: WorkbenchFilters | None = None) -> dict[str, Any]:
        """Return a compact dashboard payload."""
        graph = self.graph(filters=filters)
        history = self.snapshots.payload(limit=5)
        return {
            "stats": graph.stats(),
            "structure": structural_summary(graph),
            "tags": graph.tag_counts(),
            "layouts": list(available_layouts()),
            "clusters": list(CLUSTER_DIMENSIONS),
            "snapshots": history["count"],
            "history": self.editor.history(limit=0),
        }

    def connect(
        self,
        source: EntityId | str,
        target: EntityId | str,
        **kwargs: Any,
    ) -> EditRecord:
        """Create a relationship through the undoable editor."""
        return self.editor.connect(source, target, **kwargs)

    def disconnect(
        self,
        source: EntityId | str,
        target: EntityId | str,
        **kwargs: Any,
    ) -> EditRecord:
        """Remove a relationship through the undoable editor."""
        return self.editor.disconnect(source, target, **kwargs)

    def update_relationship(
        self,
        source: EntityId | str,
        target: EntityId | str,
        **kwargs: Any,
    ) -> EditRecord:
        """Update a relationship through the undoable editor."""
        return self.editor.update(source, target, **kwargs)

    def undo(self) -> EditRecord | None:
        """Undo the last relationship edit."""
        return self.editor.undo()

    def redo(self) -> EditRecord | None:
        """Redo the last undone relationship edit."""
        return self.editor.redo()

    def history(self) -> dict[str, Any]:
        """Return editor history metadata."""
        return self.editor.history()

    def capture(self, *, label: str = "", source: str = "workbench") -> GraphSnapshot:
        """Capture a graph snapshot."""
        snapshot = self.snapshots.capture(self.graph(), label=label, source=source)
        self._emit("graph.snapshot.captured", snapshot_id=snapshot.meta.id)
        return snapshot

    def compare(self, left_id: str, right_id: str) -> SnapshotDiff:
        """Diff two stored snapshots."""
        return self.snapshots.compare(left_id, right_id)

    def export(
        self,
        fmt: str = "json",
        *,
        filters: WorkbenchFilters | None = None,
        clusters: ClusterResult | None = None,
        **kwargs: Any,
    ) -> ExportResult:
        """Export the current graph in a named grammar."""
        result = export_graph(self.graph(filters=filters), fmt, clusters=clusters, **kwargs)
        self._emit("graph.export.created", format=result.fmt, size=result.size)
        return result

    def tag_index(self, *, filters: WorkbenchFilters | None = None) -> dict[str, list[str]]:
        """Return a tag-to-node index for chip drill-down."""
        graph = self.graph(filters=filters)
        index: dict[str, list[str]] = defaultdict(list)
        for node_id in graph.node_ids:
            for tag in graph.node(node_id).tag_set:
                index[tag].append(node_id)
        return {key: sorted(value) for key, value in sorted(index.items())}
