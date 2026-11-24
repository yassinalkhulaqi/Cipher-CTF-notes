"""Tests for DOT, JSON, and Mermaid exporters."""

from __future__ import annotations

import json

import pytest

from redscribe.v3.entities import EntityId, EntityKind, EntityLink, LinkKind
from redscribe.v3.graph_workbench.clustering import cluster_graph
from redscribe.v3.graph_workbench.exports import (
    EXPORT_FORMATS,
    ExportFormat,
    export_graph,
    to_dot,
    to_json,
    to_mermaid,
)
from redscribe.v3.graph_workbench.model import WorkbenchEdge, WorkbenchNode
from tests.v3_graph_workbench import build_graph


def test_export_format_parse_and_registry() -> None:
    assert ExportFormat.parse("DOT") is ExportFormat.DOT
    assert ExportFormat.parse("mermaid") is ExportFormat.MERMAID
    assert EXPORT_FORMATS == ("dot", "json", "mermaid")
    with pytest.raises(ValueError, match="Unknown export format"):
        ExportFormat.parse("svg")


def test_dot_export_structure() -> None:
    graph = build_graph()
    text = to_dot(graph)
    assert text.startswith("digraph graph_workbench {")
    assert text.endswith("}")
    assert "rankdir=LR" in text
    assert '"note:root" -> "finding:sql-001"' in text
    assert 'label="supports"' in text
    assert "subgraph" not in text
    assert len([line for line in text.splitlines() if "->" in line]) == 3


def test_dot_export_highlight_and_clusters() -> None:
    graph = build_graph()
    result = to_dot(
        graph,
        rankdir="TB",
        highlight=frozenset({"note:root"}),
        clusters=cluster_graph(graph, "tag"),
    )
    assert "rankdir=TB" in result
    assert "subgraph cluster_0" in result
    assert 'label="alpha"' in result
    assert "penwidth=2.5" in result


def test_dot_export_escapes_labels() -> None:
    graph = build_graph()
    original = graph.node("note:root")
    graph.nodes["note:root"] = WorkbenchNode(
        ref=original.ref,
        title='A "quoted" \\ node\nwith lines',
        kind=original.kind,
        tags=original.tags,
        metadata=dict(original.metadata),
    )
    text = to_dot(graph)
    assert '\\"quoted\\"' in text
    assert "\\n" in text
    assert 'tooltip="A \\"quoted\\" \\\\ node\\nwith lines"' in text


def test_json_export_is_stable_and_optional_metadata() -> None:
    graph = build_graph()
    compact = to_json(graph)
    assert json.loads(compact) == json.loads(to_json(graph))
    assert "\n" not in compact
    payload = json.loads(compact)
    assert payload["generator"] == "redscribe.graph_workbench"
    assert len(payload["graph"]["nodes"]) == 4
    pretty = to_json(graph, pretty=True, include_metadata=False)
    assert "\n" in pretty
    assert all(not node["metadata"] for node in json.loads(pretty)["graph"]["nodes"])


def test_mermaid_export_structure() -> None:
    graph = build_graph()
    text = to_mermaid(graph)
    assert text.startswith("flowchart LR")
    assert ":::kind_note" in text
    assert ":::kind_finding" in text
    assert "-->|supports|" in text
    assert "classDef kind_note fill:" in text
    assert "subgraph" not in text


def test_mermaid_export_clusters_and_escapes() -> None:
    graph = build_graph()
    text = to_mermaid(graph, direction="TB", clusters=cluster_graph(graph, "tag"))
    assert text.startswith("flowchart TB")
    assert "subgraph SG_kind_alpha" in text
    original = graph.node("note:root")
    from redscribe.v3.entities import EntityRef

    graph.nodes["note:root"] = WorkbenchNode(
        ref=EntityRef(original.entity_id, 'A <b>bold</b> "title"|pipe'),
        title='A <b>bold</b> "title"|pipe',
        kind=original.kind,
        tags=original.tags,
    )
    escaped = to_mermaid(graph)
    assert "#quot;" in escaped
    assert "&lt;b&gt;" in escaped
    assert "&#124;" in escaped


def test_export_dispatch_and_validation() -> None:
    graph = build_graph()
    for name in EXPORT_FORMATS:
        result = export_graph(graph, name)
        assert result.fmt == name
        assert result.node_count == 4
        assert result.edge_count == 3
        assert result.size == len(result.content)
        assert result.as_dict()["mime"] == result.mime
    with pytest.raises(ValueError, match="rankdir"):
        to_dot(graph, rankdir="DIAGONAL")
    with pytest.raises(ValueError, match="direction"):
        to_mermaid(graph, direction="SIDEWAYS")
    with pytest.raises(ValueError, match="Unknown export format"):
        export_graph(graph, "pdf")


def test_export_handles_empty_graph() -> None:
    graph = build_graph().induced(frozenset())
    assert to_dot(graph).count("[label=") == 0
    assert json.loads(to_json(graph))["graph"]["nodes"] == []
    assert to_mermaid(graph).count("-->") == 0


def test_export_ignores_edges_with_missing_endpoints() -> None:
    graph = build_graph()
    graph.upsert_edge(
        WorkbenchEdge.from_link(
            EntityLink(
                EntityId(EntityKind.NOTE, "ghost"),
                EntityId(EntityKind.NOTE, "phantom"),
                LinkKind.RELATES,
            )
        )
    )
    assert "ghost" in to_dot(graph)
    assert len(graph.validate()) >= 2
