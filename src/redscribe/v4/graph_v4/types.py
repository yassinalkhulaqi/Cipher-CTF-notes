"""Value types for the v4 graph workbench.

Every type in this module is data-only: it validates its own invariants and
round-trips through plain dictionaries so it can cross the API and storage
boundaries without executing caller-supplied code.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v4.contracts import EntityKind, EntityRef, is_entity_id

__all__ = [
    "DEFAULT_MIN_WEIGHT",
    "DEFAULT_WEIGHT",
    "GRAPH_ID_PATTERN",
    "MAX_LABEL_LENGTH",
    "RELATION_PATTERN",
    "SNAPSHOT_NAME_PATTERN",
    "FilterResult",
    "GraphData",
    "GraphEdge",
    "GraphFilter",
    "GraphMetrics",
    "GraphNode",
    "GraphPoint",
    "GraphSnapshot",
    "LayoutKind",
    "LayoutResult",
    "RelationStat",
]

RELATION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,2}$")
GRAPH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SNAPSHOT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_LABEL_LENGTH = 160
MAX_FILTER_TEXT_LENGTH = 120
MAX_SNAPSHOT_TAGS = 8
DEFAULT_WEIGHT = 1.0
DEFAULT_MIN_WEIGHT = 0.0


def _as_text(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    return str(value)


def _as_float(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = data.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key}: {value!r}") from exc


def _as_int(data: dict[str, Any], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key}: {value!r}") from exc


def _as_edge_key(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("edge key must contain exactly three parts")
    return (str(value[0]), str(value[1]), str(value[2]))


def _checked_text(value: str, name: str, limit: int) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if len(text) > limit:
        raise ValueError(f"{name} must be at most {limit} characters")
    return text


def _checked_weight(value: float, name: str = "weight") -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return value


def _checked_relation(value: str) -> str:
    relation = value.strip().casefold()
    if not RELATION_PATTERN.match(relation):
        raise ValueError(f"invalid relation slug: {value}")
    return relation


class LayoutKind(str, Enum):
    """Deterministic layout strategies supported by the workbench."""

    FORCE = "force"
    CIRCULAR = "circular"
    GRID = "grid"

    @classmethod
    def parse(cls, value: str) -> LayoutKind:
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"unknown layout kind: {value}")

    @property
    def label(self) -> str:
        return self.value.title()


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A vertex representing one vault entity."""

    id: str
    kind: EntityKind
    label: str
    weight: float = DEFAULT_WEIGHT

    def __post_init__(self) -> None:
        node_id = _checked_text(self.id, "node id", 128)
        if not GRAPH_ID_PATTERN.match(node_id):
            raise ValueError(f"invalid node id: {self.id}")
        if not isinstance(self.kind, EntityKind):
            raise ValueError(f"invalid node kind: {self.kind!r}")
        label = _checked_text(self.label, "label", MAX_LABEL_LENGTH)
        object.__setattr__(self, "id", node_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "weight", _checked_weight(self.weight))

    @classmethod
    def from_ref(cls, ref: EntityRef, weight: float = DEFAULT_WEIGHT) -> GraphNode:
        """Build a node from a shared ``EntityRef``."""
        label = ref.label.strip() or ref.kind.label
        return cls(id=ref.id, kind=ref.kind, label=label, weight=weight)

    def to_ref(self) -> EntityRef:
        """Project this node back into a shared entity reference."""
        return EntityRef(kind=self.kind, id=self.id, label=self.label)

    def is_entity_backed(self) -> bool:
        return is_entity_id(self.id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "label": self.label,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphNode:
        return cls(
            id=_as_text(data, "id"),
            kind=EntityKind.parse(_as_text(data, "kind")),
            label=_as_text(data, "label"),
            weight=_as_float(data, "weight", DEFAULT_WEIGHT),
        )


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """A typed relationship between two graph nodes."""

    source: str
    target: str
    relation: str
    weight: float = DEFAULT_WEIGHT

    def __post_init__(self) -> None:
        source = _checked_text(self.source, "edge source", 128)
        target = _checked_text(self.target, "edge target", 128)
        if source == target:
            raise ValueError("an edge cannot reference the same node twice")
        relation = _checked_relation(self.relation)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "weight", _checked_weight(self.weight))

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.relation)

    def reversed(self) -> GraphEdge:
        return GraphEdge(
            source=self.target,
            target=self.source,
            relation=self.relation,
            weight=self.weight,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphEdge:
        return cls(
            source=_as_text(data, "source"),
            target=_as_text(data, "target"),
            relation=_as_text(data, "relation"),
            weight=_as_float(data, "weight", DEFAULT_WEIGHT),
        )


@dataclass(frozen=True, slots=True)
class GraphFilter:
    """A composable, side-effect-free filter over nodes and edges."""

    kinds: tuple[EntityKind, ...] = ()
    relations: tuple[str, ...] = ()
    min_weight: float = DEFAULT_MIN_WEIGHT
    label_contains: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kinds, tuple):
            raise ValueError("kinds must be a tuple")
        if not isinstance(self.relations, tuple):
            raise ValueError("relations must be a tuple")
        for kind in self.kinds:
            if not isinstance(kind, EntityKind):
                raise ValueError(f"invalid filter kind: {kind!r}")
        relations = tuple(_checked_relation(item) for item in self.relations)
        needle = self.label_contains.strip()
        if len(needle) > MAX_FILTER_TEXT_LENGTH:
            raise ValueError("label_contains is too long")
        object.__setattr__(self, "relations", relations)
        object.__setattr__(self, "min_weight", _checked_weight(self.min_weight, "min_weight"))
        object.__setattr__(self, "label_contains", needle)

    def is_empty(self) -> bool:
        return (
            not self.kinds
            and not self.relations
            and self.min_weight <= 0.0
            and not self.label_contains
        )

    def matches_node(self, node: GraphNode) -> bool:
        if self.kinds and node.kind not in self.kinds:
            return False
        if not self.label_contains:
            return True
        return self.label_contains.casefold() in node.label.casefold()

    def matches_edge(self, edge: GraphEdge) -> bool:
        if self.relations and edge.relation not in self.relations:
            return False
        return edge.weight >= self.min_weight

    def with_kind(self, kind: EntityKind) -> GraphFilter:
        if kind in self.kinds:
            return self
        return GraphFilter(
            kinds=(*self.kinds, kind),
            relations=self.relations,
            min_weight=self.min_weight,
            label_contains=self.label_contains,
        )

    def without_kind(self, kind: EntityKind) -> GraphFilter:
        return GraphFilter(
            kinds=tuple(item for item in self.kinds if item != kind),
            relations=self.relations,
            min_weight=self.min_weight,
            label_contains=self.label_contains,
        )

    def with_relation(self, relation: str) -> GraphFilter:
        normalized = _checked_relation(relation)
        if normalized in self.relations:
            return self
        return GraphFilter(
            kinds=self.kinds,
            relations=(*self.relations, normalized),
            min_weight=self.min_weight,
            label_contains=self.label_contains,
        )

    def with_min_weight(self, value: float) -> GraphFilter:
        return GraphFilter(
            kinds=self.kinds,
            relations=self.relations,
            min_weight=_checked_weight(value, "min_weight"),
            label_contains=self.label_contains,
        )

    def with_label(self, value: str) -> GraphFilter:
        return GraphFilter(
            kinds=self.kinds,
            relations=self.relations,
            min_weight=self.min_weight,
            label_contains=value,
        )

    def describe(self) -> str:
        pieces: list[str] = []
        if self.kinds:
            pieces.append("kinds=" + ",".join(sorted(kind.value for kind in self.kinds)))
        if self.relations:
            pieces.append("relations=" + ",".join(sorted(self.relations)))
        if self.min_weight > 0.0:
            pieces.append(f"weight>={self.min_weight:.2f}")
        if self.label_contains:
            pieces.append(f"label~{self.label_contains}")
        return ", ".join(pieces) if pieces else "all"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kinds": [kind.value for kind in self.kinds],
            "relations": list(self.relations),
            "min_weight": self.min_weight,
            "label_contains": self.label_contains,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphFilter:
        raw_kinds = data.get("kinds", [])
        raw_relations = data.get("relations", [])
        if not isinstance(raw_kinds, (list, tuple)) or not isinstance(raw_relations, (list, tuple)):
            raise ValueError("kinds and relations must be sequences")
        return cls(
            kinds=tuple(EntityKind.parse(_as_text({"value": item}, "value")) for item in raw_kinds),
            relations=tuple(_as_text({"value": item}, "value") for item in raw_relations),
            min_weight=_as_float(data, "min_weight", DEFAULT_MIN_WEIGHT),
            label_contains=_as_text(data, "label_contains"),
        )


