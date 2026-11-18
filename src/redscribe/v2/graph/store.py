"""Indexed stores that turn vault notes into a typed graph model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.graph.extract import (
    TagOccurrence,
    extract_tags,
    extract_wikilinks,
    normalize_reference,
    reference_index,
)
from redscribe.v2.graph.model import (
    EDGE_LINK,
    EDGE_PARENT,
    EDGE_TAG,
    NODE_FOLDER,
    NODE_NOTE,
    NODE_REFERENCE,
    NODE_TAG,
    GraphEdge,
    GraphModel,
    GraphNode,
)

REFERENCE_ID_BASE = -1_000_000
TAG_ID_BASE = -2_000_000


@dataclass(slots=True)
class NodeStore:
    """Indexed collection of graph vertices."""

    _nodes: dict[int, GraphNode] = field(default_factory=dict)
    _by_kind: dict[str, set[int]] = field(default_factory=dict)
    _by_tag: dict[str, set[int]] = field(default_factory=dict)

    def add(self, node: GraphNode) -> GraphNode:
        """Add or replace a vertex while refreshing its indexes."""
        previous = self._nodes.get(node.id)
        if previous is not None:
            self._by_kind[previous.kind].discard(node.id)
            for tag in previous.tag_set:
                self._by_tag.get(tag, set()).discard(node.id)
        self._nodes[node.id] = node
        self._by_kind.setdefault(node.kind, set()).add(node.id)
        for tag in node.tag_set:
            self._by_tag.setdefault(tag, set()).add(node.id)
        return node

    def get(self, node_id: int) -> GraphNode | None:
        """Return one vertex by id."""
        return self._nodes.get(node_id)

    def has_node(self, node_id: int) -> bool:
        """Return whether a vertex exists."""
        return node_id in self._nodes

    def remove(self, node_id: int) -> GraphNode | None:
        """Remove a vertex and all of its index entries."""
        node = self._nodes.pop(node_id, None)
        if node is None:
            return None
        self._by_kind.get(node.kind, set()).discard(node_id)
        for tag in node.tag_set:
            self._by_tag.get(tag, set()).discard(node_id)
        return node

    def all(self) -> tuple[GraphNode, ...]:
        """Return every vertex in id order."""
        return tuple(self._nodes[node_id] for node_id in sorted(self._nodes))

    def of_kind(self, kind: str) -> tuple[GraphNode, ...]:
        """Return all vertices of one category."""
        ids = self._by_kind.get(kind, set())
        return tuple(self._nodes[node_id] for node_id in sorted(ids))

    def with_tag(self, tag: str) -> tuple[GraphNode, ...]:
        """Return all vertices carrying a tag (case-insensitive)."""
        ids = self._by_tag.get(tag.casefold(), set())
        return tuple(self._nodes[node_id] for node_id in sorted(ids))

    def tags(self) -> tuple[str, ...]:
        """Return all known tags in case-folded order."""
        return tuple(sorted(self._by_tag))

    def count(self) -> int:
        """Return the vertex count."""
        return len(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self._nodes


@dataclass(slots=True)
class EdgeStore:
    """Indexed collection of graph relationships."""

    _edges: dict[tuple[int, int, str], GraphEdge] = field(default_factory=dict)
    _outgoing: dict[int, set[int]] = field(default_factory=dict)
    _incoming: dict[int, set[int]] = field(default_factory=dict)

    def add(self, edge: GraphEdge) -> GraphEdge:
        """Add or replace one edge and refresh both adjacency indexes."""
        previous = self._edges.get(edge.key)
        if previous is not None:
            self._outgoing.get(previous.source, set()).discard(previous.target)
            self._incoming.get(previous.target, set()).discard(previous.source)
        self._edges[edge.key] = edge
        self._outgoing.setdefault(edge.source, set()).add(edge.target)
        self._incoming.setdefault(edge.target, set()).add(edge.source)
        return edge

    def remove(self, edge: GraphEdge | tuple[int, int, str]) -> GraphEdge | None:
        """Remove one edge by record or key."""
        key = edge.key if isinstance(edge, GraphEdge) else edge
        removed = self._edges.pop(key, None)
        if removed is None:
            return None
        self._outgoing.get(removed.source, set()).discard(removed.target)
        self._incoming.get(removed.target, set()).discard(removed.source)
        return removed

    def get(self, source: int, target: int, kind: str) -> GraphEdge | None:
        """Return one edge by its endpoint pair and category."""
        return self._edges.get((source, target, kind))

    def all(self) -> tuple[GraphEdge, ...]:
        """Return every edge in deterministic key order."""
        return tuple(self._edges[key] for key in sorted(self._edges))

    def outgoing(self, node_id: int) -> tuple[int, ...]:
        """Return outgoing targets in sorted order."""
        return tuple(sorted(self._outgoing.get(node_id, set())))

    def incoming(self, node_id: int) -> tuple[int, ...]:
        """Return incoming sources in sorted order."""
        return tuple(sorted(self._incoming.get(node_id, set())))

    def neighbors(self, node_id: int) -> tuple[int, ...]:
        """Return all adjacent vertices in sorted order."""
        return tuple(sorted({*self.outgoing(node_id), *self.incoming(node_id)}))

    def incident(self, node_id: int) -> tuple[GraphEdge, ...]:
        """Return edges that touch one vertex."""
        return tuple(
            edge for edge in self.all() if edge.source == node_id or edge.target == node_id
        )

    def remove_node(self, node_id: int) -> tuple[GraphEdge, ...]:
        """Remove every edge incident to a vertex."""
        removed: list[GraphEdge] = []
        for edge in self.incident(node_id):
            value = self.remove(edge)
            if value is not None:
                removed.append(value)
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)
        return tuple(removed)

    def degrees(self) -> dict[int, tuple[int, int]]:
        """Return ``{id: (in_degree, out_degree)}`` for every indexed vertex."""
        ids = set(self._outgoing) | set(self._incoming)
        return {
            node_id: (
                len(self._incoming.get(node_id, set())),
                len(self._outgoing.get(node_id, set())),
            )
            for node_id in sorted(ids)
        }

    def count(self) -> int:
        """Return the edge count."""
        return len(self._edges)

    def __len__(self) -> int:
        return len(self._edges)


@dataclass(slots=True)
class GraphStore:
    """A pair of node and edge indexes over one graph snapshot."""

    nodes: NodeStore = field(default_factory=NodeStore)
    edges: EdgeStore = field(default_factory=EdgeStore)

    @classmethod
    def from_model(cls, model: GraphModel) -> GraphStore:
        """Build stores from an existing model."""
        store = cls()
        for node in model.nodes.values():
            store.nodes.add(node)
        for edge in model.edges.values():
            store.edges.add(edge)
        return store

    def to_model(self) -> GraphModel:
        """Materialize a structural model view of the stores."""
        return GraphModel.from_records(list(self.nodes.all()), list(self.edges.all()))

    def add_node(self, node: GraphNode) -> GraphNode:
        """Add one vertex."""
        return self.nodes.add(node)

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add one edge, creating placeholder vertices when needed."""
        if not self.nodes.has_node(edge.source):
            self.nodes.add(GraphNode(id=edge.source, label="", resolved=False))
        if not self.nodes.has_node(edge.target):
            self.nodes.add(GraphNode(id=edge.target, label="", resolved=False))
        return self.edges.add(edge)

    def remove_node(self, node_id: int) -> GraphNode | None:
        """Remove a vertex and its incident edges."""
        self.edges.remove_node(node_id)
        return self.nodes.remove(node_id)

    def stats(self) -> dict[str, int]:
        """Return compact counts for the stored graph."""
        counts = {
            kind: len(self.nodes.of_kind(kind))
            for kind in (NODE_NOTE, NODE_FOLDER, NODE_REFERENCE, NODE_TAG)
        }
        return {
            "nodes": self.nodes.count(),
            "edges": self.edges.count(),
            "notes": counts[NODE_NOTE],
            "folders": counts[NODE_FOLDER],
            "references": counts[NODE_REFERENCE],
            "tags": counts[NODE_TAG],
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the stores."""
        return {
            "nodes": [node.as_dict() for node in self.nodes.all()],
            "edges": [edge.as_dict() for edge in self.edges.all()],
            "stats": self.stats(),
        }


def build_graph_store(vault: Vault) -> GraphStore:
    """Build a graph store from live vault folders, notes, links, and tags."""
    store = GraphStore()
    live = vault.live_nodes()
    paths = vault.paths_map(include_self=False)
    labels = [(node.id, node.title) for node in live if node.is_note]
    by_label = reference_index(labels)
    extracted_tags: dict[int, tuple[TagOccurrence, ...]] = {}

    for node in live:
        tags = extract_tags(node.content, stored=node.tags) if node.is_note else ()
        extracted_tags[node.id] = tags
        store.add_node(
            GraphNode(
                id=node.id,
                label=node.title,
                kind=NODE_NOTE if node.is_note else NODE_FOLDER,
                path=paths.get(node.id, ""),
                tags=tuple(item.value for item in tags),
                status=node.status,
                pinned=node.pinned,
                weight=2.0 if node.pinned else 1.0,
                metadata={
                    "flag": node.flag,
                    "target": node.target,
                    "updated_at": node.updated_at,
                },
            )
        )
        if node.parent_id is not None:
            store.add_edge(GraphEdge(source=node.parent_id, target=node.id, kind=EDGE_PARENT))

    tag_ids: dict[str, int] = {}
    for node in live:
        if not node.is_note:
            continue
        for occurrence in extract_wikilinks(node.content):
            target_id = by_label.get(occurrence.key)
            if target_id is not None and target_id != node.id:
                store.add_edge(
                    GraphEdge(
                        source=node.id,
                        target=target_id,
                        kind=EDGE_LINK,
                        alias=occurrence.display,
                        metadata={"line": occurrence.line},
                    )
                )
                continue
            reference_index_value = len(store.nodes.of_kind(NODE_REFERENCE))
            reference_id = REFERENCE_ID_BASE - reference_index_value
            existing = _reference_id(store, occurrence.key)
            if existing is not None:
                store.add_edge(
                    GraphEdge(
                        source=node.id,
                        target=existing,
                        kind=EDGE_LINK,
                        resolved=False,
                        alias=occurrence.display,
                        metadata={"line": occurrence.line},
                    )
                )
                continue
            store.add_node(
                GraphNode(
                    id=reference_id,
                    label=occurrence.display,
                    kind=NODE_REFERENCE,
                    resolved=False,
                    metadata={"target": occurrence.target},
                )
            )
            store.add_edge(
                GraphEdge(
                    source=node.id,
                    target=reference_id,
                    kind=EDGE_LINK,
                    resolved=False,
                    alias=occurrence.display,
                    metadata={"line": occurrence.line},
                )
            )

        for tag in extracted_tags[node.id]:
            key = tag.key
            if key not in tag_ids:
                tag_ids[key] = TAG_ID_BASE - len(tag_ids)
                store.add_node(
                    GraphNode(
                        id=tag_ids[key],
                        label=tag.value,
                        kind=NODE_TAG,
                        metadata={"source": tag.source},
                    )
                )
            store.add_edge(
                GraphEdge(
                    source=node.id,
                    target=tag_ids[key],
                    kind=EDGE_TAG,
                    metadata={"source": tag.source},
                )
            )
    return store


def _reference_id(store: GraphStore, key: str) -> int | None:
    """Find an existing unresolved reference vertex by normalized label."""
    for node in store.nodes.of_kind(NODE_REFERENCE):
        target = str(node.metadata.get("target", node.label))
        if normalize_reference(target) == key:
            return node.id
    return None
