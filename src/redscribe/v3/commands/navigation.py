"""Navigation graph and breadcrumb paths for the command center."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.commands.types import CommandContext
from redscribe.v3.entities.types import EntityRef

ROOT_ID = "vault"


class NavigationError(ValueError):
    """Raised for invalid navigation graph data."""


@dataclass(frozen=True, slots=True)
class NavNode:
    """One place or entity in the navigation graph."""

    id: str
    label: str
    kind: str = "place"
    parent: str = ""
    order: int = 100
    entity: EntityRef | None = None

    def __post_init__(self) -> None:
        if not self.id or len(self.id) > 160:
            raise NavigationError("Navigation node id must be 1-160 characters")
        if not self.label.strip():
            raise NavigationError("Navigation node label cannot be blank")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "parent": self.parent,
            "order": self.order,
            "entity": self.entity.as_dict() if self.entity is not None else None,
        }


@dataclass(frozen=True, slots=True)
class NavEdge:
    """A directed navigation edge with a traversal cost."""

    source: str
    target: str
    relation: str = "contains"
    cost: float = 1.0

    def __post_init__(self) -> None:
        if self.cost <= 0:
            raise NavigationError("Navigation edge cost must be positive")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "cost": self.cost,
        }


@dataclass(frozen=True, slots=True)
class NavPath:
    """A resolved navigation path."""

    nodes: tuple[str, ...]
    cost: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"nodes": list(self.nodes), "cost": round(self.cost, 4)}


@dataclass(slots=True)
class NavigationGraph:
    """Small deterministic graph with Dijkstra pathfinding."""

    _nodes: dict[str, NavNode] = field(default_factory=dict)
    _edges: list[NavEdge] = field(default_factory=list)

    def add_node(self, node: NavNode) -> NavNode:
        """Add or replace a navigation node."""
        self._nodes[node.id] = node
        return node

    def add_edge(self, edge: NavEdge) -> NavEdge:
        """Add a navigation edge, validating both endpoints."""
        if edge.source not in self._nodes or edge.target not in self._nodes:
            raise NavigationError("Navigation edge endpoints must exist")
        if edge.source == edge.target:
            raise NavigationError("Navigation edge cannot be self-referential")
        self._edges.append(edge)
        return edge

    def link(
        self, parent: str, child: str, *, relation: str = "contains", cost: float = 1.0
    ) -> NavEdge:
        """Link two existing nodes by id."""
        return self.add_edge(NavEdge(parent, child, relation, cost))

    def has(self, node_id: str) -> bool:
        """Return whether a node exists."""
        return node_id in self._nodes

    def node(self, node_id: str) -> NavNode:
        """Return a node or raise."""
        node = self._nodes.get(node_id)
        if node is None:
            raise NavigationError(f"Unknown navigation node: {node_id}")
        return node

    def children(self, node_id: str) -> tuple[NavNode, ...]:
        """Return direct children in display order."""
        self.node(node_id)
        targets = {edge.target for edge in self._edges if edge.source == node_id}
        return tuple(
            sorted(
                (self._nodes[target] for target in targets),
                key=lambda node: (node.order, node.id),
            )
        )

    def parents(self, node_id: str) -> tuple[NavNode, ...]:
        """Return direct parents in display order."""
        self.node(node_id)
        sources = {edge.source for edge in self._edges if edge.target == node_id}
        return tuple(
            sorted(
                (self._nodes[source] for source in sources),
                key=lambda node: (node.order, node.id),
            )
        )

    def path(self, start: str, goal: str) -> NavPath:
        """Find the lowest-cost path between two nodes."""
        self.node(start)
        self.node(goal)
        if start == goal:
            return NavPath((start,), 0.0)
        adjacency: dict[str, list[tuple[str, float]]] = {}
        for edge in self._edges:
            adjacency.setdefault(edge.source, []).append((edge.target, edge.cost))
        distances: dict[str, float] = {start: 0.0}
        previous: dict[str, str] = {}
        queue: list[tuple[float, str]] = [(0.0, start)]
        while queue:
            distance, current = heapq.heappop(queue)
            if distance > distances.get(current, float("inf")):
                continue
            if current == goal:
                break
            for target, cost in sorted(adjacency.get(current, ()), key=lambda item: item[0]):
                candidate = distance + cost
                if candidate < distances.get(target, float("inf")):
                    distances[target] = candidate
                    previous[target] = current
                    heapq.heappush(queue, (candidate, target))
        if goal not in distances:
            raise NavigationError(f"No path from '{start}' to '{goal}'")
        nodes = [goal]
        while nodes[-1] != start:
            nodes.append(previous[nodes[-1]])
        nodes.reverse()
        return NavPath(tuple(nodes), distances[goal])

    def breadcrumbs(self, goal: str, *, root: str = ROOT_ID) -> tuple[NavNode, ...]:
        """Return the trail from a root to a node."""
        path = self.path(root, goal)
        return tuple(self.node(node_id) for node_id in path.nodes)

    def subtree(self, node_id: str) -> tuple[NavNode, ...]:
        """Return all descendants of a node in breadth-first order."""
        self.node(node_id)
        seen: set[str] = {node_id}
        ordered: list[NavNode] = []
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            for child in self.children(current):
                if child.id in seen:
                    continue
                seen.add(child.id)
                ordered.append(child)
                queue.append(child.id)
        return tuple(ordered)

    def neighbors(self, node_id: str, *, limit: int = 8) -> tuple[NavNode, ...]:
        """Return nearby nodes for quick pivot navigation."""
        if limit < 1:
            raise NavigationError("limit must be positive")
        related = {node.id for node in self.parents(node_id)}
        related.update(node.id for node in self.children(node_id))
        return tuple(
            sorted(
                (self._nodes[item] for item in related),
                key=lambda node: (node.order, node.id),
            )[:limit]
        )

    def for_context(self, context: CommandContext) -> tuple[NavNode, ...]:
        """Return navigation targets relevant to a command context."""
        candidates = [context.entity_ref, *context.selection_refs]
        nodes: list[NavNode] = []
        for candidate in candidates:
            ref = _ref_for(candidate)
            if ref is not None and self.has(ref):
                nodes.append(self.node(ref))
        return tuple(nodes)

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable graph snapshot."""
        return {
            "nodes": [node.as_dict() for node in sorted(self._nodes.values(), key=lambda n: n.id)],
            "edges": [edge.as_dict() for edge in self._edges],
        }

    def load(self, snapshot: dict[str, Any]) -> None:
        """Restore a graph snapshot."""
        raw_nodes = snapshot.get("nodes", ())
        raw_edges = snapshot.get("edges", ())
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise NavigationError("Navigation snapshot needs node and edge lists")
        self._nodes = {}
        self._edges = []
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                raise NavigationError("Navigation node must be an object")
            ref = raw.get("entity")
            entity = (
                EntityRef.of(str(ref["kind"]), str(ref["value"]), str(ref.get("label", "")))
                if isinstance(ref, dict)
                else None
            )
            self.add_node(
                NavNode(
                    id=str(raw.get("id", "")),
                    label=str(raw.get("label", "")),
                    kind=str(raw.get("kind", "place")),
                    parent=str(raw.get("parent", "")),
                    order=int(raw.get("order", 100)),
                    entity=entity,
                )
            )
        for raw in raw_edges:
            if not isinstance(raw, dict):
                raise NavigationError("Navigation edge must be an object")
            self.add_edge(
                NavEdge(
                    source=str(raw.get("source", "")),
                    target=str(raw.get("target", "")),
                    relation=str(raw.get("relation", "contains")),
                    cost=float(raw.get("cost", 1.0)),
                )
            )

    def size(self) -> tuple[int, int]:
        """Return the node and edge counts."""
        return len(self._nodes), len(self._edges)


