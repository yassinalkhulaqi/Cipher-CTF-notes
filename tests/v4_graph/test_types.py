from __future__ import annotations

import pytest

from redscribe.v4.contracts import EntityKind, EntityRef
from redscribe.v4.graph_v4.types import (
    MAX_FILTER_TEXT_LENGTH,
    MAX_LABEL_LENGTH,
    FilterResult,
    GraphData,
    GraphEdge,
    GraphFilter,
    GraphMetrics,
    GraphNode,
    GraphPoint,
    GraphSnapshot,
    LayoutKind,
    LayoutResult,
    RelationStat,
)

from .conftest import NODE_A, NODE_B, NODE_C, NODE_D


def node(node_id: str = NODE_A, kind: EntityKind = EntityKind.NOTE) -> GraphNode:
    return GraphNode(id=node_id, kind=kind, label="A sample node", weight=0.8)


def edge(
    source: str = NODE_A,
    target: str = NODE_B,
    relation: str = "linked_to",
    weight: float = 0.7,
) -> GraphEdge:
    return GraphEdge(source=source, target=target, relation=relation, weight=weight)


def test_layout_kind_parse_and_label() -> None:
    assert LayoutKind.parse(" force ") is LayoutKind.FORCE
    assert LayoutKind.parse("CIRCULAR") is LayoutKind.CIRCULAR
    assert LayoutKind.parse("grid") is LayoutKind.GRID
    assert LayoutKind.GRID.label == "Grid"
    with pytest.raises(ValueError, match="unknown layout kind"):
        LayoutKind.parse("radial")


