from __future__ import annotations

import pytest

from redscribe.v2.graph.model import (
    EDGE_KINDS,
    NODE_KINDS,
    EdgeKind,
    GraphEdge,
    GraphModel,
    GraphNode,
    NodeKind,
)


def node(node_id: int, label: str = "", **kwargs: object) -> GraphNode:
    return GraphNode(id=node_id, label=label or f"Node {node_id}", **kwargs)


def edge(source: int, target: int, kind: str = "link", **kwargs: object) -> GraphEdge:
    return GraphEdge(source=source, target=target, kind=kind, **kwargs)


def test_node_kinds_and_edge_kinds_are_complete() -> None:
    assert [item.value for item in NodeKind] == list(NODE_KINDS)
    assert [item.value for item in EdgeKind] == list(EDGE_KINDS)
    assert NodeKind.NOTE == "note"
    assert EdgeKind.MENTION == "mention"


def test_graph_node_exposes_stable_views() -> None:
    item = node(1, "Alpha", tags=("Web", "RECON"), status="active", pinned=True, weight=2.0)
    assert item.title == "Alpha"
    assert item.tag_set == frozenset({"web", "recon"})
    payload = item.as_dict()
    assert payload["id"] == 1
    assert payload["label"] == "Alpha"
    assert payload["tags"] == ["Web", "RECON"]
    assert payload["pinned"] is True
    assert payload["weight"] == 2.0
    assert payload["metadata"] == {}


def test_graph_node_validation() -> None:
    with pytest.raises(ValueError, match="node kind"):
        node(1, kind="artifact")
    with pytest.raises(ValueError, match="weight"):
        node(1, weight=-1)


def test_graph_edge_identity_and_views() -> None:
    item = edge(1, 2, alias="other", weight=1.5, resolved=False)
    assert item.key == (1, 2, "link")
    assert item.undirected_key == (1, 2, "link")
    reversed_item = item.reversed()
    assert reversed_item.source == 2
    assert reversed_item.target == 1
    assert reversed_item.key == (2, 1, "link")
    reversed_item.metadata["seen"] = True
    assert "seen" not in item.metadata
    payload = item.as_dict()
    assert payload["alias"] == "other"
    assert payload["resolved"] is False
    assert payload["weight"] == 1.5


def test_graph_edge_validation() -> None:
    with pytest.raises(ValueError, match="edge kind"):
        edge(1, 2, kind="related")
    with pytest.raises(ValueError, match="weight"):
        edge(1, 2, weight=-0.1)


def test_model_from_records_indexes_all_records() -> None:
    model = GraphModel.from_records(
        [node(1, "Alpha"), node(2, "Beta"), node(3, "Gamma", kind="reference")],
        [edge(1, 2), edge(2, 3, kind="mention", resolved=False)],
    )
    assert model.size == 3
    assert model.edge_count == 2
    assert model.has_node(1)
    assert not model.has_node(99)
    assert model.get_node(2) is not None
    assert model.get_node(2).label == "Beta"
    assert model.outgoing(1) == (2,)
    assert model.incoming(3) == (2,)
    assert model.neighbors(2) == (1, 3)
    assert model.neighbors(2, kinds=("link",)) == (1,)
    assert [item.source for item in model.edges_for(2)] == [1, 2]
    assert [item.id for item in model.nodes_of_kind("reference")] == [3]


def test_model_upsert_edge_creates_placeholder_vertices() -> None:
    model = GraphModel()
    model.upsert_edge(edge(4, 5, kind="tag"))
    assert model.size == 2
    assert model.get_node(4) is not None
    assert model.get_node(4).label == ""
    assert model.get_node(5).resolved is True


def test_model_remove_node_removes_incident_edges() -> None:
    model = GraphModel.from_records(
        [node(1), node(2), node(3)],
        [edge(1, 2), edge(2, 3), edge(3, 1, kind="mention")],
    )
    removed = model.remove_node(2)
    assert removed is not None
    assert removed.id == 2
    assert model.size == 2
    assert model.edge_count == 1
    assert model.neighbors(1) == (3,)
    assert model.remove_node(2) is None


def test_model_remove_edge_by_record_and_key() -> None:
    item = edge(1, 2)
    model = GraphModel.from_records([node(1), node(2)], [item, edge(2, 1, kind="tag")])
    assert model.remove_edge(item) is item
    assert model.remove_edge((2, 1, "tag")) is not None
    assert model.edge_count == 0
    assert model.remove_edge((9, 9, "link")) is None


def test_model_induced_copy_and_as_dict() -> None:
    model = GraphModel.from_records(
        [node(1, "Alpha", tags=("web",)), node(2, "Beta"), node(3, "Gamma")],
        [edge(1, 2), edge(2, 3)],
    )
    subset = model.induced(frozenset({1, 2}))
    assert subset.size == 2
    assert subset.edge_count == 1
    copy = model.copy()
    copy.upsert_node(node(9))
    assert model.size == 3
    assert copy.size == 4
    payload = model.as_dict()
    assert [item["id"] for item in payload["nodes"]] == [1, 2, 3]
    assert [item["source"] for item in payload["edges"]] == [1, 2]


def test_model_validate_reports_broken_edges_and_self_loops() -> None:
    model = GraphModel()
    model.nodes[1] = node(1)
    model.nodes[2] = node(2)
    model.edges[(1, 2, "link")] = edge(1, 2)
    model.edges[(9, 1, "link")] = edge(9, 1)
    model.edges[(1, 1, "tag")] = edge(1, 1, kind="tag")
    problems = model.validate()
    assert any("unknown source" in item for item in problems)
    assert any("self loop" in item for item in problems)
    assert GraphModel.from_records([node(1), node(2)], [edge(1, 2)]).validate() == ()


def test_model_validate_reports_key_mismatch() -> None:
    model = GraphModel()
    model.nodes[1] = node(2)
    problems = model.validate()
    assert any("does not match" in item for item in problems)


def test_model_neighbor_kind_filtering_is_deterministic() -> None:
    model = GraphModel.from_records(
        [node(index) for index in range(1, 5)],
        [
            edge(1, 2, kind="link"),
            edge(3, 1, kind="mention"),
            edge(1, 4, kind="tag"),
            edge(4, 2, kind="parent"),
        ],
    )
    assert model.neighbors(1) == (2, 3, 4)
    assert model.neighbors(1, kinds=("link", "parent")) == (2,)
    assert model.outgoing(1, kinds=("link", "tag")) == (2, 4)
    assert model.incoming(1, kinds=("mention",)) == (3,)
    assert model.edges_for(99) == ()
    assert model.nodes_of_kind("folder") == ()


def test_model_induced_ignores_unknown_ids() -> None:
    model = GraphModel.from_records([node(1), node(2)], [edge(1, 2)])
    subset = model.induced({1, 99})
    assert subset.size == 1
    assert subset.edge_count == 0
