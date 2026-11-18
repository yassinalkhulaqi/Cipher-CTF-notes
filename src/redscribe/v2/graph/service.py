"""Facade service that composes the graph-intelligence subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.graph.algorithms import (
    average_clustering,
    betweenness_centrality,
    closeness_centrality,
    clustering_coefficients,
    connected_components,
    degree_centrality,
    detect_communities,
    eigenvector_centrality,
    find_cycles,
    graph_metrics,
    shortest_path,
)
from redscribe.v2.graph.extract import normalize_reference
from redscribe.v2.graph.links import LinkService
from redscribe.v2.graph.model import (
    EDGE_KINDS,
    NODE_KINDS,
    GraphModel,
)
from redscribe.v2.graph.recommend import RecommendationService
from redscribe.v2.graph.snapshot import GraphSnapshot, SnapshotStore
from redscribe.v2.graph.store import GraphStore, build_graph_store

MEASURES = ("degree", "closeness", "betweenness", "eigenvector")


@dataclass(frozen=True, slots=True)
class GraphFilters:
    """Declarative filters applied to a graph model."""

    kinds: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    query: str = ""
    max_nodes: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> GraphFilters:
        """Build validated filters from an API-style dictionary."""
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
                    result.append(item.strip())
            return tuple(result)

        kinds = values("kinds")
        invalid = [kind for kind in kinds if kind not in NODE_KINDS]
        if invalid:
            raise ValueError(f"Unknown node kind: {invalid[0]}")
        max_nodes = data.get("max_nodes", 0) or 0
        if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 0:
            raise ValueError("max_nodes must be a non-negative integer")
        query = data.get("query", "") or ""
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        return cls(
            kinds=kinds,
            tags=tuple(value.casefold().lstrip("#") for value in values("tags")),
            statuses=values("statuses"),
            query=query.strip().casefold(),
            max_nodes=max_nodes,
        )

    def matches(self, label: str, tags: tuple[str, ...], status: str, kind: str) -> bool:
        """Return whether one vertex satisfies every filter."""
        if self.kinds:
            if kind not in self.kinds:
                return False
        elif kind != "note":
            return False
        if self.statuses and status not in self.statuses:
            return False
        if self.tags:
            folded = frozenset(tag.casefold().lstrip("#") for tag in tags)
            if not any(tag in folded for tag in self.tags):
                return False
        return not (self.query and self.query not in label.casefold())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "kinds": list(self.kinds),
            "tags": list(self.tags),
            "statuses": list(self.statuses),
            "query": self.query,
            "max_nodes": self.max_nodes,
        }


@dataclass(slots=True)
class GraphIntelligenceService:
    """Vault-backed facade for graph construction, analysis, and snapshots."""

    vault: Vault
    _store: GraphStore | None = field(default=None, repr=False)
    _snapshots: SnapshotStore = field(default_factory=SnapshotStore, repr=False)

    def store(self, *, refresh: bool = False) -> GraphStore:
        """Return the lazily built graph store."""
        if self._store is None or refresh:
            self._store = build_graph_store(self.vault)
        return self._store

    def links(self) -> LinkService:
        """Build a link service over the current graph."""
        store = self.store()
        contents = {node.id: node.content for node in self.vault.live_nodes() if node.is_note}
        return LinkService(store, contents)

    def recommendations(self) -> RecommendationService:
        """Build a recommendation service over the current graph."""
        return RecommendationService(self.store())

    def model(self, *, filters: GraphFilters | None = None) -> GraphModel:
        """Return the current model, optionally filtered."""
        model = self.store().to_model()
        if filters is None:
            return model
        kept = [
            node_id
            for node_id in sorted(model.nodes)
            if filters.matches(
                model.nodes[node_id].label,
                model.nodes[node_id].tags,
                model.nodes[node_id].status,
                model.nodes[node_id].kind,
            )
        ]
        if filters.max_nodes:
            kept = kept[: filters.max_nodes]
        return model.induced(frozenset(kept))

    def overview(self) -> dict[str, Any]:
        """Return structural counts and metrics for the full graph."""
        store = self.store()
        model = store.to_model()
        metrics = graph_metrics(model)
        return {
            "stats": store.stats(),
            "metrics": metrics,
            "tags": list(store.nodes.tags()),
            "snapshot_count": len(self._snapshots.list()),
        }

    def nodes(self, *, filters: GraphFilters | None = None) -> list[dict[str, Any]]:
        """Return serialized vertices, optionally filtered."""
        model = self.model(filters=filters)
        return [model.nodes[node_id].as_dict() for node_id in sorted(model.nodes)]

    def edges(
        self,
        *,
        filters: GraphFilters | None = None,
        kinds: tuple[str, ...] = EDGE_KINDS,
    ) -> list[dict[str, Any]]:
        """Return serialized edges whose endpoints survive filtering."""
        model = self.model(filters=filters)
        allowed = frozenset(kinds)
        return [
            model.edges[key].as_dict()
            for key in sorted(model.edges)
            if model.edges[key].kind in allowed
        ]

    def neighbors(
        self,
        node_id: int,
        *,
        depth: int = 1,
        kinds: tuple[str, ...] = EDGE_KINDS,
    ) -> dict[str, Any]:
        """Return the neighborhood of a vertex up to a bounded depth."""
        if depth < 1 or depth > 5:
            raise ValueError("depth must be between 1 and 5")
        store = self.store()
        if not store.nodes.has_node(node_id):
            raise ValueError("Node does not exist")
        model = store.to_model()
        current = {node_id}
        visited = {node_id}
        for _ in range(depth):
            following: set[int] = set()
            for item in current:
                following.update(model.neighbors(item, kinds=kinds))
            following -= visited
            visited.update(following)
            current = following
            if not current:
                break
        ordered = tuple(sorted(visited))
        return {
            "node_id": node_id,
            "depth": depth,
            "nodes": [model.nodes[item].as_dict() for item in ordered],
            "edges": [
                model.edges[key].as_dict()
                for key in sorted(model.edges)
                if model.edges[key].source in visited and model.edges[key].target in visited
            ],
        }

    def centrality(self, measure: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return one ranked centrality measure."""
        if measure not in MEASURES:
            raise ValueError(f"Unknown centrality measure: {measure}")
        if limit < 1:
            raise ValueError("limit must be positive")
        model = self.store().to_model()
        scores = {
            "degree": degree_centrality,
            "closeness": closeness_centrality,
            "betweenness": betweenness_centrality,
            "eigenvector": eigenvector_centrality,
        }[measure](model)
        return [item.as_dict() for item in scores[:limit]]

    def clustering(self) -> dict[str, Any]:
        """Return local clustering coefficients and the graph average."""
        model = self.store().to_model()
        scores = clustering_coefficients(model)
        return {
            "average": average_clustering(model),
            "scores": [item.as_dict() for item in scores],
        }

    def components(self, *, min_size: int = 1) -> list[dict[str, Any]]:
        """Return connected components of the graph."""
        return [
            item.as_dict()
            for item in connected_components(self.store().to_model(), min_size=min_size)
        ]

    def communities(self) -> list[dict[str, Any]]:
        """Return detected communities."""
        return [item.as_dict() for item in detect_communities(self.store().to_model())]

    def cycles(self, *, limit: int = 25) -> list[dict[str, Any]]:
        """Return discovered simple cycles."""
        return [item.as_dict() for item in find_cycles(self.store().to_model(), limit=limit)]

    def path(
        self,
        source: int,
        target: int,
        *,
        weighted: bool = False,
        directed: bool = False,
        max_hops: int | None = None,
    ) -> dict[str, Any] | None:
        """Return the shortest path between two vertices, if any."""
        model = self.store().to_model()
        if source not in model.nodes or target not in model.nodes:
            return None
        result = shortest_path(
            model,
            source,
            target,
            weighted=weighted,
            directed=directed,
            max_hops=max_hops,
        )
        return result.as_dict() if result is not None else None

    def resolve_label(self, label: str) -> int | None:
        """Resolve a wikilink-style label to a note id."""
        key = normalize_reference(label)
        for node in self.store().nodes.of_kind("note"):
            if normalize_reference(node.label) == key:
                return node.id
        return None

    def capture(self, *, label: str = "", source: str = "vault") -> GraphSnapshot:
        """Capture a graph snapshot."""
        return self._snapshots.capture(
            self.store(refresh=True).to_model(), label=label, source=source
        )

    def snapshots(self, *, limit: int = 20) -> dict[str, Any]:
        """Return snapshot history metadata."""
        return self._snapshots.payload(limit=limit)

    def snapshot(self, snapshot_id: str) -> GraphSnapshot:
        """Return one stored snapshot."""
        return self._snapshots.require(snapshot_id)

    def diff(self, left_id: str, right_id: str) -> dict[str, Any]:
        """Diff two stored snapshots."""
        return self._snapshots.compare(left_id, right_id).as_dict()

    def delete_snapshot(self, snapshot_id: str) -> str:
        """Delete a stored snapshot and return its id."""
        snapshot = self._snapshots.require(snapshot_id)
        self._snapshots.delete(snapshot_id)
        return snapshot.meta.id

    def insights(self, *, limit: int = 10) -> dict[str, Any]:
        """Return the combined intelligence dashboard payload."""
        store = self.store()
        model = store.to_model()
        recommendations = self.recommendations()
        links = self.links()
        return {
            "overview": self.overview(),
            "centrality": [item.as_dict() for item in degree_centrality(model)[:limit]],
            "components": [
                item.as_dict() for item in connected_components(model, min_size=2)[:limit]
            ],
            "communities": [item.as_dict() for item in detect_communities(model)[:limit]],
            "clusters": [item.as_dict() for item in clustering_coefficients(model)[:limit]],
            "recommendations": [
                item.as_dict() for item in recommendations.missing_links(limit=limit)
            ],
            "dangling": [item.as_dict() for item in links.dangling()[:limit]],
        }

    def layout(self, *, filters: GraphFilters | None = None) -> dict[str, Any]:
        """Return a node/edge payload suitable for layout algorithms."""
        model = self.model(filters=filters)
        return {
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "kind": node.kind,
                    "tags": list(node.tags),
                    "weight": node.weight,
                }
                for node in model.nodes.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "kind": edge.kind,
                    "weight": edge.weight,
                }
                for edge in model.edges.values()
            ],
        }