def _ref_for(value: str) -> str | None:
    """Map a context ref to a graph node id."""
    return value or None


def register_core_navigation(graph: NavigationGraph) -> NavigationGraph:
    """Populate the navigation graph that ships with the command center."""
    nodes = (
        NavNode(ROOT_ID, "Vault", order=0),
        NavNode("pane:main", "Main workspace", parent=ROOT_ID, order=10),
        NavNode("pane:secondary", "Secondary workspace", parent=ROOT_ID, order=20),
        NavNode("folder:engagements", "Engagements", parent=ROOT_ID, order=30),
        NavNode("findings", "Findings", parent=ROOT_ID, order=40),
        NavNode("evidence", "Evidence", parent=ROOT_ID, order=50),
        NavNode("reports", "Reports", parent=ROOT_ID, order=60),
    )
    for node in nodes:
        graph.add_node(node)
    for parent, child in (
        (ROOT_ID, "pane:main"),
        (ROOT_ID, "pane:secondary"),
        (ROOT_ID, "folder:engagements"),
        (ROOT_ID, "findings"),
        (ROOT_ID, "evidence"),
        (ROOT_ID, "reports"),
        ("folder:engagements", "findings"),
    ):
        graph.link(parent, child)
    return graph


def default_navigation() -> NavigationGraph:
    """Build a navigation graph with the core places registered."""
    return register_core_navigation(NavigationGraph())
