"""Typed graph model for the V2 graph-intelligence package.

The model is intentionally independent from the vault storage layer. A
:class:`GraphModel` holds immutable vertex and edge records inside mutable
indexes, which lets the analysis services share one representation while still
returning stable values to callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

NODE_NOTE = "note"
NODE_FOLDER = "folder"
NODE_REFERENCE = "reference"
NODE_TAG = "tag"

NODE_KINDS: tuple[str, ...] = (NODE_NOTE, NODE_FOLDER, NODE_REFERENCE, NODE_TAG)

EDGE_PARENT = "parent"
EDGE_LINK = "link"
EDGE_TAG = "tag"
EDGE_MENTION = "mention"

EDGE_KINDS: tuple[str, ...] = (EDGE_PARENT, EDGE_LINK, EDGE_TAG, EDGE_MENTION)

DEFAULT_STATUS = "todo"


class NodeKind(str, Enum):
    """Vertex categories used by the graph model."""

    NOTE = NODE_NOTE
    FOLDER = NODE_FOLDER
    REFERENCE = NODE_REFERENCE
    TAG = NODE_TAG


class EdgeKind(str, Enum):
    """Relationship categories used by the graph model."""

    PARENT = EDGE_PARENT
    LINK = EDGE_LINK
    TAG = EDGE_TAG
    MENTION = EDGE_MENTION


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One immutable vertex in a graph snapshot."""

    id: int
    label: str = ""
    kind: str = NODE_NOTE
    path: str = ""
    tags: tuple[str, ...] = ()
    status: str = DEFAULT_STATUS
    pinned: bool = False
    resolved: bool = True
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in NODE_KINDS:
            raise ValueError(f"Unknown graph node kind: {self.kind}")
        if self.weight < 0:
            raise ValueError("Node weight cannot be negative")

    @property
    def title(self) -> str:
        """Display title of the vertex."""
        return self.label

    @property
    def tag_set(self) -> frozenset[str]:
        """Case-folded tags for fast overlap checks."""
        return frozenset(tag.casefold() for tag in self.tags)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the vertex."""
        return {
            "id": self.id,
            "label": self.label,
            "title": self.title,
            "kind": self.kind,
            "path": self.path,
            "tags": list(self.tags),
            "status": self.status,
            "pinned": self.pinned,
            "resolved": self.resolved,
            "weight": self.weight,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One immutable relationship between two vertices."""

    source: int
    target: int
    kind: str = EDGE_LINK
    weight: float = 1.0
    resolved: bool = True
    alias: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in EDGE_KINDS:
            raise ValueError(f"Unknown graph edge kind: {self.kind}")
        if self.weight < 0:
            raise ValueError("Edge weight cannot be negative")

    @property
    def key(self) -> tuple[int, int, str]:
        """Identity used by the edge store."""
        return (self.source, self.target, self.kind)

    @property
    def undirected_key(self) -> tuple[int, int, str]:
        """Canonical identity for undirected analyses."""
        left, right = sorted((self.source, self.target))
        return (left, right, self.kind)

    def reversed(self) -> GraphEdge:
        """Return the same relationship with source and target swapped."""
        return GraphEdge(
            source=self.target,
            target=self.source,
            kind=self.kind,
            weight=self.weight,
            resolved=self.resolved,
            alias=self.alias,
            metadata=dict(self.metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the edge."""
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "weight": self.weight,
            "resolved": self.resolved,
            "alias": self.alias,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class GraphModel:
    """Mutable indexes over immutable graph records."""

    nodes: dict[int, GraphNode] = field(default_factory=dict)
    edges: dict[tuple[int, int, str], GraphEdge] = field(default_factory=dict)

    @classmethod
    def from_records(
        cls,
        nodes: list[GraphNode] | tuple[GraphNode, ...],
        edges: list[GraphEdge] | tuple[GraphEdge, ...] = (),
    ) -> GraphModel:
        """Build a model from vertex and edge records."""
        model = cls()
        for node in nodes:
            model.upsert_node(node)
        for edge in edges:
            model.upsert_edge(edge)
        return model

    @property
    def size(self) -> int:
        """Number of vertices."""
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """Number of relationships."""
        return len(self.edges)

    def upsert_node(self, node: GraphNode) -> None:
        """Insert or replace one vertex."""
        self.nodes[node.id] = node

    def remove_node(self, node_id: int) -> GraphNode | None:
        """Remove a vertex and every incident edge."""
        node = self.nodes.pop(node_id, None)
        if node is None:
            return None
        for key in [
            key
            for key, edge in self.edges.items()
            if edge.source == node_id or edge.target == node_id
        ]:
            del self.edges[key]
        return node

    def upsert_edge(self, edge: GraphEdge) -> None:
        """Insert or replace one edge, creating missing vertices lazily."""
        for node_id, label in ((edge.source, ""), (edge.target, "")):
            if node_id not in self.nodes:
                self.upsert_node(GraphNode(id=node_id, label=label, resolved=edge.resolved))
        self.edges[edge.key] = edge

    def remove_edge(self, edge: GraphEdge | tuple[int, int, str]) -> GraphEdge | None:
        """Remove one edge by record or key."""
        key = edge.key if isinstance(edge, GraphEdge) else edge
        return self.edges.pop(key, None)

    def has_node(self, node_id: int) -> bool:
        """Return whether a vertex exists."""
        return node_id in self.nodes

    def get_node(self, node_id: int) -> GraphNode | None:
        """Return one vertex by id."""
        return self.nodes.get(node_id)

    def outgoing(self, node_id: int, *, kinds: tuple[str, ...] = EDGE_KINDS) -> tuple[int, ...]:
        """Return targets of outgoing edges of the requested kinds."""
        allowed = frozenset(kinds)
        targets = {
            edge.target
            for edge in self.edges.values()
            if edge.source == node_id and edge.kind in allowed
        }
        return tuple(sorted(targets))

    def incoming(self, node_id: int, *, kinds: tuple[str, ...] = EDGE_KINDS) -> tuple[int, ...]:
        """Return sources of incoming edges of the requested kinds."""
        allowed = frozenset(kinds)
        sources = {
            edge.source
            for edge in self.edges.values()
            if edge.target == node_id and edge.kind in allowed
        }
        return tuple(sorted(sources))

    def neighbors(
        self,
        node_id: int,
        *,
        kinds: tuple[str, ...] = EDGE_KINDS,
        directed: bool = False,
    ) -> tuple[int, ...]:
        """Return adjacent vertex ids in deterministic order."""
        if not directed:
            allowed = frozenset(kinds)
            found = {
                other
                for edge in self.edges.values()
                if edge.kind in allowed and node_id in (edge.source, edge.target)
                for other in (edge.target, edge.source)
                if other != node_id
            }
            return tuple(sorted(found))
        return tuple(
            sorted({*self.outgoing(node_id, kinds=kinds), *self.incoming(node_id, kinds=kinds)})
        )

    def edges_for(
        self, node_id: int, *, kinds: tuple[str, ...] = EDGE_KINDS
    ) -> tuple[GraphEdge, ...]:
        """Return all edges incident to one vertex."""
        allowed = frozenset(kinds)
        found = [
            edge
            for edge in self.edges.values()
            if edge.kind in allowed and node_id in (edge.source, edge.target)
        ]
        found.sort(key=lambda edge: (edge.source, edge.target, edge.kind))
        return tuple(found)

    def nodes_of_kind(self, kind: str) -> tuple[GraphNode, ...]:
        """Return vertices of one kind in id order."""
        return tuple(
            self.nodes[node_id]
            for node_id in sorted(self.nodes)
            if self.nodes[node_id].kind == kind
        )

    def induced(self, node_ids: frozenset[int] | set[int]) -> GraphModel:
        """Return a model restricted to the given vertices."""
        nodes = {node_id: self.nodes[node_id] for node_id in node_ids if node_id in self.nodes}
        edges = {
            key: edge
            for key, edge in self.edges.items()
            if edge.source in nodes and edge.target in nodes
        }
        return GraphModel(nodes=nodes, edges=edges)

    def copy(self) -> GraphModel:
        """Return a shallow structural copy of the model."""
        return GraphModel(nodes=dict(self.nodes), edges=dict(self.edges))

    def validate(self) -> tuple[str, ...]:
        """Return human-readable integrity problems found in the model."""
        problems: list[str] = []
        for edge in sorted(self.edges.values(), key=lambda item: item.key):
            if edge.source not in self.nodes:
                problems.append(f"edge {edge.key} has unknown source")
            if edge.target not in self.nodes:
                problems.append(f"edge {edge.key} has unknown target")
            if edge.source == edge.target:
                problems.append(f"edge {edge.key} is a self loop")
        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]
            if node.id != node_id:
                problems.append(f"node key {node_id} does not match id {node.id}")
        return tuple(problems)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the whole model."""
        return {
            "nodes": [self.nodes[node_id].as_dict() for node_id in sorted(self.nodes)],
            "edges": [self.edges[key].as_dict() for key in sorted(self.edges)],
        }
