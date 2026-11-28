from __future__ import annotations

import pytest

from redscribe.v4.contracts import EntityKind, EntityLink, EntityRef
from redscribe.v4.graph_v4.service import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    CircularLayout,
    FilterEngine,
    ForceLayout,
    GraphAnalyzer,
    GraphBuilder,
    GridLayout,
    LayoutEngine,
    compute_layout,
    relation_legend,
)
from redscribe.v4.graph_v4.types import (
    GraphData,
    GraphEdge,
    GraphFilter,
    LayoutKind,
)

from .conftest import (
    NODE_A,
    NODE_B,
    NODE_C,
    NODE_D,
    NODE_E,
    NODE_F,
    NODE_G,
    make_links,
    make_refs,
)


def test_builder_dedupes_nodes_and_links(sample_builder: GraphBuilder) -> None:
    assert sample_builder.link_count == 6
    assert sample_builder.duplicate_link_count == 1
    assert len(sample_builder.node_ids()) == 7
    assert sample_builder.has_node(NODE_A)
    assert not sample_builder.has_node("missing")


def test_builder_merges_duplicate_weight_and_label() -> None:
    ref = EntityRef(kind=EntityKind.NOTE, id=NODE_A, label="Alpha note")
    builder = GraphBuilder()
    first = builder.add_ref(ref)
    second = builder.add_ref(EntityRef(kind=EntityKind.NOTE, id=NODE_A), weight=0.6)
    assert second.weight == 1.0
    assert second.label == first.label
    builder.add_ref(ref, weight=0.2)
    merged = builder.build().node_by_id(NODE_A)
    assert merged is not None
    assert merged.weight == 1.0
    assert builder.add_refs(make_refs()) == 6


def test_builder_sorted_and_dangling_edges_removed() -> None:
    builder = GraphBuilder()
    builder.add_edge(GraphEdge(source=NODE_B, target=NODE_A, relation="linked_to"))
    builder.add_edge(GraphEdge(source=NODE_C, target=NODE_D, relation="supports", weight=0.4))
    data = builder.build()
    assert data.node_ids == tuple(sorted((NODE_B, NODE_A, NODE_C, NODE_D)))
    assert [edge.key for edge in data.edges] == [
        (NODE_B, NODE_A, "linked_to"),
        (NODE_C, NODE_D, "supports"),
    ]


def test_builder_edge_replacement_and_clear() -> None:
    builder = GraphBuilder()
    strong = GraphEdge(source=NODE_A, target=NODE_B, relation="linked_to", weight=0.9)
    weak = GraphEdge(source=NODE_A, target=NODE_B, relation="linked_to", weight=0.3)
    assert builder.add_edge(strong) == strong
    assert builder.add_edge(weak) == strong
    extra = GraphEdge(source=NODE_A, target=NODE_C, relation="mentions")
    assert builder.add_edge(extra) == extra
    assert len(builder.build().edges) == 2
    builder.clear()
    assert builder.node_ids() == ()
    assert builder.link_count == 0
    assert builder.duplicate_link_count == 0


def test_builder_from_links_and_add_links_count() -> None:
    links = make_links()
    builder = GraphBuilder.from_links(links)
    assert len(builder.build().edges) == 5
    duplicate = EntityLink(
        source=make_refs()[0], target=make_refs()[1], relation="linked_to", weight=0.1
    )
    assert builder.add_links((duplicate,)) == 1
    assert builder.duplicate_link_count == 2


def test_analyzer_degree_map_and_centrality(sample_data: GraphData) -> None:
    analyzer = GraphAnalyzer(sample_data)
    degrees = analyzer.degree_map()
    assert degrees[NODE_A] == 2
    assert degrees[NODE_C] == 3
    assert degrees[NODE_E] == 0
    assert analyzer.degree_map(min_weight=0.7)[NODE_C] == 1
    ranked = analyzer.centrality()
    assert ranked[0][0] == NODE_C
    assert ranked[0][1] == 0.5
    assert ranked[-1] == (NODE_E, 0.0)


