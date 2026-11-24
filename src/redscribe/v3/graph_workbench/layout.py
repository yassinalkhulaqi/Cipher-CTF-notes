"""Deterministic, pluggable layout strategies for the graph workbench.

Every strategy is a pure function of ``(graph, options)``: the same seed and the
same graph always produce byte-identical coordinates. That property is what
makes snapshots, diffs, minimaps, and interaction tests reproducible.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from redscribe.v3.graph_workbench.model import WorkbenchGraph

DEFAULT_WIDTH = 1200.0
DEFAULT_HEIGHT = 760.0
DEFAULT_ITERATIONS = 24
DEFAULT_PADDING = 48.0
DEFAULT_SAMPLE = 16


def stable_hash(value: str) -> int:
    """Return a platform-independent 32-bit hash for a string."""
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


class SeededRandom:
    """Small xorshift generator with no global state or platform dependence."""

    __slots__ = ("_state", "seed")

    def __init__(self, seed: int = 1) -> None:
        self.seed = int(seed)
        self._state = self.seed & 0xFFFFFFFF
        if self._state == 0:
            self._state = 0x9E3779B9

    def next_u32(self) -> int:
        """Advance the generator and return the next 32-bit value."""
        value = self._state
        value ^= (value << 13) & 0xFFFFFFFF
        value ^= value >> 17
        value ^= (value << 5) & 0xFFFFFFFF
        self._state = value & 0xFFFFFFFF
        return self._state

    def random(self) -> float:
        """Return the next value in ``[0, 1)``."""
        return self.next_u32() / 0x100000000

    def between(self, low: float, high: float) -> float:
        """Return a uniform value in ``[low, high)``."""
        return low + (high - low) * self.random()

    def below(self, count: int) -> int:
        """Return an integer in ``[0, count)``."""
        if count <= 0:
            return 0
        return self.next_u32() % count

    def shuffle(self, items: tuple[str, ...]) -> tuple[str, ...]:
        """Return a deterministically shuffled copy."""
        result = list(items)
        for index in range(len(result) - 1, 0, -1):
            other = self.below(index + 1)
            result[index], result[other] = result[other], result[index]
        return tuple(result)


@dataclass(frozen=True, slots=True)
class LayoutOptions:
    """Inputs that affect layout output beyond the graph itself."""

    seed: int = 1
    width: float = DEFAULT_WIDTH
    height: float = DEFAULT_HEIGHT
    padding: float = DEFAULT_PADDING
    iterations: int = DEFAULT_ITERATIONS
    sample_size: int = DEFAULT_SAMPLE
    direction: str = "LR"
    root: str = ""
    time_key: str = "timestamp"
    lane_height: float = 88.0

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Layout dimensions must be positive")
        if self.padding < 0:
            raise ValueError("Padding cannot be negative")
        if self.iterations < 1 or self.iterations > 200:
            raise ValueError("Iterations must be between 1 and 200")
        if self.sample_size < 2 or self.sample_size > 256:
            raise ValueError("Sample size must be between 2 and 256")
        if self.direction not in ("LR", "TB"):
            raise ValueError("Layout direction must be LR or TB")
        if self.lane_height <= 0:
            raise ValueError("Lane height must be positive")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> LayoutOptions:
        """Build validated options from a wire payload."""
        if not data:
            return cls()
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        values: dict[str, Any] = {}
        for key, value in data.items():
            if key not in allowed or value is None:
                continue
            values[key] = value
        return cls(**values)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "padding": self.padding,
            "iterations": self.iterations,
            "sample_size": self.sample_size,
            "direction": self.direction,
            "root": self.root,
            "time_key": self.time_key,
            "lane_height": self.lane_height,
        }


@dataclass(frozen=True, slots=True)
class Point:
    """A two-dimensional coordinate with stable rounding."""

    x: float
    y: float

    def rounded(self, digits: int = 2) -> Point:
        """Return a copy rounded to a fixed number of decimals."""
        return Point(round(self.x, digits), round(self.y, digits))

    def as_dict(self) -> dict[str, float]:
        """Return a JSON-safe representation."""
        return {"x": round(self.x, 4), "y": round(self.y, 4)}


@dataclass(frozen=True, slots=True)
class LayoutResult:
    """The output of one layout computation."""

    strategy: str
    seed: int
    width: float
    height: float
    positions: dict[str, Point] = field(default_factory=dict)
    center: str = ""

    def __len__(self) -> int:
        """Return the number of positioned vertices."""
        return len(self.positions)

    def point(self, node_id: str) -> Point:
        """Return one position or raise a descriptive error."""
        try:
            return self.positions[node_id]
        except KeyError as error:
            raise ValueError(f"Node was not laid out: {node_id}") from error

    def ordered_ids(self) -> tuple[str, ...]:
        """Return positioned node ids in stable order."""
        return tuple(sorted(self.positions))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "strategy": self.strategy,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "center": self.center,
            "positions": {key: value.as_dict() for key, value in sorted(self.positions.items())},
        }


@runtime_checkable
class LayoutStrategy(Protocol):
    """Interface implemented by every layout strategy."""

    name: str

    def compute(self, graph: WorkbenchGraph, options: LayoutOptions) -> LayoutResult:
        """Compute positions for every vertex of ``graph``."""
        ...


def _inner_box(options: LayoutOptions) -> tuple[float, float, float, float]:
    """Return the usable drawing rectangle."""
    left = min(options.padding, options.width / 3)
    top = min(options.padding, options.height / 3)
    return left, top, options.width - left, options.height - top


def normalize_positions(
    positions: dict[str, Point],
    options: LayoutOptions,
) -> dict[str, Point]:
    """Fit raw positions into the configured canvas with deterministic rounding."""
    if not positions:
        return {}
    left, top, right, bottom = _inner_box(options)
    values = [(point.x, point.y) for point in positions.values()]
    min_x = min(value[0] for value in values)
    max_x = max(value[0] for value in values)
    min_y = min(value[1] for value in values)
    max_y = max(value[1] for value in values)
    span_x = max_x - min_x or 1.0
    span_y = max_y - min_y or 1.0
    scale_x = max(right - left, 1.0) / span_x
    scale_y = max(bottom - top, 1.0) / span_y
    scale = min(scale_x, scale_y)
    offset_x = left + ((right - left) - span_x * scale) / 2
    offset_y = top + ((bottom - top) - span_y * scale) / 2
    return {
        key: Point(
            offset_x + (point.x - min_x) * scale,
            offset_y + (point.y - min_y) * scale,
        ).rounded()
        for key, point in positions.items()
    }


class ForceLayout:
    """Seeded force-directed layout with bounded, sampled repulsion."""

    name = "force"

    def compute(self, graph: WorkbenchGraph, options: LayoutOptions) -> LayoutResult:
        """Relax a deterministic initial embedding into the target canvas."""
        keys = graph.node_ids
        if not keys:
            return LayoutResult(self.name, options.seed, options.width, options.height)
        rng = SeededRandom(options.seed)
        points = self._initial_points(keys, rng)
        edges = [
            (edge.source, edge.target, max(edge.weight, 0.05))
            for edge in graph.edges.values()
            if edge.source in points and edge.target in points
        ]
        sample = min(options.sample_size, max(2, len(keys)))
        iterations = self._iteration_budget(len(keys), options.iterations)
        for step in range(iterations):
            points = self._relax(points, edges, sample, step)
        return LayoutResult(
            strategy=self.name,
            seed=options.seed,
            width=options.width,
            height=options.height,
            positions=normalize_positions(points, options),
            center=self._center(graph, keys),
        )

    @staticmethod
    def _iteration_budget(size: int, requested: int) -> int:
        """Scale work down for very large graphs without changing small ones."""
        if size <= 400:
            return requested
        budget = max(6, min(requested, 12000 // max(size // 10, 1)))
        return budget

    @staticmethod
    def _initial_points(keys: tuple[str, ...], rng: SeededRandom) -> dict[str, Point]:
        """Seed positions on a golden-angle spiral with a stable hash offset."""
        points: dict[str, Point] = {}
        for index, key in enumerate(keys):
            angle = index * 2.399963229728653 + (stable_hash(key) % 1000) / 1000.0
            radius = 0.35 * math.sqrt(index + 1)
            jitter = rng.between(-0.05, 0.05)
            points[key] = Point(
                math.cos(angle) * (radius + jitter),
                math.sin(angle) * (radius + jitter),
            )
        return points

    @staticmethod
    def _peers(keys: tuple[str, ...], index: int, sample: int, step: int) -> tuple[str, ...]:
        """Choose a deterministic subset of repulsion partners."""
        size = len(keys)
        stride = max(1, size // max(sample - 1, 1))
        start = (index + step * stride) % size
        return tuple(keys[(start + offset * stride) % size] for offset in range(sample - 1))

    def _relax(
        self,
        points: dict[str, Point],
        edges: list[tuple[str, str, float]],
        sample: int,
        step: int,
    ) -> dict[str, Point]:
        """Perform one damped relaxation step."""
        keys = tuple(sorted(points))
        deltas: dict[str, Point] = {key: Point(0.0, 0.0) for key in keys}
        cooling = 1.0 / (1.0 + step * 0.12)
        for index, key in enumerate(keys):
            current = points[key]
            push_x = 0.0
            push_y = 0.0
            for other_key in self._peers(keys, index, sample, step):
                if other_key == key:
                    continue
                other = points[other_key]
                diff_x = current.x - other.x
                diff_y = current.y - other.y
                squared = diff_x * diff_x + diff_y * diff_y + 0.02
                force = 0.9 / squared
                distance = math.sqrt(squared)
                push_x += force * diff_x / distance
                push_y += force * diff_y / distance
            for source, target, weight in edges:
                if source == key:
                    other = points[target]
                elif target == key:
                    other = points[source]
                else:
                    continue
                diff_x = other.x - current.x
                diff_y = other.y - current.y
                distance = math.sqrt(diff_x * diff_x + diff_y * diff_y) + 0.01
                strength = min(distance - 1.4, 1.2) * weight * 0.08
                push_x += strength * diff_x / distance
                push_y += strength * diff_y / distance
            deltas[key] = Point(-current.x * 0.01, -current.y * 0.01)
            deltas[key] = Point(
                deltas[key].x + push_x * cooling,
                deltas[key].y + push_y * cooling,
            )
        return {
            key: Point(
                max(-50.0, min(50.0, points[key].x + deltas[key].x)),
                max(-50.0, min(50.0, points[key].y + deltas[key].y)),
            )
            for key in keys
        }

    @staticmethod
    def _center(graph: WorkbenchGraph, keys: tuple[str, ...]) -> str:
        """Return the highest-degree vertex as the visual center."""
        return max(keys, key=lambda key: (graph.degree(key), key))


class HierarchicalLayout:
    """Layered layout computed from directed edges with cycle-safe fallbacks."""

    name = "hierarchical"

    def compute(self, graph: WorkbenchGraph, options: LayoutOptions) -> LayoutResult:
        """Place vertices in layers ordered by dependency depth."""
        keys = graph.node_ids
        if not keys:
            return LayoutResult(self.name, options.seed, options.width, options.height)
        layers = self._layers(graph, keys, options.root)
        points: dict[str, Point] = {}
        for layer_index, layer in enumerate(layers):
            count = len(layer)
            for position, key in enumerate(layer):
                across = (position + 1) / (count + 1)
                depth = layer_index / max(len(layers) - 1, 1)
                if options.direction == "TB":
                    points[key] = Point(across, depth)
                else:
                    points[key] = Point(depth, across)
        return LayoutResult(
            strategy=self.name,
            seed=options.seed,
            width=options.width,
            height=options.height,
            positions=normalize_positions(points, options),
            center=(
                options.root if options.root in graph.nodes else (layers[0][0] if layers else "")
            ),
        )

    @staticmethod
    def _layers(
        graph: WorkbenchGraph,
        keys: tuple[str, ...],
        root: str,
    ) -> tuple[tuple[str, ...], ...]:
        """Assign vertices to acyclic layers using stable topological order."""
        incoming: dict[str, int] = dict.fromkeys(keys, 0)
        outgoing: dict[str, list[str]] = {key: [] for key in keys}
        for edge in graph.edges.values():
            if (
                edge.source == edge.target
                or edge.source not in incoming
                or edge.target not in incoming
            ):
                continue
            outgoing[edge.source].append(edge.target)
            incoming[edge.target] += 1
        roots = [key for key in keys if incoming[key] == 0]
        if root in incoming:
            roots = [root]
        if not roots:
            roots = [max(keys, key=lambda key: (graph.degree(key), key))]
        depth: dict[str, int] = {}
        queue = [(key, 0) for key in sorted(roots)]
        cursor = 0
        while cursor < len(queue):
            key, level = queue[cursor]
            cursor += 1
            if key in depth and depth[key] <= level:
                continue
            depth[key] = level
            for target in sorted(outgoing[key]):
                if level + 1 <= len(keys):
                    queue.append((target, level + 1))
        for key in keys:
            if key not in depth:
                depth[key] = 0
        max_depth = max(depth.values(), default=0)
        groups: list[list[str]] = [[] for _ in range(max_depth + 1)]
        for key in sorted(keys, key=lambda item: (depth[item], -graph.degree(item), item)):
            groups[depth[key]].append(key)
        return tuple(tuple(group) for group in groups if group)


class RadialLayout:
    """Concentric-ring layout rooted at the most connected vertex by default."""

    name = "radial"

    def compute(self, graph: WorkbenchGraph, options: LayoutOptions) -> LayoutResult:
        """Place vertices on rings determined by hops from the center."""
        keys = graph.node_ids
        if not keys:
            return LayoutResult(self.name, options.seed, options.width, options.height)
        center = options.root if options.root in graph.nodes else self._center(graph, keys)
        rings = self._rings(graph, center)
        points: dict[str, Point] = {}
        max_ring = max(rings.values(), default=0)
        for ring in range(max_ring + 1):
            members = sorted(
                (key for key, value in rings.items() if value == ring),
                key=lambda key: (graph.nodes[key].kind, key),
            )
            radius = 0.12 + 0.38 * (ring / max(max_ring, 1))
            for index, key in enumerate(members):
                angle = 2 * math.pi * index / max(len(members), 1) + ring * 0.31
                points[key] = Point(0.5 + math.cos(angle) * radius, 0.5 + math.sin(angle) * radius)
        return LayoutResult(
            strategy=self.name,
            seed=options.seed,
            width=options.width,
            height=options.height,
            positions=normalize_positions(points, options),
            center=center,
        )

    @staticmethod
    def _center(graph: WorkbenchGraph, keys: tuple[str, ...]) -> str:
        """Choose the center by degree, then by key."""
        return max(keys, key=lambda key: (graph.degree(key), key))

    @staticmethod
    def _rings(graph: WorkbenchGraph, center: str) -> dict[str, int]:
        """Return hop distances from the center over the undirected graph."""
        result = {center: 0}
        frontier = [center]
        depth = 0
        while frontier:
            following: list[str] = []
            for key in frontier:
                for neighbor in graph.neighbors(key):
                    if neighbor in result:
                        continue
                    result[neighbor] = depth + 1
                    following.append(neighbor)
            frontier = sorted(following)
            depth += 1
        return result


class TimelineLayout:
    """Chronological layout with one horizontal lane per entity kind."""

    name = "timeline"

    def compute(self, graph: WorkbenchGraph, options: LayoutOptions) -> LayoutResult:
        """Order vertices by timestamp and assign kind-based lanes."""
        keys = graph.node_ids
        if not keys:
            return LayoutResult(self.name, options.seed, options.width, options.height)
        ordered = sorted(keys, key=lambda key: (self._time(graph, key, options), key))
        lanes = self._lanes(graph)
        points: dict[str, Point] = {}
        for index, key in enumerate(ordered):
            across = (index + 1) / (len(ordered) + 1)
            lane = lanes.get(graph.nodes[key].kind, len(lanes))
            points[key] = Point(across, lane / max(len(lanes), 1))
        return LayoutResult(
            strategy=self.name,
            seed=options.seed,
            width=options.width,
            height=options.height,
            positions=normalize_positions(points, options),
            center=ordered[0] if ordered else "",
        )

    @staticmethod
    def _time(graph: WorkbenchGraph, key: str, options: LayoutOptions) -> float:
        """Read the configured time field from node metadata or the node itself."""
        node = graph.node(key)
        if options.time_key == "timestamp":
            return node.timestamp
        value = node.metadata.get(options.time_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            return float(stable_hash(value) % 100000) / 100000
        return 0.0

    @staticmethod
    def _lanes(graph: WorkbenchGraph) -> dict[str, int]:
        """Return a stable lane index per distinct kind."""
        kinds = sorted({node.kind for node in graph.nodes.values()})
        return {kind: index for index, kind in enumerate(kinds)}


_LAYOUTS: dict[str, LayoutStrategy] = {
    strategy.name: strategy
    for strategy in (ForceLayout(), HierarchicalLayout(), RadialLayout(), TimelineLayout())
}


def available_layouts() -> tuple[str, ...]:
    """Return registered layout names in stable order."""
    return tuple(sorted(_LAYOUTS))


def register_layout(strategy: LayoutStrategy) -> None:
    """Register a custom strategy, allowing additive extensions."""
    _LAYOUTS[strategy.name] = strategy


def get_layout(name: str) -> LayoutStrategy:
    """Return a registered strategy or raise a descriptive error."""
    strategy = _LAYOUTS.get(name.strip().casefold())
    if strategy is None:
        raise ValueError(f"Unknown layout '{name}'; available: {', '.join(available_layouts())}")
    return strategy


def compute_layout(
    graph: WorkbenchGraph,
    name: str = "force",
    options: LayoutOptions | None = None,
) -> LayoutResult:
    """Run a named strategy against a graph and validated options."""
    return get_layout(name).compute(graph, options or LayoutOptions())
