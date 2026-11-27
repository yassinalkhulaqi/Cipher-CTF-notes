"""Domain operations for the v4 graph workbench.

The service layer is deterministic and data-only: builders deduplicate typed
entity references, analyzers walk the resulting graph, layouts compute stable
coordinates from an explicit seed, and the filter engine explains what was
hidden. No function here performs IO or evaluates caller-supplied code.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from collections.abc import Iterable, Sequence

from redscribe.v4.contracts import EntityKind, EntityLink, EntityRef

from .types import (
    DEFAULT_WEIGHT,
    FilterResult,
    GraphData,
    GraphEdge,
    GraphFilter,
    GraphMetrics,
    GraphNode,
    GraphPoint,
    LayoutKind,
    LayoutResult,
    RelationStat,
)

__all__ = [
    "DEFAULT_GRID_GAP",
    "DEFAULT_HEIGHT",
    "DEFAULT_ITERATIONS",
    "DEFAULT_PADDING",
    "DEFAULT_SEED",
    "DEFAULT_WIDTH",
    "CircularLayout",
    "FilterEngine",
    "ForceLayout",
    "GraphAnalyzer",
    "GraphBuilder",
    "GridLayout",
    "LayoutEngine",
    "compute_layout",
    "relation_legend",
]

DEFAULT_WIDTH = 960.0
DEFAULT_HEIGHT = 600.0
DEFAULT_PADDING = 56.0
DEFAULT_ITERATIONS = 24
DEFAULT_SEED = 0
DEFAULT_GRID_GAP = 18.0


def _sorted_edges(edges: Iterable[GraphEdge]) -> tuple[GraphEdge, ...]:
    return tuple(sorted(edges, key=lambda edge: edge.key))


class GraphBuilder:
    """Accumulate entity references and links into a canonical ``GraphData``."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[tuple[str, str, str], GraphEdge] = {}
        self._link_count = 0
        self._duplicate_links = 0

    @property
    def link_count(self) -> int:
        return self._link_count

    @property
    def duplicate_link_count(self) -> int:
        return self._duplicate_links

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._link_count = 0
        self._duplicate_links = 0

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes))

    def add_ref(self, ref: EntityRef, weight: float = DEFAULT_WEIGHT) -> GraphNode:
        """Add a reference, merging duplicate ids without losing information."""
        candidate = GraphNode.from_ref(ref, weight)
        existing = self._nodes.get(candidate.id)
        if existing is None:
            self._nodes[candidate.id] = candidate
            return candidate
        label = existing.label
        if label == existing.kind.label and candidate.label != candidate.kind.label:
            label = candidate.label
        merged = GraphNode(
            id=existing.id,
            kind=existing.kind,
            label=label,
            weight=max(existing.weight, candidate.weight),
        )
        self._nodes[candidate.id] = merged
        return merged

    def add_refs(self, refs: Iterable[EntityRef]) -> int:
        before = len(self._nodes)
        for ref in refs:
            self.add_ref(ref)
        return len(self._nodes) - before

    def add_link(self, link: EntityLink) -> GraphEdge | None:
        """Add a typed link, creating endpoint nodes when they are missing."""
        self.add_ref(link.source)
        self.add_ref(link.target)
        edge = GraphEdge(
            source=link.source.id,
            target=link.target.id,
            relation=link.relation,
            weight=link.weight,
        )
        existing = self._edges.get(edge.key)
        if existing is not None:
            self._duplicate_links += 1
            if existing.weight >= edge.weight:
                self._link_count += 1
                return existing
            edge = GraphEdge(
                source=edge.source,
                target=edge.target,
                relation=edge.relation,
                weight=edge.weight,
            )
            self._edges[edge.key] = edge
            self._link_count += 1
            return edge
        self._edges[edge.key] = edge
        self._link_count += 1
        return edge

    def add_links(self, links: Iterable[EntityLink]) -> int:
        before = self._link_count
        for link in links:
            self.add_link(link)
        return self._link_count - before

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add a pre-built edge (and infer lightweight endpoint nodes)."""
        if edge.source not in self._nodes:
            self._nodes[edge.source] = GraphNode(
                id=edge.source, kind=EntityKind.NOTE, label=edge.source
            )
        if edge.target not in self._nodes:
            self._nodes[edge.target] = GraphNode(
                id=edge.target, kind=EntityKind.NOTE, label=edge.target
            )
        existing = self._edges.get(edge.key)
        if existing is not None and existing.weight >= edge.weight:
            return existing
        self._edges[edge.key] = edge
        return edge

    def build(self) -> GraphData:
        """Return a sorted snapshot with dangling edges removed."""
        nodes = tuple(self._nodes[node_id] for node_id in sorted(self._nodes))
        known = set(self._nodes)
        edges = _sorted_edges(
            edge for edge in self._edges.values() if edge.source in known and edge.target in known
        )
        return GraphData(nodes=nodes, edges=edges)

    @classmethod
    def from_links(cls, links: Iterable[EntityLink]) -> GraphBuilder:
        builder = cls()
        builder.add_links(links)
        return builder


class GraphAnalyzer:
    """Read-only graph algorithms over a ``GraphData`` snapshot."""

    def __init__(self, data: GraphData) -> None:
        self.data = data

    def adjacency(self, min_weight: float = 0.0) -> dict[str, tuple[str, ...]]:
        """Build an undirected adjacency map with sorted neighbours."""
        neighbours: dict[str, set[str]] = {node.id: set() for node in self.data.nodes}
        for edge in self.data.edges:
            if edge.weight < min_weight:
                continue
            neighbours.setdefault(edge.source, set()).add(edge.target)
            neighbours.setdefault(edge.target, set()).add(edge.source)
        return {node_id: tuple(sorted(items)) for node_id, items in neighbours.items()}

    def degree_map(self, min_weight: float = 0.0) -> dict[str, int]:
        return {
            node_id: len(items) for node_id, items in sorted(self.adjacency(min_weight).items())
        }

    def centrality(self) -> tuple[tuple[str, float], ...]:
        """Return normalized degree centrality, highest first."""
        degrees = self.degree_map()
        denominator = max(1, len(self.data.nodes) - 1)
        ranked = ((node_id, round(value / denominator, 4)) for node_id, value in degrees.items())
        return tuple(sorted(ranked, key=lambda item: (-item[1], item[0])))

    def components(self) -> tuple[tuple[str, ...], ...]:
        """Return connected components of the undirected graph."""
        adjacency = self.adjacency()
        seen: set[str] = set()
        components: list[tuple[str, ...]] = []
        for start in sorted(adjacency):
            if start in seen:
                continue
            seen.add(start)
            queue = deque([start])
            gathered: list[str] = []
            while queue:
                current = queue.popleft()
                gathered.append(current)
                for neighbour in adjacency[current]:
                    if neighbour not in seen:
                        seen.add(neighbour)
                        queue.append(neighbour)
            components.append(tuple(sorted(gathered)))
        return tuple(sorted(components))

    def component_of(self, node_id: str) -> tuple[str, ...]:
        if self.data.node_by_id(node_id) is None:
            raise ValueError(f"unknown node: {node_id}")
        for component in self.components():
            if node_id in component:
                return component
        return (node_id,)

    def shortest_path(self, source: str, target: str) -> tuple[str, ...]:
        """Return a deterministic BFS path, or an empty tuple if unreachable."""
        adjacency = self.adjacency()
        if source not in adjacency or target not in adjacency:
            raise ValueError("both endpoints must exist in the graph")
        if source == target:
            return (source,)
        previous: dict[str, str | None] = {source: None}
        queue = deque([source])
        while queue:
            current = queue.popleft()
            for neighbour in adjacency[current]:
                if neighbour in previous:
                    continue
                previous[neighbour] = current
                if neighbour == target:
                    path: list[str] = []
                    cursor: str | None = neighbour
                    while cursor is not None:
                        path.append(cursor)
                        cursor = previous[cursor]
                    return tuple(reversed(path))
                queue.append(neighbour)
        return ()

    def isolated_nodes(self) -> tuple[str, ...]:
        degrees = self.degree_map()
        return tuple(sorted(node.id for node in self.data.nodes if degrees.get(node.id, 0) == 0))

    def neighbors(self, node_id: str, min_weight: float = 0.0) -> tuple[str, ...]:
        adjacency = self.adjacency(min_weight)
        if node_id not in adjacency:
            raise ValueError(f"unknown node: {node_id}")
        return adjacency[node_id]

    def ego_network(self, node_id: str, depth: int = 1) -> GraphData:
        """Return the induced subgraph within ``depth`` hops of a node."""
        if depth < 0:
            raise ValueError("depth must not be negative")
        adjacency = self.adjacency()
        if node_id not in adjacency:
            raise ValueError(f"unknown node: {node_id}")
        included = {node_id}
        frontier = {node_id}
        for _ in range(depth):
            frontier = {
                neighbour
                for current in frontier
                for neighbour in adjacency.get(current, ())
                if neighbour not in included
            }
            included.update(frontier)
        nodes = tuple(node for node in self.data.nodes if node.id in included)
        edges = _sorted_edges(
            edge for edge in self.data.edges if edge.source in included and edge.target in included
        )
        return GraphData(nodes=nodes, edges=edges)

    def relation_stats(self) -> tuple[RelationStat, ...]:
        return relation_legend(self.data.edges)

    def diameter(self) -> int:
        """Return the longest shortest path across all components."""
        longest = 0
        for component in self.components():
            for index, source in enumerate(component):
                for target in component[index + 1 :]:
                    path = self.shortest_path(source, target)
                    if path:
                        longest = max(longest, len(path) - 1)
        return longest

    def metrics(self) -> GraphMetrics:
        return GraphMetrics(
            node_count=len(self.data.nodes),
            edge_count=len(self.data.edges),
            degree=self.degree_map(),
            component_count=len(self.components()),
        )


def relation_legend(edges: Iterable[GraphEdge]) -> tuple[RelationStat, ...]:
    """Aggregate edge relations for the UI legend."""
    grouped: dict[str, list[float]] = {}
    for edge in edges:
        grouped.setdefault(edge.relation, []).append(edge.weight)
    stats = [
        RelationStat(
            relation=relation,
            count=len(weights),
            average_weight=round(sum(weights) / len(weights), 4),
        )
        for relation, weights in grouped.items()
    ]
    return tuple(sorted(stats, key=lambda item: (-item.count, item.relation)))


class FilterEngine:
    """Apply a ``GraphFilter`` and report exactly what it removed."""

    def __init__(self, flt: GraphFilter) -> None:
        self.filter = flt

    def apply(self, data: GraphData) -> FilterResult:
        visible_nodes = tuple(node for node in data.nodes if self.filter.matches_node(node))
        visible_ids = {node.id for node in visible_nodes}
        hidden_node_ids = tuple(node.id for node in data.nodes if node.id not in visible_ids)
        visible_edges = tuple(
            edge
            for edge in data.edges
            if self.filter.matches_edge(edge)
            and edge.source in visible_ids
            and edge.target in visible_ids
        )
        visible_keys = {edge.key for edge in visible_edges}
        hidden_keys = tuple(edge.key for edge in data.edges if edge.key not in visible_keys)
        return FilterResult(
            nodes=visible_nodes,
            edges=visible_edges,
            hidden_node_ids=hidden_node_ids,
            hidden_edge_keys=hidden_keys,
            total_nodes=len(data.nodes),
            total_edges=len(data.edges),
        )

    def explain(self, data: GraphData) -> dict[str, int]:
        """Return compact counters suitable for an API payload."""
        result = self.apply(data)
        return {
            "visible_nodes": len(result.nodes),
            "visible_edges": len(result.edges),
            "hidden_nodes": result.hidden_nodes,
            "hidden_edges": result.hidden_edges,
        }


class ForceLayout:
    """A seeded, fixed-iteration spring layout with deterministic output."""

    def __init__(
        self,
        width: float = DEFAULT_WIDTH,
        height: float = DEFAULT_HEIGHT,
        padding: float = DEFAULT_PADDING,
        iterations: int = DEFAULT_ITERATIONS,
        seed: int = DEFAULT_SEED,
        spring_length: float = 140.0,
        repulsion: float = 12000.0,
        damping: float = 0.85,
        max_step: float = 28.0,
    ) -> None:
        if width <= 2 * padding or height <= 2 * padding:
            raise ValueError("layout is too small for its padding")
        if iterations < 0 or seed < 0:
            raise ValueError("iterations and seed must not be negative")
        if spring_length <= 0 or repulsion <= 0 or max_step <= 0:
            raise ValueError("force constants must be positive")
        if not 0.0 < damping <= 1.0:
            raise ValueError("damping must be in (0, 1]")
        self.width = width
        self.height = height
        self.padding = padding
        self.iterations = iterations
        self.seed = seed
        self.spring_length = spring_length
        self.repulsion = repulsion
        self.damping = damping
        self.max_step = max_step

    def _unit(self, node_id: str, salt: str) -> float:
        digest = hashlib.sha256(f"{self.seed}:{salt}:{node_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / float(1 << 64)

    def _seed_positions(self, node_ids: Sequence[str]) -> dict[str, list[float]]:
        min_x, max_x = self.padding, self.width - self.padding
        min_y, max_y = self.padding, self.height - self.padding
        return {
            node_id: [
                min_x + (max_x - min_x) * self._unit(node_id, "x"),
                min_y + (max_y - min_y) * self._unit(node_id, "y"),
            ]
            for node_id in node_ids
        }

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def compute(self, data: GraphData) -> LayoutResult:
        node_ids = tuple(sorted(data.node_ids))
        if not node_ids:
            return LayoutResult(
                kind=LayoutKind.FORCE,
                width=self.width,
                height=self.height,
                points=(),
                seed=self.seed,
                iterations=self.iterations,
            )
        positions = self._seed_positions(node_ids)
        for _ in range(self.iterations):
            deltas: dict[str, list[float]] = {node_id: [0.0, 0.0] for node_id in node_ids}
            for index, source in enumerate(node_ids):
                for target in node_ids[index + 1 :]:
                    dx = positions[source][0] - positions[target][0]
                    dy = positions[source][1] - positions[target][1]
                    distance = max(1.0, math.hypot(dx, dy))
                    force = self.repulsion / (distance * distance)
                    fx = (dx / distance) * force
                    fy = (dy / distance) * force
                    deltas[source][0] += fx
                    deltas[source][1] += fy
                    deltas[target][0] -= fx
                    deltas[target][1] -= fy
            for edge in data.edges:
                source, target = edge.source, edge.target
                dx = positions[target][0] - positions[source][0]
                dy = positions[target][1] - positions[source][1]
                distance = max(1.0, math.hypot(dx, dy))
                strength = (distance - self.spring_length) * 0.015
                fx = (dx / distance) * strength
                fy = (dy / distance) * strength
                deltas[source][0] += fx
                deltas[source][1] += fy
                deltas[target][0] -= fx
                deltas[target][1] -= fy
            for node_id in node_ids:
                for axis in (0, 1):
                    step = (
                        self._clamp(deltas[node_id][axis], -self.max_step, self.max_step)
                        * self.damping
                    )
                    positions[node_id][axis] += step
                positions[node_id][0] = self._clamp(
                    positions[node_id][0], self.padding, self.width - self.padding
                )
                positions[node_id][1] = self._clamp(
                    positions[node_id][1], self.padding, self.height - self.padding
                )
        points = tuple(
            GraphPoint(node_id=node_id, x=positions[node_id][0], y=positions[node_id][1])
            for node_id in node_ids
        )
        return LayoutResult(
            kind=LayoutKind.FORCE,
            width=self.width,
            height=self.height,
            points=points,
            seed=self.seed,
            iterations=self.iterations,
        )


class CircularLayout:
    """Place nodes evenly on a circle in stable id order."""

    def __init__(
        self,
        width: float = DEFAULT_WIDTH,
        height: float = DEFAULT_HEIGHT,
        padding: float = DEFAULT_PADDING,
    ) -> None:
        if width <= 2 * padding or height <= 2 * padding:
            raise ValueError("layout is too small for its padding")
        self.width = width
        self.height = height
        self.padding = padding

    def compute(self, data: GraphData) -> LayoutResult:
        node_ids = tuple(sorted(data.node_ids))
        center_x, center_y = self.width / 2, self.height / 2
        radius = min(center_x, center_y) - self.padding
        points: list[GraphPoint] = []
        total = len(node_ids)
        for index, node_id in enumerate(node_ids):
            if total == 1:
                x, y = center_x, center_y
            else:
                angle = (2 * math.pi * index / total) - (math.pi / 2)
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
            points.append(GraphPoint(node_id=node_id, x=x, y=y))
        return LayoutResult(
            kind=LayoutKind.CIRCULAR,
            width=self.width,
            height=self.height,
            points=tuple(points),
        )


class GridLayout:
    """Place nodes on a centered grid with deterministic row-major order."""

    def __init__(
        self,
        width: float = DEFAULT_WIDTH,
        height: float = DEFAULT_HEIGHT,
        padding: float = DEFAULT_PADDING,
        gap: float = DEFAULT_GRID_GAP,
    ) -> None:
        if width <= 2 * padding or height <= 2 * padding:
            raise ValueError("layout is too small for its padding")
        if gap < 0:
            raise ValueError("gap must not be negative")
        self.width = width
        self.height = height
        self.padding = padding
        self.gap = gap

    def compute(self, data: GraphData) -> LayoutResult:
        node_ids = tuple(sorted(data.node_ids))
        total = len(node_ids)
        if not total:
            return LayoutResult(
                kind=LayoutKind.GRID, width=self.width, height=self.height, points=()
            )
        columns = max(1, math.ceil(math.sqrt(total)))
        rows = max(1, math.ceil(total / columns))
        usable_width = self.width - 2 * self.padding
        usable_height = self.height - 2 * self.padding
        cell_width = usable_width / columns
        cell_height = usable_height / rows
        points: list[GraphPoint] = []
        for index, node_id in enumerate(node_ids):
            row, column = divmod(index, columns)
            x = self.padding + column * cell_width + cell_width / 2
            y = self.padding + row * cell_height + cell_height / 2
            points.append(GraphPoint(node_id=node_id, x=x, y=y))
        return LayoutResult(
            kind=LayoutKind.GRID,
            width=self.width,
            height=self.height,
            points=tuple(points),
        )


class LayoutEngine:
    """Facade that dispatches to one of the deterministic layout strategies."""

    def __init__(
        self,
        width: float = DEFAULT_WIDTH,
        height: float = DEFAULT_HEIGHT,
        padding: float = DEFAULT_PADDING,
        seed: int = DEFAULT_SEED,
        iterations: int = DEFAULT_ITERATIONS,
    ) -> None:
        self.width = width
        self.height = height
        self.padding = padding
        self.seed = seed
        self.iterations = iterations

    def compute(self, data: GraphData, kind: LayoutKind = LayoutKind.FORCE) -> LayoutResult:
        if kind is LayoutKind.FORCE:
            return ForceLayout(
                width=self.width,
                height=self.height,
                padding=self.padding,
                seed=self.seed,
                iterations=self.iterations,
            ).compute(data)
        if kind is LayoutKind.CIRCULAR:
            return CircularLayout(
                width=self.width, height=self.height, padding=self.padding
            ).compute(data)
        if kind is LayoutKind.GRID:
            return GridLayout(width=self.width, height=self.height, padding=self.padding).compute(
                data
            )
        raise ValueError(f"unsupported layout kind: {kind}")


def compute_layout(
    data: GraphData,
    kind: LayoutKind = LayoutKind.FORCE,
    *,
    seed: int = DEFAULT_SEED,
    width: float = DEFAULT_WIDTH,
    height: float = DEFAULT_HEIGHT,
    iterations: int = DEFAULT_ITERATIONS,
) -> LayoutResult:
    """Compute one layout without constructing a facade."""
    return LayoutEngine(width=width, height=height, seed=seed, iterations=iterations).compute(
        data, kind
    )