def test_analyzer_components_and_isolated(sample_data: GraphData) -> None:
    analyzer = GraphAnalyzer(sample_data)
    assert analyzer.components() == (
        tuple(sorted((NODE_A, NODE_B, NODE_C, NODE_D))),
        (NODE_E,),
        tuple(sorted((NODE_F, NODE_G))),
    )
    assert analyzer.isolated_nodes() == (NODE_E,)
    assert NODE_C in analyzer.component_of(NODE_C)
    with pytest.raises(ValueError, match="unknown node"):
        analyzer.component_of("missing")


def test_analyzer_shortest_path(sample_data: GraphData) -> None:
    analyzer = GraphAnalyzer(sample_data)
    assert analyzer.shortest_path(NODE_A, NODE_D) == (NODE_A, NODE_C, NODE_D)
    assert analyzer.shortest_path(NODE_A, NODE_A) == (NODE_A,)
    assert analyzer.shortest_path(NODE_A, NODE_F) == ()
    with pytest.raises(ValueError, match="both endpoints"):
        analyzer.shortest_path(NODE_A, "missing")


def test_analyzer_neighbors_and_ego_network(sample_data: GraphData) -> None:
    analyzer = GraphAnalyzer(sample_data)
    assert analyzer.neighbors(NODE_A) == (NODE_B, NODE_C)
    assert analyzer.neighbors(NODE_A, min_weight=0.8) == (NODE_B,)
    with pytest.raises(ValueError, match="unknown node"):
        analyzer.neighbors("missing")
    one_hop = analyzer.ego_network(NODE_A, depth=1)
    assert len(one_hop.nodes) == 3
    assert len(one_hop.edges) == 3
    two_hops = analyzer.ego_network(NODE_A, depth=2)
    assert len(two_hops.nodes) == 4
    assert len(two_hops.edges) == 4
    with pytest.raises(ValueError, match="depth must not be negative"):
        analyzer.ego_network(NODE_A, depth=-1)


def test_analyzer_metrics_and_diameter(sample_data: GraphData) -> None:
    analyzer = GraphAnalyzer(sample_data)
    metrics = analyzer.metrics()
    assert metrics.node_count == 7
    assert metrics.edge_count == 5
    assert metrics.component_count == 3
    assert metrics.isolated_count == 1
    assert metrics.density == 0.2381
    assert analyzer.diameter() == 2
    assert GraphAnalyzer(GraphData()).metrics().node_count == 0


def test_analyzer_relation_stats(sample_data: GraphData) -> None:
    stats = GraphAnalyzer(sample_data).relation_stats()
    assert tuple(item.relation for item in stats) == (
        "derived_from",
        "linked_to",
        "mentions",
        "related_to",
        "supports",
    )
    assert stats[1].average_weight == 0.9
    assert relation_legend(()) == ()


def test_filter_engine_semantics(sample_data: GraphData) -> None:
    notes = FilterEngine(GraphFilter().with_kind(EntityKind.NOTE)).apply(sample_data)
    assert tuple(node.id for node in notes.nodes) == (NODE_A, NODE_E, NODE_G)
    assert notes.edges == ()
    assert notes.hidden_nodes == 4
    assert notes.hidden_edges == 5

    weighted = FilterEngine(GraphFilter().with_min_weight(0.7)).apply(sample_data)
    assert len(weighted.edges) == 3
    assert weighted.hidden_nodes == 0
    assert weighted.hidden_edges == 2

    mentions = FilterEngine(GraphFilter().with_relation("mentions")).apply(sample_data)
    assert tuple(edge.key for edge in mentions.edges) == ((NODE_A, NODE_C, "mentions"),)
    assert mentions.hidden_edges == 4

    empty = FilterEngine(GraphFilter()).apply(sample_data)
    assert empty.hidden_nodes == 0
    assert empty.hidden_edges == 0
    assert not empty.is_empty


def test_filter_engine_label_and_hidden_ids(sample_data: GraphData) -> None:
    engine = FilterEngine(GraphFilter().with_label("beta"))
    result = engine.apply(sample_data)
    assert tuple(node.id for node in result.nodes) == (NODE_B,)
    assert result.hidden_node_ids == tuple(sorted((NODE_A, NODE_C, NODE_D, NODE_E, NODE_F, NODE_G)))
    assert result.hidden_edge_keys
    assert engine.explain(sample_data) == {
        "visible_nodes": 1,
        "visible_edges": 0,
        "hidden_nodes": 6,
        "hidden_edges": 5,
    }