def test_graph_node_validates_identity() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        GraphNode(id="  ", kind=EntityKind.NOTE, label="x")
    with pytest.raises(ValueError, match="invalid node id"):
        GraphNode(id="bad id!", kind=EntityKind.NOTE, label="x")
    with pytest.raises(ValueError, match="invalid node kind"):
        GraphNode(id=NODE_A, kind="note", label="x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="label must not be empty"):
        GraphNode(id=NODE_A, kind=EntityKind.NOTE, label=" ")
    with pytest.raises(ValueError, match="at most"):
        GraphNode(id=NODE_A, kind=EntityKind.NOTE, label="x" * (MAX_LABEL_LENGTH + 1))


def test_graph_node_weight_bounds_and_trim() -> None:
    item = GraphNode(id=f" {NODE_A} ", kind=EntityKind.NOTE, label=" padded ", weight=0.2)
    assert item.id == NODE_A
    assert item.label == "padded"
    for weight in (-0.01, 1.01, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="weight must be"):
            GraphNode(id=NODE_A, kind=EntityKind.NOTE, label="x", weight=weight)


def test_graph_node_entity_ref_round_trip() -> None:
    ref = EntityRef(kind=EntityKind.FINDING, id=NODE_B, label="Finding B")
    item = GraphNode.from_ref(ref, weight=0.4)
    assert item.kind is EntityKind.FINDING
    assert item.label == "Finding B"
    assert item.weight == 0.4
    assert item.to_ref() == ref
    assert item.is_entity_backed()

    inferred = GraphNode.from_ref(EntityRef(kind=EntityKind.RUN, id=NODE_C))
    assert inferred.label == "Run"
    assert not GraphNode(id="local-slug", kind=EntityKind.NOTE, label="x").is_entity_backed()


def test_graph_node_dict_round_trip() -> None:
    item = node()
    restored = GraphNode.from_dict(item.to_dict())
    assert restored == item
    assert item.to_dict()["kind"] == "note"
    with pytest.raises(ValueError, match="entity kind"):
        GraphNode.from_dict({"id": NODE_A, "kind": "unknown", "label": "x"})
    with pytest.raises(ValueError, match="invalid weight"):
        GraphNode.from_dict({"id": NODE_A, "kind": "note", "label": "x", "weight": "heavy"})


def test_graph_edge_validation_and_key() -> None:
    item = edge()
    assert item.key == (NODE_A, NODE_B, "linked_to")
    assert item.reversed().key == (NODE_B, NODE_A, "linked_to")
    with pytest.raises(ValueError, match="same node twice"):
        GraphEdge(source=NODE_A, target=NODE_A, relation="linked_to")
    with pytest.raises(ValueError, match="invalid relation slug"):
        GraphEdge(source=NODE_A, target=NODE_B, relation="Bad Rel!")
    with pytest.raises(ValueError, match="weight must be"):
        GraphEdge(source=NODE_A, target=NODE_B, relation="linked_to", weight=2.0)


def test_graph_edge_dict_round_trip() -> None:
    item = edge(relation="finding.supports", weight=0.33)
    restored = GraphEdge.from_dict(item.to_dict())
    assert restored == item
    assert restored.relation == "finding.supports"
    upper = GraphEdge.from_dict({"source": NODE_A, "target": NODE_B, "relation": "MENTIONS"})
    assert upper.relation == "mentions"


def test_graph_filter_defaults_and_node_matching() -> None:
    flt = GraphFilter()
    assert flt.is_empty()
    assert flt.matches_node(node())
    note_only = flt.with_kind(EntityKind.NOTE)
    assert not note_only.is_empty()
    assert note_only.matches_node(node())
    assert not note_only.matches_node(node(NODE_B, EntityKind.TARGET))
    assert note_only.without_kind(EntityKind.NOTE).is_empty()
    needle = flt.with_label(" SAMPLE ")
    assert needle.label_contains == "SAMPLE"
    assert needle.matches_node(node())
    assert not needle.matches_node(GraphNode(id=NODE_C, kind=EntityKind.NOTE, label="Other"))


def test_graph_filter_edge_matching() -> None:
    flt = GraphFilter().with_relation("linked_to").with_min_weight(0.6)
    assert flt.matches_edge(edge(weight=0.9))
    assert not flt.matches_edge(edge(weight=0.5))
    assert not flt.matches_edge(edge(relation="mentions", weight=0.9))
    assert flt.with_relation("linked_to").relations == ("linked_to",)
    assert GraphFilter().with_relation("LINKED_TO").relations == ("linked_to",)


def test_graph_filter_builders_are_immutable() -> None:
    original = GraphFilter()
    updated = (
        original.with_kind(EntityKind.NOTE)
        .with_kind(EntityKind.FINDING)
        .with_relation("mentions")
        .with_min_weight(0.25)
        .with_label("alpha")
    )
    assert original.is_empty()
    assert updated.kinds == (EntityKind.NOTE, EntityKind.FINDING)
    assert updated.relations == ("mentions",)
    assert updated.min_weight == 0.25
    assert updated.with_kind(EntityKind.NOTE) is updated
    assert updated.with_relation("mentions") is updated
    assert updated.with_kind(EntityKind.NOTE).without_kind(EntityKind.FINDING).kinds == (
        EntityKind.NOTE,
    )


def test_graph_filter_validation() -> None:
    with pytest.raises(ValueError, match="tuple"):
        GraphFilter(kinds=[EntityKind.NOTE])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tuple"):
        GraphFilter(relations=["linked_to"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid relation"):
        GraphFilter().with_relation("not valid")
    with pytest.raises(ValueError, match="min_weight must be"):
        GraphFilter().with_min_weight(1.5)
    with pytest.raises(ValueError, match="too long"):
        GraphFilter().with_label("x" * (MAX_FILTER_TEXT_LENGTH + 1))


def test_graph_filter_description_and_dict_round_trip() -> None:
    flt = (
        GraphFilter()
        .with_kind(EntityKind.NOTE)
        .with_relation("linked_to")
        .with_min_weight(0.5)
        .with_label("alpha")
    )
    assert "kinds=note" in flt.describe()
    assert "relations=linked_to" in flt.describe()
    assert "weight>=0.50" in flt.describe()
    assert "label~alpha" in flt.describe()
    assert GraphFilter.from_dict(flt.to_dict()) == flt
    assert GraphFilter().describe() == "all"
    assert GraphFilter.from_dict({}).is_empty()


def test_graph_metrics_properties() -> None:
    metrics = GraphMetrics(
        node_count=4,
        edge_count=2,
        degree={NODE_A: 2, NODE_B: 1, NODE_C: 0, NODE_D: 1},
    )
    assert metrics.isolated_count == 1
    assert metrics.max_degree == 2
    assert metrics.average_degree == 1.0
    assert metrics.density == 0.3333
    assert metrics.degree_for(NODE_A) == 2
    assert metrics.degree_for("missing") == 0
    assert GraphMetrics(node_count=1, edge_count=0).density == 0.0
    assert GraphMetrics(node_count=0, edge_count=0).average_degree == 0.0


def test_graph_metrics_validation_and_round_trip() -> None:
    with pytest.raises(ValueError, match="counts must not be negative"):
        GraphMetrics(node_count=-1, edge_count=0)
    with pytest.raises(ValueError, match="invalid degree key"):
        GraphMetrics(node_count=1, edge_count=0, degree={"bad key": 1})
    with pytest.raises(ValueError, match="degree values"):
        GraphMetrics(node_count=1, edge_count=0, degree={NODE_A: -1})
    with pytest.raises(ValueError, match="degree must be a mapping"):
        GraphMetrics.from_dict({"node_count": 1, "edge_count": 0, "degree": []})
    metrics = GraphMetrics(node_count=2, edge_count=1, degree={NODE_A: 1, NODE_B: 1})
    restored = GraphMetrics.from_dict(metrics.to_dict())
    assert restored.node_count == 2
    assert restored.degree == metrics.degree
    assert metrics.to_dict()["isolated_count"] == 0


def test_relation_stat_validation() -> None:
    stat = RelationStat(relation="linked_to", count=4, average_weight=0.625)
    assert RelationStat.from_dict(stat.to_dict()) == stat
    with pytest.raises(ValueError, match="invalid relation"):
        RelationStat(relation="BAD", count=1, average_weight=1.0)
    with pytest.raises(ValueError, match="count must not be negative"):
        RelationStat(relation="linked_to", count=-1, average_weight=1.0)


def test_graph_data_validation() -> None:
    with pytest.raises(ValueError, match="duplicate node ids"):
        GraphData(nodes=(node(), node()), edges=())
    with pytest.raises(ValueError, match="duplicate edge keys"):
        GraphData(nodes=(node(), node(NODE_B)), edges=(edge(), edge()))
    with pytest.raises(ValueError, match="unknown node"):
        GraphData(nodes=(node(),), edges=(edge(),))
    with pytest.raises(ValueError, match="must be tuples"):
        GraphData(nodes=[node()], edges=())  # type: ignore[arg-type]


def test_graph_data_helpers_and_round_trip() -> None:
    data = GraphData(nodes=(node(), node(NODE_B)), edges=(edge(),))
    assert data.node_ids == (NODE_A, NODE_B)
    assert not data.is_empty
    assert data.node_by_id(NODE_A) == node()
    assert data.node_by_id("missing") is None
    reduced = data.with_nodes((node(),))
    assert len(reduced.nodes) == 1
    assert reduced.edges == ()
    assert data.with_edges(()).edges == ()
    assert GraphData.from_dict(data.to_dict()) == data
    with pytest.raises(ValueError, match="must be lists"):
        GraphData.from_dict({"nodes": (), "edges": ()})


def test_graph_point_and_layout_result() -> None:
    first = GraphPoint(node_id=NODE_A, x=10.0, y=20.0)
    second = GraphPoint(node_id=NODE_B, x=13.0, y=24.0)
    assert first.distance_to(second) == 5.0
    assert first.to_dict() == {"node_id": NODE_A, "x": 10.0, "y": 20.0}
    assert GraphPoint.from_dict(first.to_dict()) == first
    with pytest.raises(ValueError, match="must be finite"):
        GraphPoint(node_id=NODE_A, x=float("nan"), y=1.0)
    result = LayoutResult(
        kind=LayoutKind.GRID,
        width=100.0,
        height=100.0,
        points=(first, second),
        seed=3,
        iterations=2,
    )
    assert result.by_id()[NODE_B] == second
    assert result.in_bounds()
    assert not result.in_bounds(padding=20.0)
    assert LayoutResult.from_dict(result.to_dict()) == result
    with pytest.raises(ValueError, match="duplicate node ids"):
        LayoutResult(kind=LayoutKind.GRID, width=100.0, height=100.0, points=(first, first))
    with pytest.raises(ValueError, match="dimensions must be positive"):
        LayoutResult(kind=LayoutKind.GRID, width=0.0, height=100.0, points=())


def test_filter_result_hidden_accounting() -> None:
    result = FilterResult(
        nodes=(node(),),
        edges=(),
        hidden_node_ids=(NODE_B,),
        hidden_edge_keys=(edge().key,),
        total_nodes=2,
        total_edges=1,
    )
    assert result.hidden_nodes == 1
    assert result.hidden_edges == 1
    assert not result.is_empty
    assert result.to_data() == GraphData(nodes=(node(),), edges=())
    restored = FilterResult.from_dict(result.to_dict())
    assert restored.hidden_nodes == 1
    assert restored.hidden_edge_keys == ((NODE_A, NODE_B, "linked_to"),)
    assert FilterResult(nodes=(), edges=()).is_empty


def test_graph_snapshot_validation_and_round_trip(sample_data: GraphData) -> None:
    snapshot = GraphSnapshot(
        name="alpha-view",
        data=sample_data,
        filter=GraphFilter().with_kind(EntityKind.NOTE),
        layout=LayoutKind.CIRCULAR,
        created_at="2026-01-01T00:00:00Z",
        tags=("reviewed", "ctf"),
    )
    assert GraphSnapshot.from_dict(snapshot.to_dict()) == snapshot
    assert snapshot.with_filter(GraphFilter()).filter.is_empty()
    with pytest.raises(ValueError, match="invalid snapshot name"):
        GraphSnapshot(
            name="Bad Name",
            data=sample_data,
            filter=GraphFilter(),
            layout=LayoutKind.FORCE,
            created_at="now",
        )
    with pytest.raises(ValueError, match="created_at must not be empty"):
        GraphSnapshot(
            name="valid",
            data=sample_data,
            filter=GraphFilter(),
            layout=LayoutKind.FORCE,
            created_at=" ",
        )
    with pytest.raises(ValueError, match="at most 8"):
        GraphSnapshot(
            name="valid",
            data=sample_data,
            filter=GraphFilter(),
            layout=LayoutKind.FORCE,
            created_at="now",
            tags=tuple(f"tag{i}" for i in range(9)),
        )