@dataclass(frozen=True, slots=True)
class GraphMetrics:
    """Summary counters for a graph snapshot."""

    node_count: int
    edge_count: int
    degree: dict[str, int] = field(default_factory=dict)
    component_count: int = 1

    def __post_init__(self) -> None:
        if self.node_count < 0 or self.edge_count < 0:
            raise ValueError("counts must not be negative")
        if self.component_count < 0:
            raise ValueError("component_count must not be negative")
        for node_id, value in self.degree.items():
            if not GRAPH_ID_PATTERN.match(node_id):
                raise ValueError(f"invalid degree key: {node_id}")
            if value < 0:
                raise ValueError("degree values must not be negative")

    @property
    def isolated_count(self) -> int:
        return sum(1 for value in self.degree.values() if value == 0)

    @property
    def max_degree(self) -> int:
        return max(self.degree.values(), default=0)

    @property
    def average_degree(self) -> float:
        if not self.degree:
            return 0.0
        return round(sum(self.degree.values()) / len(self.degree), 4)

    @property
    def density(self) -> float:
        if self.node_count < 2:
            return 0.0
        possible = self.node_count * (self.node_count - 1)
        return round((2 * self.edge_count) / possible, 4)

    def degree_for(self, node_id: str) -> int:
        return self.degree.get(node_id, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "degree": dict(sorted(self.degree.items())),
            "component_count": self.component_count,
            "isolated_count": self.isolated_count,
            "max_degree": self.max_degree,
            "average_degree": self.average_degree,
            "density": self.density,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphMetrics:
        raw = data.get("degree", {})
        if not isinstance(raw, dict):
            raise ValueError("degree must be a mapping")
        degree = {str(key): _as_int({"value": value}, "value") for key, value in raw.items()}
        return cls(
            node_count=_as_int(data, "node_count"),
            edge_count=_as_int(data, "edge_count"),
            degree=degree,
            component_count=_as_int(data, "component_count", 1),
        )


@dataclass(frozen=True, slots=True)
class RelationStat:
    """Aggregated usage of one relationship type."""

    relation: str
    count: int
    average_weight: float

    def __post_init__(self) -> None:
        if self.relation != _checked_relation(self.relation):
            raise ValueError(f"invalid relation slug: {self.relation}")
        if self.count < 0:
            raise ValueError("count must not be negative")
        _checked_weight(self.average_weight, "average_weight")

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "count": self.count,
            "average_weight": self.average_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RelationStat:
        return cls(
            relation=_as_text(data, "relation"),
            count=_as_int(data, "count"),
            average_weight=_as_float(data, "average_weight", DEFAULT_WEIGHT),
        )


@dataclass(frozen=True, slots=True)
class GraphData:
    """An immutable, sorted collection of nodes and edges."""

    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.nodes, tuple) or not isinstance(self.edges, tuple):
            raise ValueError("nodes and edges must be tuples")
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate node ids are not allowed")
        keys = [edge.key for edge in self.edges]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate edge keys are not allowed")
        known = set(ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"edge references an unknown node: {edge.key}")

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    @property
    def is_empty(self) -> bool:
        return not self.nodes

    def node_by_id(self, node_id: str) -> GraphNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def with_nodes(self, nodes: Iterable[GraphNode]) -> GraphData:
        kept = tuple(nodes)
        known = {node.id for node in kept}
        edges = tuple(edge for edge in self.edges if edge.source in known and edge.target in known)
        return GraphData(nodes=kept, edges=edges)

    def with_edges(self, edges: Iterable[GraphEdge]) -> GraphData:
        return GraphData(nodes=self.nodes, edges=tuple(edges))

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphData:
        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("nodes and edges must be lists")
        return cls(
            nodes=tuple(GraphNode.from_dict(dict(item)) for item in raw_nodes),
            edges=tuple(GraphEdge.from_dict(dict(item)) for item in raw_edges),
        )


