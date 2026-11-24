"""Pathfinding and structural analysis for the graph workbench.

All traversals treat relationships as undirected by default because analysts
usually ask "how are these two things connected?" rather than "which way does
the arrow point?". Directed traversal is available for provenance questions.
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.graph_workbench.model import WorkbenchEdge, WorkbenchGraph

Adjacency = dict[str, dict[str, WorkbenchEdge]]


def build_adjacency(
    graph: WorkbenchGraph,
    *,
    directed: bool = False,
    kinds: tuple[str, ...] = (),
) -> Adjacency:
    """Build a deterministic, edge-labeled adjacency map."""
    allowed = frozenset(kinds)
    result: Adjacency = {key: {} for key in graph.node_ids}
    for key in graph.edge_keys:
        edge = graph.edges[key]
        if allowed and edge.kind.value not in allowed:
            continue
        source, target = edge.source, edge.target
        if source not in result or target not in result:
            continue
        pairs = ((source, target), (target, source)) if not directed else ((source, target),)
        for left, right in pairs:
            current = result[left].get(right)
            if current is None or (edge.weight, key) < (current.weight, current.key):
                result[left][right] = edge
    return result


@dataclass(frozen=True, slots=True)
class PathStep:
    """One explained hop in a relationship path."""

    index: int
    source: str
    target: str
    kind: str
    label: str
    weight: float
    direction: str
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "index": self.index,
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "label": self.label,
            "weight": self.weight,
            "direction": self.direction,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class PathResult:
    """A shortest path plus human-readable reasoning for every step."""

    source: str
    target: str
    node_ids: tuple[str, ...] = ()
    steps: tuple[PathStep, ...] = ()
    cost: float = 0.0
    directed: bool = False
    weighted: bool = False
    max_hops: int | None = None

    @property
    def found(self) -> bool:
        """Return whether a path exists (or endpoints coincide)."""
        return bool(self.node_ids)

    @property
    def hops(self) -> int:
        """Return the number of traversed relationships."""
        return max(len(self.node_ids) - 1, 0)

    def explanations(self) -> tuple[str, ...]:
        """Return the step explanation strings in traversal order."""
        return tuple(step.explanation for step in self.steps)

    def labels(self, graph: WorkbenchGraph) -> tuple[str, ...]:
        """Return display labels for each node on the path."""
        return tuple(graph.node(key).label for key in self.node_ids)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": self.source,
            "target": self.target,
            "found": self.found,
            "node_ids": list(self.node_ids),
            "steps": [step.as_dict() for step in self.steps],
            "explanations": list(self.explanations()),
            "hops": self.hops,
            "cost": round(self.cost, 6),
            "directed": self.directed,
            "weighted": self.weighted,
            "max_hops": self.max_hops,
        }


def _step_explanation(
    graph: WorkbenchGraph,
    edge: WorkbenchEdge,
    source: str,
    target: str,
    index: int,
) -> str:
    """Describe one hop in analyst-friendly language."""
    origin = graph.node(source).label
    destination = graph.node(target).label
    relation = edge.label or edge.kind.value
    direction = "points to" if edge.source == source else "is referenced by"
    return (
        f"Step {index}: {origin} {direction} {destination} "
        f"via {relation} (weight {edge.weight:.2f})"
    )


def shortest_path(
    graph: WorkbenchGraph,
    source: str,
    target: str,
    *,
    directed: bool = False,
    weighted: bool = False,
    max_hops: int | None = None,
) -> PathResult:
    """Find a deterministic shortest path and explain each hop.

    Ties are broken by node key so repeated computations yield identical
    explanations. Higher link weights represent stronger relationships and
    therefore lower traversal cost in weighted mode.
    """
    graph.node(source)
    graph.node(target)
    if max_hops is not None and max_hops < 0:
        raise ValueError("max_hops cannot be negative")
    result = PathResult(
        source=source,
        target=target,
        directed=directed,
        weighted=weighted,
        max_hops=max_hops,
    )
    if source == target:
        return PathResult(
            source=source,
            target=target,
            node_ids=(source,),
            directed=directed,
            weighted=weighted,
            max_hops=max_hops,
        )
    adjacency = build_adjacency(graph, directed=directed)
    costs: dict[str, float] = {source: 0.0}
    hops: dict[str, int] = {source: 0}
    previous: dict[str, tuple[str, WorkbenchEdge]] = {}
    queue: list[tuple[float, str]] = [(0.0, source)]
    while queue:
        cost, current = heapq.heappop(queue)
        if cost > costs.get(current, float("inf")):
            continue
        if current == target:
            break
        if max_hops is not None and hops[current] >= max_hops:
            continue
        for neighbor in sorted(adjacency[current]):
            if neighbor == source:
                continue
            edge = adjacency[current][neighbor]
            step_cost = 1.0 / max(edge.weight, 0.05) if weighted else 1.0
            candidate = cost + step_cost
            candidate_hops = hops[current] + 1
            if candidate > costs.get(neighbor, float("inf")) + 1e-12:
                continue
            if (
                neighbor in costs
                and candidate >= costs[neighbor] - 1e-12
                and (candidate_hops, current) >= (hops[neighbor], previous[neighbor][0])
            ):
                continue
            costs[neighbor] = candidate
            hops[neighbor] = candidate_hops
            previous[neighbor] = (current, edge)
            heapq.heappush(queue, (candidate, neighbor))
    if target not in previous:
        return result
    chain: list[str] = [target]
    edges: list[WorkbenchEdge] = []
    cursor = target
    while cursor != source:
        parent, edge = previous[cursor]
        edges.append(edge)
        chain.append(parent)
        cursor = parent
    chain.reverse()
    edges.reverse()
    steps: list[PathStep] = []
    for index, (left, right, edge) in enumerate(
        zip(chain[:-1], chain[1:], edges, strict=True), start=1
    ):
        steps.append(
            PathStep(
                index=index,
                source=left,
                target=right,
                kind=edge.kind.value,
                label=edge.label,
                weight=edge.weight,
                direction="forward" if edge.source == left else "reverse",
                explanation=_step_explanation(graph, edge, left, right, index),
            )
        )
    return PathResult(
        source=source,
        target=target,
        node_ids=tuple(chain),
        steps=tuple(steps),
        cost=float(costs[target]),
        directed=directed,
        weighted=weighted,
        max_hops=max_hops,
    )


@dataclass(frozen=True, slots=True)
class Component:
    """One undirected connected component."""

    index: int
    node_ids: tuple[str, ...]
    size: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "index": self.index,
            "node_ids": list(self.node_ids),
            "size": self.size,
        }


def connected_components(graph: WorkbenchGraph) -> tuple[Component, ...]:
    """Return components ordered by size, then by first member."""
    adjacency = build_adjacency(graph)
    visited: set[str] = set()
    groups: list[tuple[str, ...]] = []
    for start in graph.node_ids:
        if start in visited:
            continue
        visited.add(start)
        queue = deque([start])
        members: list[str] = []
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        groups.append(tuple(sorted(members)))
    groups.sort(key=lambda group: (-len(group), group))
    return tuple(
        Component(index=index, node_ids=group, size=len(group))
        for index, group in enumerate(groups, start=1)
    )


@dataclass(frozen=True, slots=True)
class CutVertex:
    """An articulation point and the fragments it separates."""

    node_id: str
    label: str
    fragments: tuple[tuple[str, ...], ...] = ()
    severity: str = "medium"

    @property
    def component_count(self) -> int:
        """Return the number of fragments after removal."""
        return len(self.fragments)

    @property
    def isolated_count(self) -> int:
        """Return the number of singletons created by removal."""
        return sum(1 for fragment in self.fragments if len(fragment) == 1)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "node_id": self.node_id,
            "label": self.label,
            "component_count": self.component_count,
            "isolated_count": self.isolated_count,
            "fragments": [list(fragment) for fragment in self.fragments],
            "severity": self.severity,
        }


@dataclass(slots=True)
class _Tarjan:
    """Iterative low-link traversal state."""

    discovery: dict[str, int] = field(default_factory=dict)
    low: dict[str, int] = field(default_factory=dict)
    parent: dict[str, str] = field(default_factory=dict)
    children: dict[str, int] = field(default_factory=dict)
    roots: dict[str, str] = field(default_factory=dict)
    timer: int = 0


def _tarjan(graph: WorkbenchGraph, adjacency: Adjacency) -> _Tarjan:
    """Compute discovery times, low links, and tree edges iteratively."""
    state = _Tarjan()
    for start in graph.node_ids:
        if start in state.discovery:
            continue
        state.discovery[start] = state.low[start] = state.timer
        state.timer += 1
        state.roots[start] = start
        stack: list[tuple[str, tuple[str, ...], int]] = [
            (start, tuple(sorted(adjacency[start])), 0)
        ]
        while stack:
            node, neighbors, index = stack[-1]
            if index < len(neighbors):
                neighbor = neighbors[index]
                stack[-1] = (node, neighbors, index + 1)
                if neighbor not in state.discovery:
                    state.parent[neighbor] = node
                    state.children[node] = state.children.get(node, 0) + 1
                    state.roots[neighbor] = state.roots[node]
                    state.discovery[neighbor] = state.low[neighbor] = state.timer
                    state.timer += 1
                    stack.append((neighbor, tuple(sorted(adjacency[neighbor])), 0))
                elif neighbor != state.parent.get(node):
                    state.low[node] = min(state.low[node], state.discovery[neighbor])
                continue
            stack.pop()
            parent = state.parent.get(node)
            if parent is not None:
                state.low[parent] = min(state.low[parent], state.low[node])
    return state


def articulation_points(graph: WorkbenchGraph) -> tuple[CutVertex, ...]:
    """Return cut vertices and the components created by removing each one."""
    adjacency = build_adjacency(graph)
    state = _tarjan(graph, adjacency)
    articulation: list[str] = []
    for node in graph.node_ids:
        parent = state.parent.get(node)
        if parent is None:
            continue
        is_root_child = state.roots[node] == parent
        is_bridge_child = state.roots[node] != parent
        if (is_root_child and state.children.get(parent, 0) > 1) or (
            is_bridge_child and state.low[node] >= state.discovery[parent]
        ):
            articulation.append(parent)
    result: list[CutVertex] = []
    for node_id in sorted(set(articulation)):
        reduced = adjacency.copy()
        reduced.pop(node_id, None)
        for neighbors in reduced.values():
            neighbors.pop(node_id, None)
        fragments = connected_components(graph.induced(frozenset(reduced)))
        if len(fragments) <= len(connected_components(graph)):
            continue
        count = len(fragments)
        severity = "critical" if count >= 4 else "high" if count == 3 else "medium"
        result.append(
            CutVertex(
                node_id=node_id,
                label=graph.node(node_id).label,
                fragments=tuple(fragment.node_ids for fragment in fragments),
                severity=severity,
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class Bridge:
    """A relationship whose removal splits a connected component."""

    source: str
    target: str
    kind: str
    key: tuple[str, str, str]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "key": list(self.key),
        }


def bridges(graph: WorkbenchGraph) -> tuple[Bridge, ...]:
    """Return undirected bridges using the same low-link traversal."""
    adjacency = build_adjacency(graph)
    state = _tarjan(graph, adjacency)
    found: list[Bridge] = []
    for edge_key in graph.edge_keys:
        edge = graph.edges[edge_key]
        left, right = edge.source, edge.target
        forward = state.parent.get(right) == left and state.low[right] > state.discovery[left]
        backward = state.parent.get(left) == right and state.low[left] > state.discovery[right]
        if forward or backward:
            found.append(Bridge(left, right, edge.kind.value, edge_key))
    return tuple(found)


def neighborhood(graph: WorkbenchGraph, node_id: str, *, depth: int = 1) -> dict[str, Any]:
    """Return a bounded neighborhood around one vertex."""
    graph.node(node_id)
    if depth < 1 or depth > 6:
        raise ValueError("depth must be between 1 and 6")
    visited = {node_id}
    frontier = {node_id}
    for _ in range(depth):
        following: set[str] = set()
        for key in frontier:
            following.update(graph.neighbors(key))
        frontier = following - visited
        visited.update(frontier)
        if not frontier:
            break
    induced = graph.induced(frozenset(visited))
    return {
        "node_id": node_id,
        "depth": depth,
        "nodes": [induced.node(key).as_dict() for key in induced.node_ids],
        "edges": [edge.as_dict() for edge in induced.edges.values()],
        "count": len(induced),
    }


def structural_summary(graph: WorkbenchGraph) -> dict[str, Any]:
    """Return compact metrics used by the workbench status strip."""
    components = connected_components(graph)
    degrees = [graph.degree(key) for key in graph.node_ids]
    cut_vertices = articulation_points(graph)
    isolated = sum(1 for component in components if component.size == 1)
    return {
        "nodes": len(graph),
        "edges": len(graph.edges),
        "components": len(components),
        "largest_component": max((component.size for component in components), default=0),
        "isolated": isolated,
        "cut_vertices": len(cut_vertices),
        "bridges": len(bridges(graph)),
        "average_degree": round(sum(degrees) / len(degrees), 3) if degrees else 0.0,
        "density": round(
            len(graph.edges) / (len(graph) * (len(graph) - 1) / 2) if len(graph) > 1 else 0.0,
            4,
        ),
    }