def test_filter_engine_combined_semantics(sample_data: GraphData) -> None:
    flt = (
        GraphFilter()
        .with_kind(EntityKind.NOTE)
        .with_kind(EntityKind.TARGET)
        .with_relation("linked_to")
        .with_min_weight(0.5)
    )
    result = FilterEngine(flt).apply(sample_data)
    assert tuple(node.id for node in result.nodes) == (
        NODE_A,
        NODE_B,
        NODE_E,
        NODE_F,
        NODE_G,
    )
    assert tuple(edge.key for edge in result.edges) == ((NODE_A, NODE_B, "linked_to"),)
    assert result.hidden_nodes == 2
    assert result.hidden_edges == 4


def test_force_layout_is_deterministic_and_bounded(sample_data: GraphData) -> None:
    first = ForceLayout(seed=11, iterations=6).compute(sample_data)
    second = ForceLayout(seed=11, iterations=6).compute(sample_data)
    assert first == second
    assert first.seed == 11
    assert first.iterations == 6
    assert first.kind is LayoutKind.FORCE
    assert len(first.points) == 7
    assert first.in_bounds(padding=55.0)
    assert ForceLayout(seed=12, iterations=6).compute(sample_data) != first


def test_force_layout_zero_iterations_and_empty(sample_data: GraphData) -> None:
    result = ForceLayout(iterations=0).compute(sample_data)
    assert result.iterations == 0
    assert result.in_bounds()
    assert ForceLayout().compute(GraphData()).points == ()


def test_force_layout_validation(sample_data: GraphData) -> None:
    with pytest.raises(ValueError, match="too small"):
        ForceLayout(width=100.0, height=100.0, padding=56.0)
    with pytest.raises(ValueError, match="must not be negative"):
        ForceLayout(iterations=-1)
    with pytest.raises(ValueError, match="force constants"):
        ForceLayout(repulsion=0.0)
    with pytest.raises(ValueError, match="damping"):
        ForceLayout(damping=1.5)


def test_circular_layout_positions(sample_data: GraphData) -> None:
    result = CircularLayout().compute(sample_data)
    assert result.kind is LayoutKind.CIRCULAR
    assert result.width == DEFAULT_WIDTH
    assert result.height == DEFAULT_HEIGHT
    assert result.in_bounds()
    assert tuple(point.node_id for point in result.points) == tuple(sorted(sample_data.node_ids))
    single = CircularLayout().compute(sample_data.with_nodes((sample_data.nodes[0],)))
    assert single.points[0].x == DEFAULT_WIDTH / 2
    assert single.points[0].y == DEFAULT_HEIGHT / 2


def test_grid_layout_positions(sample_data: GraphData) -> None:
    result = GridLayout().compute(sample_data)
    assert result.kind is LayoutKind.GRID
    assert len(result.points) == 7
    assert result.in_bounds()
    assert tuple(point.node_id for point in result.points) == tuple(sorted(sample_data.node_ids))
    assert GridLayout().compute(GraphData()).points == ()
    with pytest.raises(ValueError, match="gap must not be negative"):
        GridLayout(gap=-1.0)


def test_layout_engine_dispatch(sample_data: GraphData) -> None:
    engine = LayoutEngine(seed=4, iterations=2)
    assert engine.compute(sample_data).kind is LayoutKind.FORCE
    assert engine.compute(sample_data, LayoutKind.CIRCULAR).kind is LayoutKind.CIRCULAR
    assert engine.compute(sample_data, LayoutKind.GRID).kind is LayoutKind.GRID
    assert compute_layout(sample_data, LayoutKind.GRID, seed=5).kind is LayoutKind.GRID
    with pytest.raises(ValueError, match="unsupported layout"):
        engine.compute(sample_data, "radial")  # type: ignore[arg-type]


def test_builder_from_entity_refs_produces_layout_ready_data() -> None:
    data = GraphBuilder.from_links(make_links()).build()
    result = compute_layout(data, LayoutKind.FORCE, seed=3, iterations=3)
    assert result.by_id().keys() == set(data.node_ids)
    assert len(relation_legend(data.edges)) == 5
