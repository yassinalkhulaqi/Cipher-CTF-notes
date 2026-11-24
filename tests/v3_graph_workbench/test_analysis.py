"""Tests for path explanations, cut vertices, and structural analysis."""

from __future__ import annotations

import pytest

from redscribe.v3.entities import EntityId, EntityKind, EntityLink, EntityRecord, LinkKind
from redscribe.v3.graph_workbench.analysis import (
    articulation_points,
    bridges,
    build_adjacency,
    connected_components,
    neighborhood,
    shortest_path,
    structural_summary,
)
from redscribe.v3.graph_workbench.model import (
    WorkbenchEdge,
    WorkbenchGraph,
    WorkbenchNode,
)
from tests.v3_graph_workbench import build_graph


def chain_graph(size: int) -> WorkbenchGraph:
    """Build a deterministic chain of notes, optionally closed into a cycle."""
    graph = WorkbenchGraph()
    for index in range(size):
        graph.upsert_node(
            WorkbenchNode.from_record(
                EntityRecord(EntityId(EntityKind.NOTE, f"n{index}"), title=f"Node {index}")
            )
        )
    for index in range(size - 1):
        graph.upsert_edge(
            WorkbenchEdge.from_link(
                EntityLink(
                    EntityId(EntityKind.NOTE, f"n{index}"),
                    EntityId(EntityKind.NOTE, f"n{index + 1}"),
                    LinkKind.RELATES,
                )
            )
        )
    return graph


def test_build_adjacency_is_deterministic() -> None:
    graph = build_graph()
    adjacency = build_adjacency(graph)
    assert adjacency["note:root"]["finding:sql-001"].kind is LinkKind.EVIDENCES
    assert build_adjacency(graph) == adjacency
    directed = build_adjacency(graph, directed=True)
    assert "finding:sql-001" not in directed["target:host-01"]
    filtered = build_adjacency(graph, kinds=("evidences",))
    assert set(filtered["note:root"]) == {"finding:sql-001"}
    assert set(adjacency["note:root"]) == {"finding:sql-001", "target:host-01"}


def test_shortest_path_and_explanations() -> None:
    graph = build_graph()
    result = shortest_path(graph, "note:root", "evidence:cap-01")
    assert result.found
    assert result.node_ids == ("note:root", "finding:sql-001", "evidence:cap-01")
    assert result.hops == 2
    assert result.cost == 2.0
    assert len(result.steps) == 2
    assert result.steps[0].kind == "evidences"
    assert result.steps[0].direction == "forward"
    assert result.steps[0].explanation.startswith("Step 1: Root note points to SQL finding")
    assert result.explanations() == tuple(step.explanation for step in result.steps)
    assert result.labels(graph)[0] == "Root note"
    assert result.as_dict()["found"] is True


def test_shortest_path_same_node_and_disconnected() -> None:
    graph = build_graph()
    same = shortest_path(graph, "note:root", "note:root")
    assert same.node_ids == ("note:root",)
    assert same.hops == 0
    assert same.steps == ()
    isolated = WorkbenchGraph()
    for name in ("solo", "other"):
        isolated.upsert_node(
            WorkbenchNode.from_record(
                EntityRecord(EntityId(EntityKind.NOTE, name), title=name.title())
            )
        )
    result = shortest_path(graph, "note:root", "target:host-01")
    assert result.found
    assert shortest_path(isolated, "note:solo", "note:other").found is False


def test_shortest_path_options_and_validation() -> None:
    graph = build_graph()
    directed = shortest_path(graph, "target:host-01", "note:root", directed=True)
    assert directed.found is False
    weighted = shortest_path(graph, "note:root", "evidence:cap-01", weighted=True)
    assert weighted.cost >= 0
    bounded = shortest_path(graph, "note:root", "evidence:cap-01", max_hops=1)
    assert bounded.found is False
    with pytest.raises(ValueError, match="Unknown workbench node"):
        shortest_path(graph, "note:root", "note:missing")
    with pytest.raises(ValueError, match="max_hops"):
        shortest_path(graph, "note:root", "note:root", max_hops=-1)


def test_connected_components() -> None:
    graph = build_graph()
    components = connected_components(graph)
    assert len(components) == 1
    assert components[0].size == 4
    assert components[0].as_dict()["index"] == 1
    chain = chain_graph(5)
    chain.remove_edge(("note:n1", "note:n2", "relates"))
    groups = connected_components(chain)
    assert len(groups) == 2
    assert groups[0].node_ids == ("note:n2", "note:n3", "note:n4")
    assert groups[1].node_ids == ("note:n0", "note:n1")


def test_articulation_points_in_chain_and_star() -> None:
    chain = chain_graph(5)
    cuts = articulation_points(chain)
    assert {item.node_id for item in cuts} == {"note:n1", "note:n2", "note:n3"}
    middle = next(item for item in cuts if item.node_id == "note:n2")
    assert middle.component_count == 2
    assert middle.severity == "medium"
    assert middle.as_dict()["label"] == "Node 2"

    star = WorkbenchGraph()
    for name in ("hub", "a", "b", "c"):
        star.upsert_node(
            WorkbenchNode.from_record(EntityRecord(EntityId(EntityKind.NOTE, name), title=name))
        )
    for leaf in ("a", "b", "c"):
        star.upsert_edge(
            WorkbenchEdge.from_link(
                EntityLink(
                    EntityId(EntityKind.NOTE, "hub"),
                    EntityId(EntityKind.NOTE, leaf),
                    LinkKind.RELATES,
                )
            )
        )
    cuts = articulation_points(star)
    assert len(cuts) == 1
    assert cuts[0].node_id == "note:hub"
    assert cuts[0].component_count == 3
    assert cuts[0].severity == "high"


def test_cycle_has_no_articulation_points() -> None:
    graph = chain_graph(4)
    graph.upsert_edge(
        WorkbenchEdge.from_link(
            EntityLink(
                EntityId(EntityKind.NOTE, "n3"),
                EntityId(EntityKind.NOTE, "n0"),
                LinkKind.RELATES,
            )
        )
    )
    assert articulation_points(graph) == ()
    assert bridges(graph) == ()


def test_bridges_in_a_chain() -> None:
    chain = chain_graph(4)
    result = bridges(chain)
    assert len(result) == 3
    assert all(item.kind == "relates" for item in result)
    assert result[0].as_dict()["source"] == "note:n0"


def test_neighborhood_and_structural_summary() -> None:
    graph = build_graph()
    near = neighborhood(graph, "note:root", depth=1)
    assert near["count"] == 3
    assert len(near["edges"]) == 2
    deeper = neighborhood(graph, "note:root", depth=2)
    assert deeper["count"] == 4
    summary = structural_summary(graph)
    assert summary["nodes"] == 4
    assert summary["edges"] == 3
    assert summary["components"] == 1
    assert summary["cut_vertices"] == 2
    assert summary["bridges"] == 3
    with pytest.raises(ValueError, match="depth"):
        neighborhood(graph, "note:root", depth=0)
