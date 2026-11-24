"""Tests for workbench node, edge, and graph model adaptation."""

from __future__ import annotations

import pytest

from redscribe.v3.entities import EntityId, EntityKind, EntityLink, EntityRecord, LinkKind
from redscribe.v3.graph_workbench.model import (
    Severity,
    WorkbenchEdge,
    WorkbenchGraph,
    WorkbenchNode,
    graph_from_entity_snapshot,
    severity_from_metadata,
)
from tests.v3_graph_workbench import build_graph, build_service


def test_severity_from_metadata_prefers_string_fields() -> None:
    assert severity_from_metadata({"severity": "HIGH"}, ()) is Severity.HIGH
    assert severity_from_metadata({"risk": "informational"}, ()) is Severity.INFO
    assert severity_from_metadata({"impact": "moderate"}, ()) is Severity.MEDIUM


def test_severity_from_numeric_score_and_tags() -> None:
    assert severity_from_metadata({"cvss": 9.4}, ()) is Severity.CRITICAL
    assert severity_from_metadata({"score": 5.0}, ()) is Severity.MEDIUM
    assert severity_from_metadata({}, ("severity/high",)) is Severity.HIGH
    assert severity_from_metadata({}, ("#severity:low",)) is Severity.LOW
    assert severity_from_metadata({}, ()) is Severity.UNKNOWN


def test_severity_aliases_and_rank() -> None:
    assert Severity.parse("severe") is Severity.HIGH
    assert Severity.parse("not-a-level") is Severity.UNKNOWN
    assert Severity.LOW.rank < Severity.CRITICAL.rank
    assert Severity.CRITICAL.value == "critical"


def test_workbench_node_from_record() -> None:
    record = EntityRecord(
        entity_id=EntityId(EntityKind.FINDING, "f-1"),
        title="Broken auth",
        tags=["web", "web", "severity/high"],
        metadata={"severity": "high"},
        version=3,
    )
    node = WorkbenchNode.from_record(record)
    assert node.id == "finding:f-1"
    assert node.kind == "finding"
    assert node.tags == ("severity/high", "web")
    assert node.severity == "high"
    assert node.version == 3
    assert node.label == "Broken auth"


def test_workbench_node_validation() -> None:
    ref = WorkbenchNode.from_record(EntityRecord(EntityId(EntityKind.NOTE, "n"), title="Note"))
    payload = ref.as_dict()
    payload["version"] = 0
    with pytest.raises(ValueError, match="version"):
        WorkbenchNode.from_dict(payload)


def test_workbench_node_roundtrip() -> None:
    original = build_graph().node("note:root").as_dict()
    node = WorkbenchNode.from_dict(original)
    assert node.as_dict() == original
    assert node.entity_id.kind is EntityKind.NOTE
    assert node.tag_set == frozenset({"alpha", "severity/high"})


def test_workbench_node_with_updates_is_immutable() -> None:
    original = WorkbenchNode.from_dict(build_graph().node("note:root").as_dict())
    updated = original.with_updates(title="Changed")
    assert updated.title == "Changed"
    assert original.title == "Root note"


def test_workbench_edge_properties_and_roundtrip() -> None:
    link = EntityLink(
        source=EntityId(EntityKind.NOTE, "a"),
        target=EntityId(EntityKind.FINDING, "b"),
        kind=LinkKind.EVIDENCES,
        label="proof",
        weight=0.75,
    )
    edge = WorkbenchEdge.from_link(link)
    assert edge.key == ("note:a", "finding:b", "evidences")
    assert edge.label == "proof"
    assert edge.weight == 0.75
    assert edge.other("note:a") == "finding:b"
    assert edge.other("finding:b") == "note:a"
    with pytest.raises(ValueError, match="not incident"):
        edge.other("note:z")
    assert WorkbenchEdge.from_dict(edge.as_dict()).as_dict() == edge.as_dict()


def test_undirected_edge_key_is_stable() -> None:
    link = EntityLink(
        EntityId(EntityKind.NOTE, "a"), EntityId(EntityKind.NOTE, "b"), LinkKind.RELATES
    )
    reverse = EntityLink(
        EntityId(EntityKind.NOTE, "b"), EntityId(EntityKind.NOTE, "a"), LinkKind.RELATES
    )
    assert (
        WorkbenchEdge.from_link(link).undirected_key
        == WorkbenchEdge.from_link(reverse).undirected_key
    )


def test_graph_from_entity_snapshot() -> None:
    service = build_service()
    graph = graph_from_entity_snapshot(service.snapshot())
    assert len(graph) == 4
    assert len(graph.edges) == 3
    assert graph.validate() == ()
    assert graph.stats()["nodes"] == 4
    assert graph.stats()["severity_critical"] == 1
    assert graph.tag_counts()["alpha"] == 2


def test_graph_node_and_edge_operations() -> None:
    graph = build_graph()
    assert graph.has_node("note:root")
    assert set(graph.neighbors("note:root")) == {"finding:sql-001", "target:host-01"}
    assert graph.degree("note:root") == 2
    assert len(graph.incident("note:root")) == 2
    assert len(graph.of_kind("finding")) == 1
    assert len(graph.link_graph()) == 3
    with pytest.raises(ValueError, match="Unknown workbench node"):
        graph.node("note:missing")


def test_graph_copy_and_induced_subgraphs() -> None:
    graph = build_graph()
    subset = graph.induced(frozenset({"note:root", "finding:sql-001"}))
    assert len(subset) == 2
    assert len(subset.edges) == 1
    assert graph.node("note:root") is subset.node("note:root")
    copied = graph.copy()
    copied.remove_node("note:root")
    assert len(copied) == 3
    assert len(copied.edges) == 1
    assert len(graph) == 4


def test_graph_payload_roundtrip() -> None:
    graph = build_graph()
    payload = graph.as_dict()
    restored = WorkbenchGraph.from_payload(payload)
    assert restored.as_dict() == payload
    assert restored.validate() == ()
    lightweight = graph.as_dict(include_metadata=False)
    assert all(not node["metadata"] for node in lightweight["nodes"])


def test_graph_validation_detects_problems() -> None:
    graph = build_graph()
    broken = WorkbenchEdge.from_link(
        EntityLink(
            EntityId(EntityKind.NOTE, "a"),
            EntityId(EntityKind.NOTE, "b"),
            LinkKind.RELATES,
        )
    )
    graph.upsert_edge(broken)
    problems = graph.validate()
    assert any("unknown source" in problem for problem in problems)
    assert graph.kind_color("evidence").startswith("#")