@dataclass(frozen=True, slots=True)
class GraphPoint:
    """A positioned node produced by a layout engine."""

    node_id: str
    x: float
    y: float

    def __post_init__(self) -> None:
        _checked_text(self.node_id, "node id", 128)
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("layout coordinates must be finite")

    def distance_to(self, other: GraphPoint) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "x": round(self.x, 3), "y": round(self.y, 3)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphPoint:
        return cls(
            node_id=_as_text(data, "node_id"),
            x=_as_float(data, "x"),
            y=_as_float(data, "y"),
        )


@dataclass(frozen=True, slots=True)
class LayoutResult:
    """The deterministic output of one layout computation."""

    kind: LayoutKind
    width: float
    height: float
    points: tuple[GraphPoint, ...]
    seed: int = 0
    iterations: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LayoutKind):
            raise ValueError(f"invalid layout kind: {self.kind!r}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("layout dimensions must be positive")
        if self.seed < 0 or self.iterations < 0:
            raise ValueError("seed and iterations must not be negative")
        if not isinstance(self.points, tuple):
            raise ValueError("points must be a tuple")
        ids = [point.node_id for point in self.points]
        if len(ids) != len(set(ids)):
            raise ValueError("layout contains duplicate node ids")

    def by_id(self) -> dict[str, GraphPoint]:
        return {point.node_id: point for point in self.points}

    def in_bounds(self, padding: float = 0.0) -> bool:
        return all(
            padding <= point.x <= self.width - padding
            and padding <= point.y <= self.height - padding
            for point in self.points
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "width": self.width,
            "height": self.height,
            "points": [point.to_dict() for point in self.points],
            "seed": self.seed,
            "iterations": self.iterations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutResult:
        raw = data.get("points", [])
        if not isinstance(raw, list):
            raise ValueError("points must be a list")
        return cls(
            kind=LayoutKind.parse(_as_text(data, "kind")),
            width=_as_float(data, "width", 960.0),
            height=_as_float(data, "height", 600.0),
            points=tuple(GraphPoint.from_dict(dict(item)) for item in raw),
            seed=_as_int(data, "seed"),
            iterations=_as_int(data, "iterations"),
        )


@dataclass(frozen=True, slots=True)
class FilterResult:
    """The visible slice of a graph plus hidden-item accounting."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    hidden_node_ids: tuple[str, ...] = ()
    hidden_edge_keys: tuple[tuple[str, str, str], ...] = ()
    total_nodes: int = 0
    total_edges: int = 0

    @property
    def hidden_nodes(self) -> int:
        return self.total_nodes - len(self.nodes)

    @property
    def hidden_edges(self) -> int:
        return self.total_edges - len(self.edges)

    @property
    def is_empty(self) -> bool:
        return not self.nodes and not self.edges

    def to_data(self) -> GraphData:
        return GraphData(nodes=self.nodes, edges=self.edges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "hidden_nodes": self.hidden_nodes,
            "hidden_edges": self.hidden_edges,
            "hidden_node_ids": list(self.hidden_node_ids),
            "hidden_edge_keys": [list(key) for key in self.hidden_edge_keys],
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterResult:
        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        raw_keys = data.get("hidden_edge_keys", [])
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("nodes and edges must be lists")
        if not isinstance(raw_keys, list):
            raise ValueError("hidden_edge_keys must be a list")
        hidden_ids = data.get("hidden_node_ids", [])
        if not isinstance(hidden_ids, list):
            raise ValueError("hidden_node_ids must be a list")
        return cls(
            nodes=tuple(GraphNode.from_dict(dict(item)) for item in raw_nodes),
            edges=tuple(GraphEdge.from_dict(dict(item)) for item in raw_edges),
            hidden_node_ids=tuple(str(item) for item in hidden_ids),
            hidden_edge_keys=tuple(_as_edge_key(item) for item in raw_keys),
            total_nodes=_as_int(data, "total_nodes"),
            total_edges=_as_int(data, "total_edges"),
        )


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """A named, persisted view of a graph."""

    name: str
    data: GraphData
    filter: GraphFilter
    layout: LayoutKind
    created_at: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        name = _checked_text(self.name, "snapshot name", 64)
        if not SNAPSHOT_NAME_PATTERN.match(name):
            raise ValueError(f"invalid snapshot name: {self.name}")
        if not self.created_at.strip():
            raise ValueError("created_at must not be empty")
        if not isinstance(self.filter, GraphFilter) or not isinstance(self.data, GraphData):
            raise ValueError("snapshot needs a GraphData and GraphFilter")
        if not isinstance(self.layout, LayoutKind):
            raise ValueError(f"invalid snapshot layout: {self.layout!r}")
        if not isinstance(self.tags, tuple) or len(self.tags) > MAX_SNAPSHOT_TAGS:
            raise ValueError("tags must be a tuple of at most 8 entries")
        for tag in self.tags:
            if not SNAPSHOT_NAME_PATTERN.match(tag):
                raise ValueError(f"invalid snapshot tag: {tag}")
        object.__setattr__(self, "name", name)

    def with_filter(self, value: GraphFilter) -> GraphSnapshot:
        return GraphSnapshot(
            name=self.name,
            data=self.data,
            filter=value,
            layout=self.layout,
            created_at=self.created_at,
            tags=self.tags,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data": self.data.to_dict(),
            "filter": self.filter.to_dict(),
            "layout": self.layout.value,
            "created_at": self.created_at,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphSnapshot:
        raw_data = data.get("data", {})
        raw_filter = data.get("filter", {})
        raw_tags = data.get("tags", [])
        if not isinstance(raw_data, dict) or not isinstance(raw_filter, dict):
            raise ValueError("data and filter must be mappings")
        if not isinstance(raw_tags, list):
            raise ValueError("tags must be a list")
        return cls(
            name=_as_text(data, "name"),
            data=GraphData.from_dict(raw_data),
            filter=GraphFilter.from_dict(raw_filter),
            layout=LayoutKind.parse(_as_text(data, "layout", LayoutKind.FORCE.value)),
            created_at=_as_text(data, "created_at"),
            tags=tuple(str(item) for item in raw_tags),
        )
