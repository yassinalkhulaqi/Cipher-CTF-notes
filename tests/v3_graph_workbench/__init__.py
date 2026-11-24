"""Test helpers shared by the graph-workbench test modules."""

from __future__ import annotations

from redscribe.v3.entities import EntityService, LinkGraph, LinkKind
from redscribe.v3.graph_workbench.model import WorkbenchGraph, graph_from_entity_snapshot

FIXTURE_TAGS = ("alpha", "beta", "severity/high")


def build_service() -> EntityService:
    """Create an entity service with a small, deterministic graph."""
    service = EntityService()
    root = service.create(
        "note",
        title="Root note",
        value="root",
        tags=["alpha", "severity/high"],
        metadata={"severity": "high"},
    )
    finding = service.create(
        "finding",
        title="SQL finding",
        value="sql-001",
        tags=["beta"],
        metadata={"severity": "critical", "cvss": 9.1},
    )
    evidence = service.create(
        "evidence",
        title="Capture",
        value="cap-01",
        tags=["alpha"],
        metadata={"severity": "low"},
    )
    target = service.create("target", title="Host 10.0.0.1", value="host-01", tags=["beta"])
    service.link(root.entity_id, finding.entity_id, kind=LinkKind.EVIDENCES, label="supports")
    service.link(finding.entity_id, evidence.entity_id, kind=LinkKind.DERIVES)
    service.link(root.entity_id, target.entity_id, kind=LinkKind.RELATES)
    return service


def build_graph() -> WorkbenchGraph:
    """Return a workbench graph built from the shared fixture."""
    service = build_service()
    return graph_from_entity_snapshot(service.snapshot())


def ids(graph: WorkbenchGraph) -> tuple[str, ...]:
    """Return stable node keys of a graph."""
    return graph.node_ids


def assert_link(graph: WorkbenchGraph, source: str, target: str, kind: str) -> bool:
    """Return whether a typed link exists."""
    return any(
        edge.source == source and edge.target == target and edge.kind.value == kind
        for edge in graph.edges.values()
    )


__all__ = [
    "FIXTURE_TAGS",
    "LinkGraph",
    "assert_link",
    "build_graph",
    "build_service",
    "ids",
]
