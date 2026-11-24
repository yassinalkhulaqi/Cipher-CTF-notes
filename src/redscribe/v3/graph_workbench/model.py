"""Analytical graph model for the V3 graph workbench.

The workbench builds its own read-optimized view over the universal V3 entity
contracts. It never redefines those contracts: records and links arrive from
``redscribe.v3.entities`` and are adapted into immutable, serializable nodes and
edges that layout, clustering, analysis, and export modules can share.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from redscribe.v3.entities import (
    EntityId,
    EntityKind,
    EntityLink,
    EntityRecord,
    EntityRef,
    EntityStatus,
    LinkGraph,
    LinkKind,
)
from redscribe.v3.entities.registry import EntityKindRegistry, default_registry

SEVERITY_UNKNOWN = "unknown"
SEVERITY_ORDER: tuple[str, ...] = (
    SEVERITY_UNKNOWN,
    "info",
    "low",
    "medium",
    "high",
    "critical",
)
_SEVERITY_KEYS: tuple[str, ...] = (
    "severity",
    "risk",
    "impact",
    "priority",
    "cvss_severity",
    "cvss",
    "score",
)
_SEVERITY_ALIASES: dict[str, str] = {
    "none": SEVERITY_UNKNOWN,
    "": SEVERITY_UNKNOWN,
    "informational": "info",
    "notice": "info",
    "moderate": "medium",
    "med": "medium",
    "severe": "high",
    "urgent": "critical",
}


class Severity(str, Enum):
    """Normalized severity ladder used by clustering and inspection."""

    UNKNOWN = SEVERITY_UNKNOWN
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def parse(cls, value: str) -> Severity:
        """Parse a severity label with stable aliases."""
        normalized = value.strip().casefold()
        normalized = _SEVERITY_ALIASES.get(normalized, normalized)
        for severity in cls:
            if severity.value == normalized:
                return severity
        return cls.UNKNOWN

    @property
    def rank(self) -> int:
        """Return the severity ordering position."""
        return SEVERITY_ORDER.index(self.value)


def severity_from_metadata(metadata: dict[str, Any], tags: tuple[str, ...]) -> Severity:
    """Derive a severity from entity metadata, then from ``severity:*`` tags."""
    for key in _SEVERITY_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return Severity.parse(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _severity_from_score(float(value))
    for tag in sorted(tags):
        folded = tag.casefold().lstrip("#")
        for prefix in ("severity/", "severity:", "sev/"):
            if folded.startswith(prefix):
                return Severity.parse(folded[len(prefix) :])
    return Severity.UNKNOWN


def _severity_from_score(score: float) -> Severity:
    """Map a numeric risk score onto the severity ladder."""
    if score >= 9.0:
        return Severity.CRITICAL
    if score >= 7.0:
        return Severity.HIGH
    if score >= 4.0:
        return Severity.MEDIUM
    if score > 0.0:
        return Severity.LOW
    return Severity.INFO


@dataclass(frozen=True, slots=True)
class WorkbenchNode:
    """One immutable vertex with the metadata the workbench needs to explain it."""

    ref: EntityRef
    title: str
    kind: str
    tags: tuple[str, ...] = ()
    severity: str = SEVERITY_UNKNOWN
    status: str = "draft"
    owner: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    version: int = 1

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Workbench node title cannot be blank")
        if self.version < 1:
            raise ValueError("Workbench node version must be at least 1")
        if not self.kind:
            raise ValueError("Workbench node kind cannot be blank")

    @classmethod
    def from_record(cls, record: EntityRecord) -> WorkbenchNode:
        """Adapt a universal entity record into a workbench node."""
        severity = severity_from_metadata(record.metadata, record.tags)
        return cls(
            ref=EntityRef(record.entity_id, record.title),
            title=record.title,
            kind=record.entity_id.kind.value,
            tags=tuple(sorted(set(record.tags))),
            severity=severity.value,
            status=record.status.value,
            owner=record.owner,
            summary=record.summary,
            metadata=dict(record.metadata),
            timestamp=record.updated_at or record.created_at,
            version=record.version,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkbenchNode:
        """Restore a node from its serialized form."""
        ref_data = data.get("ref")
        if isinstance(ref_data, dict):
            entity_id = EntityId.parse(str(ref_data["ref"]))
            label = str(ref_data.get("label", ""))
        else:
            entity_id = EntityId.parse(str(data.get("id", "")))
            label = str(data.get("title", ""))
        metadata = data.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("Node metadata must be an object")
        tags = data.get("tags") or ()
        if not isinstance(tags, (list, tuple)):
            raise ValueError("Node tags must be a list")
        timestamp = data.get("timestamp", data.get("updated_at", 0.0))
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise ValueError("Node timestamp must be a number")
        return cls(
            ref=EntityRef(entity_id, label),
            title=str(data.get("title", label)) or str(entity_id),
            kind=str(data.get("kind", entity_id.kind.value)),
            tags=tuple(str(tag) for tag in tags),
            severity=str(data.get("severity", SEVERITY_UNKNOWN)),
            status=str(data.get("status", "draft")),
            owner=str(data.get("owner", "")),
            summary=str(data.get("summary", "")),
            metadata=dict(metadata),
            timestamp=float(timestamp),
            version=int(data.get("version", 1)),
        )

    @property
    def id(self) -> str:
        """Canonical entity identifier used as the graph key."""
        return str(self.ref.entity_id)

    @property
    def entity_id(self) -> EntityId:
        """Universal identifier of the underlying entity."""
        return self.ref.entity_id

    @property
    def label(self) -> str:
        """Display label of the vertex."""
        return self.ref.label or self.title

    @property
    def severity_level(self) -> Severity:
        """Parsed severity ladder entry."""
        return Severity.parse(self.severity)

    @property
    def tag_set(self) -> frozenset[str]:
        """Case-folded tag set for cluster membership checks."""
        return frozenset(tag.casefold().lstrip("#") for tag in self.tags)

    def with_updates(self, **changes: Any) -> WorkbenchNode:
        """Return a copy with selected fields replaced."""
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "ref": self.ref.as_dict(),
            "title": self.title,
            "label": self.label,
            "kind": self.kind,
            "tags": list(self.tags),
            "severity": self.severity,
            "status": self.status,
            "owner": self.owner,
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchEdge:
    """One immutable typed relationship between two workbench nodes."""

    link: EntityLink

    @classmethod
    def from_link(cls, link: EntityLink) -> WorkbenchEdge:
        """Wrap a universal entity link."""
        return cls(link=link)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkbenchEdge:
        """Restore an edge from its serialized form."""
        source = EntityId.parse(str(data["source"]))
        target = EntityId.parse(str(data["target"]))
        kind = LinkKind.parse(str(data.get("kind", LinkKind.RELATES.value)))
        label = str(data.get("label", ""))
        weight = float(data.get("weight", 1.0))
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Edge metadata must be an object")
        return cls(
            link=EntityLink(
                source=source,
                target=target,
                kind=kind,
                label=label,
                weight=weight,
                metadata=dict(metadata),
            )
        )

    @property
    def key(self) -> tuple[str, str, str]:
        """Stable identity of the relationship."""
        return self.link.key

    @property
    def source(self) -> str:
        """Source node key."""
        return str(self.link.source)

    @property
    def target(self) -> str:
        """Target node key."""
        return str(self.link.target)

    @property
    def kind(self) -> LinkKind:
        """Relationship kind."""
        return self.link.kind

    @property
    def weight(self) -> float:
        """Relationship confidence weight."""
        return self.link.weight

    @property
    def label(self) -> str:
        """Human-readable relationship label."""
        return self.link.label

    @property
    def undirected_key(self) -> tuple[str, str, str]:
        """Direction-independent identity used by structural analysis."""
        left, right = sorted((self.source, self.target))
        return (left, right, self.kind.value)

    def connects(self, left: str, right: str) -> bool:
        """Return whether this edge joins two node keys in either direction."""
        return {self.source, self.target} == {left, right}

    def other(self, node_id: str) -> str:
        """Return the far endpoint of this edge."""
        if node_id == self.source:
            return self.target
        if node_id == self.target:
            return self.source
        raise ValueError(f"Node {node_id} is not incident to this edge")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return self.link.as_dict()

    def as_link(self) -> EntityLink:
        """Return the underlying universal entity link."""
        return self.link


@dataclass(slots=True)
class WorkbenchGraph:
    """Read-optimized index over workbench nodes and typed relationships."""

    nodes: dict[str, WorkbenchNode] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], WorkbenchEdge] = field(default_factory=dict)
    registry: EntityKindRegistry = field(default_factory=lambda: default_registry)

    @classmethod
    def from_records(
        cls,
        records: tuple[EntityRecord, ...] | list[EntityRecord],
        links: tuple[EntityLink, ...] | list[EntityLink] = (),
        *,
        registry: EntityKindRegistry | None = None,
    ) -> WorkbenchGraph:
        """Build a graph from universal records and links."""
        graph = cls(registry=registry or default_registry)
        for record in records:
            graph.upsert_node(WorkbenchNode.from_record(record))
        for link in links:
            graph.upsert_edge(WorkbenchEdge.from_link(link))
        return graph

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> WorkbenchGraph:
        """Restore a graph from a snapshot-style JSON payload."""
        graph = cls()
        for item in data.get("nodes", ()):
            node = WorkbenchNode.from_dict(dict(item))
            graph.upsert_node(node)
        for item in data.get("edges", ()):
            graph.upsert_edge(WorkbenchEdge.from_dict(dict(item)))
        return graph

    def copy(self) -> WorkbenchGraph:
        """Return a structural copy that can be mutated independently."""
        return WorkbenchGraph(
            nodes=dict(self.nodes),
            edges=dict(self.edges),
            registry=self.registry,
        )

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Return sorted node keys."""
        return tuple(sorted(self.nodes))

    @property
    def edge_keys(self) -> tuple[tuple[str, str, str], ...]:
        """Return sorted edge keys."""
        return tuple(sorted(self.edges))

    def __len__(self) -> int:
        """Return the vertex count."""
        return len(self.nodes)

    def upsert_node(self, node: WorkbenchNode) -> None:
        """Insert or replace one vertex."""
        self.nodes[node.id] = node

    def upsert_edge(self, edge: WorkbenchEdge) -> None:
        """Insert or replace one typed relationship."""
        self.edges[edge.key] = edge

    def remove_node(self, node_id: str) -> WorkbenchNode | None:
        """Remove a vertex and every incident relationship."""
        removed = self.nodes.pop(node_id, None)
        if removed is not None:
            for key in [
                key for key, edge in self.edges.items() if node_id in (edge.source, edge.target)
            ]:
                del self.edges[key]
        return removed

    def remove_edge(self, key: tuple[str, str, str]) -> WorkbenchEdge | None:
        """Remove one relationship by key."""
        return self.edges.pop(key, None)

    def has_node(self, node_id: str) -> bool:
        """Return whether a vertex exists."""
        return node_id in self.nodes

    def node(self, node_id: str) -> WorkbenchNode:
        """Return a vertex or raise a descriptive error."""
        try:
            return self.nodes[node_id]
        except KeyError as error:
            raise ValueError(f"Unknown workbench node: {node_id}") from error

    def incident(self, node_id: str) -> tuple[WorkbenchEdge, ...]:
        """Return all relationships incident to a vertex in stable order."""
        self.node(node_id)
        return tuple(
            self.edges[key]
            for key in self.edge_keys
            if node_id in (self.edges[key].source, self.edges[key].target)
        )

    def neighbors(self, node_id: str, *, directed: bool = False) -> tuple[str, ...]:
        """Return adjacent node keys in deterministic order."""
        self.node(node_id)
        found: set[str] = set()
        for edge in self.incident(node_id):
            if directed and edge.source == node_id:
                found.add(edge.target)
            elif directed:
                continue
            else:
                found.add(edge.other(node_id))
        return tuple(sorted(found))

    def degree(self, node_id: str) -> int:
        """Return the number of incident relationships."""
        return len(self.incident(node_id))

    def induced(self, node_ids: frozenset[str] | set[str]) -> WorkbenchGraph:
        """Return the subgraph induced by a set of vertices."""
        kept = set(node_ids) & set(self.nodes)
        graph = WorkbenchGraph(registry=self.registry)
        graph.nodes = {key: self.nodes[key] for key in sorted(kept)}
        graph.edges = {
            key: edge
            for key, edge in self.edges.items()
            if edge.source in kept and edge.target in kept
        }
        return graph

    def of_kind(self, kind: EntityKind | str) -> tuple[WorkbenchNode, ...]:
        """Return vertices of one entity kind."""
        key = kind.value if isinstance(kind, EntityKind) else kind.casefold()
        return tuple(self.nodes[item] for item in self.node_ids if self.nodes[item].kind == key)

    def link_graph(self) -> LinkGraph:
        """Project the workbench graph back onto the universal link graph."""
        return LinkGraph(tuple(edge.as_link() for edge in self.edges.values()))

    def tag_counts(self) -> dict[str, int]:
        """Return case-folded tag usage counts."""
        counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            for tag in node.tag_set:
                counts[tag] += 1
        return dict(sorted(counts.items()))

    def stats(self) -> dict[str, int]:
        """Return compact structural counts."""
        kinds: dict[str, int] = defaultdict(int)
        severities: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            kinds[node.kind] += 1
            severities[node.severity] += 1
        result = {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "components": 0,
        }
        result.update({f"kind_{key}": value for key, value in sorted(kinds.items())})
        result.update({f"severity_{key}": value for key, value in sorted(severities.items())})
        return result

    def kind_color(self, kind: str) -> str:
        """Return the registered color for a kind."""
        return self.registry.get(kind).color

    def validate(self) -> tuple[str, ...]:
        """Return integrity problems found in the graph."""
        problems: list[str] = []
        for key in self.edge_keys:
            edge = self.edges[key]
            if edge.source not in self.nodes:
                problems.append(f"edge {key} has unknown source")
            if edge.target not in self.nodes:
                problems.append(f"edge {key} has unknown target")
            if edge.source == edge.target:
                problems.append(f"edge {key} is a self loop")
        for node_id in self.node_ids:
            node = self.nodes[node_id]
            if node.ref.entity_id.kind.value != node.kind:
                problems.append(f"node {node_id} has mismatched kind")
        return tuple(problems)

    def as_dict(self, *, include_metadata: bool = True) -> dict[str, Any]:
        """Return a JSON-safe representation of the whole graph."""
        nodes = []
        for node_id in self.node_ids:
            payload = self.nodes[node_id].as_dict()
            if not include_metadata:
                payload["metadata"] = {}
            nodes.append(payload)
        return {
            "nodes": nodes,
            "edges": [self.edges[key].as_dict() for key in self.edge_keys],
        }


def graph_from_entity_snapshot(snapshot: dict[str, Any]) -> WorkbenchGraph:
    """Build a workbench graph from ``EntityService.snapshot()`` output."""
    records: list[EntityRecord] = []
    for item in snapshot.get("records", ()):
        entity_id = EntityId.parse(str(item["entity_id"]))
        records.append(
            EntityRecord(
                entity_id=entity_id,
                title=str(item["title"]),
                status=EntityStatus(str(item.get("status", "draft"))),
                tags=tuple(str(tag) for tag in item.get("tags", ())),
                summary=str(item.get("summary", "")),
                owner=str(item.get("owner", "")),
                created_at=float(item.get("created_at", 0.0)),
                updated_at=float(item.get("updated_at", 0.0)),
                version=int(item.get("version", 1)),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    links = tuple(
        EntityLink(
            source=EntityId.parse(str(item["source"])),
            target=EntityId.parse(str(item["target"])),
            kind=LinkKind.parse(str(item.get("kind", "relates"))),
            label=str(item.get("label", "")),
            weight=float(item.get("weight", 1.0)),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in snapshot.get("links", ())
    )
    return WorkbenchGraph.from_records(records, links)
