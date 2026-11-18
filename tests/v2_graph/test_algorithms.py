from __future__ import annotations

import pytest

from redscribe.v2.graph.algorithms import (
    adjacency,
    average_clustering,
    betweenness_centrality,
    closeness_centrality,
    clustering_coefficients,
    connected_components,
    degree_centrality,
    detect_communities,
    eigenvector_centrality,
    find_cycles,
    graph_metrics,
    shortest_path,
)
from redscribe.v2.graph.model import GraphEdge, GraphModel, GraphNode


def node(node_id: int, label: str | None = None) -> GraphNode:
    return GraphNode(id=node_id, label=label or f"Node {node_id}")


def link(source: int, target: int, weight: float = 1.0, kind: str = "link") -> GraphEdge:
    return GraphEdge(source=source, target=target, weight=weight, kind=kind)


def chain() -> GraphModel:
    return GraphModel.from_records(
        [node(1), node(2), node(3), node(4), node(9)],
        [link(1, 2), link(2, 3), link(3, 4)],
    )


def triangle() -> GraphModel:
    return GraphModel.from_records(
        [node(1, "Alpha"), node(2, "Beta"), node(3, "Gamma")],
        [link(1, 2, 2.0), link(2, 3), link(3, 1)],
    )


def test_adjacency_is_undirected_and_weighted() -> None:
    links = adjacency(triangle())
    assert links[1][2] == 2.0
    assert links[2][1] == 2.0
    assert set(links[1]) == {2, 3}
    directed = adjacency(triangle(), directed=True)
    assert directed[2] == {3: 1.0}
    assert 1 not in directed[2]
    resolved = adjacency(
        GraphModel.from_records([node(1), node(2)], [GraphEdge(1, 2, resolved=False)]),
        resolved_only=True,
    )
    assert resolved[1] == {}
    filtered = adjacency(triangle(), kinds=("tag",))
    assert all(not neighbors for neighbors in filtered.values())


def test_connected_components_orders_by_size_then_ids() -> None:
    groups = connected_components(chain())
    assert [group.node_ids for group in groups] == [(1, 2, 3, 4), (9,)]
    assert groups[0].size == 4
    assert groups[0].labels == ("Node 1", "Node 2", "Node 3", "Node 4")
    assert groups[0].as_dict()["index"] == 1
    assert connected_components(chain(), min_size=2) == groups[:1]
    assert connected_components(GraphModel(), min_size=1) == ()
    with pytest.raises(ValueError):
        connected_components(chain(), min_size=0)


def test_degree_centrality_ranks_hubs_first() -> None:
    scores = degree_centrality(chain())
    assert [item.node_id for item in scores[:2]] == [2, 3]
    assert scores[0].measure == "degree"
    assert scores[0].rank == 1
    assert scores[0].score == scores[1].score == 0.5
    assert scores[2].score < scores[0].score
    assert all(0 <= item.score <= 1 for item in scores)
    assert scores[-1].node_id == 9
    assert scores[0].as_dict()["rank"] == 1


def test_closeness_centrality_prefers_central_vertices() -> None:
    scores = closeness_centrality(chain())
    assert scores[0].node_id in (2, 3)
    assert all(0 <= item.score <= 1 for item in scores)
    assert all(item.measure == "closeness" for item in scores)


def test_betweenness_centrality_prefers_bridges() -> None:
    scores = betweenness_centrality(chain())
    assert scores[0].node_id in (2, 3)
    assert all(item.measure == "betweenness" for item in scores)
    assert scores[-1].score == 0


def test_eigenvector_centrality_is_stable() -> None:
    scores = eigenvector_centrality(triangle())
    assert len(scores) == 3
    assert all(item.measure == "eigenvector" for item in scores)
    assert all(item.score >= 0 for item in scores)
    assert [item.node_id for item in scores] == sorted(
        [item.node_id for item in scores],
        key=lambda value: -next(s.score for s in scores if s.node_id == value),
    )


def test_clustering_coefficients_detect_triangles() -> None:
    scores = clustering_coefficients(triangle())
    assert len(scores) == 3
    assert all(item.coefficient == 1 for item in scores)
    assert all(item.triangles == 1 for item in scores)
    assert all(item.degree == 2 for item in scores)
    assert average_clustering(triangle()) == 1
    assert average_clustering(GraphModel()) == 0
    assert all(item.as_dict()["coefficient"] == 1 for item in scores)


def test_clustering_coefficients_for_chain_are_zero() -> None:
    scores = clustering_coefficients(chain())
    assert all(item.coefficient == 0 for item in scores)
    assert average_clustering(chain()) == 0


def test_shortest_path_uses_fewest_hops_by_default() -> None:
    result = shortest_path(chain(), 1, 4)
    assert result is not None
    assert result.node_ids == (1, 2, 3, 4)
    assert result.hops == 3
    assert result.cost == 3
    assert result.labels == ("Node 1", "Node 2", "Node 3", "Node 4")
    assert len(result.edge_keys) == 3
    payload = result.as_dict()
    assert payload["edges"][0] == [1, 2, "link"]


def test_shortest_path_can_use_weights() -> None:
    model = GraphModel.from_records(
        [node(1), node(2), node(3)],
        [link(1, 2, weight=10), link(1, 3, weight=1), link(3, 2, weight=1)],
    )
    unweighted = shortest_path(model, 1, 2)
    weighted = shortest_path(model, 1, 2, weighted=True)
    assert unweighted is not None
    assert weighted is not None
    assert unweighted.node_ids == (1, 2)
    assert weighted.node_ids == (1, 3, 2)
    assert weighted.cost == 2


def test_shortest_path_respects_direction_and_hop_limit() -> None:
    model = GraphModel.from_records([node(1), node(2)], [link(1, 2)])
    assert shortest_path(model, 1, 2, directed=True) is not None
    assert shortest_path(model, 2, 1, directed=True) is None
    assert shortest_path(chain(), 1, 4, max_hops=2) is None
    assert shortest_path(chain(), 1, 1).hops == 0
    with pytest.raises(ValueError):
        shortest_path(chain(), 1, 99)
    with pytest.raises(ValueError):
        shortest_path(chain(), 1, 2, max_hops=-1)


def test_find_cycles_detects_triangles() -> None:
    cycles = find_cycles(triangle())
    assert len(cycles) == 1
    assert cycles[0].length == 3
    assert cycles[0].labels == ("Alpha", "Beta", "Gamma")
    assert cycles[0].as_dict()["node_ids"] == [1, 2, 3]
    assert find_cycles(chain()) == ()
    with pytest.raises(ValueError):
        find_cycles(triangle(), limit=0)


def test_detect_communities_keeps_disconnected_groups_separate() -> None:
    communities = detect_communities(chain())
    assert len(communities) == 2
    assert communities[0].node_ids == (1, 2, 3, 4)
    assert communities[1].node_ids == (9,)
    assert communities[0].as_dict()["index"] == 1
    assert all(item.iterations >= 1 for item in communities)
    assert [item.node_ids for item in detect_communities(chain(), seed=3)] == [
        item.node_ids for item in communities
    ]
    with pytest.raises(ValueError):
        detect_communities(chain(), max_iterations=0)


def test_graph_metrics_summarizes_structure() -> None:
    metrics = graph_metrics(triangle())
    assert metrics["nodes"] == 3
    assert metrics["edges"] == 3
    assert metrics["density"] == 1
    assert metrics["components"] == 1
    assert metrics["average_degree"] == 2
    assert metrics["average_clustering"] == 1
    assert metrics["cycles"] >= 1
    empty = graph_metrics(GraphModel())
    assert empty["nodes"] == 0
    assert empty["density"] == 0


def test_graph_metrics_account_for_unresolved_edges() -> None:
    model = GraphModel.from_records(
        [node(1), node(2), node(3)],
        [link(1, 2), GraphEdge(2, 3, resolved=False)],
    )
    metrics = graph_metrics(model)
    assert metrics["nodes"] == 3
    assert metrics["edges"] == 2
    assert metrics["density"] > 0


def test_centrality_on_empty_model_is_empty() -> None:
    model = GraphModel()
    assert degree_centrality(model) == ()
    assert closeness_centrality(model) == ()
    assert betweenness_centrality(model) == ()
    assert eigenvector_centrality(model) == ()


def test_centrality_handles_single_node() -> None:
    model = GraphModel.from_records([node(1)], [])
    scores = degree_centrality(model)
    assert len(scores) == 1
    assert scores[0].score == 0
    assert closeness_centrality(model)[0].score == 0
    assert betweenness_centrality(model)[0].score == 0


def test_shortest_path_edge_keys_are_canonical() -> None:
    model = GraphModel.from_records(
        [node(1), node(2)],
        [link(2, 1, kind="mention"), link(1, 2, kind="link")],
    )
    result = shortest_path(model, 1, 2)
    assert result is not None
    assert result.edge_keys == ((1, 2, "link"),)


def test_find_cycles_limit_is_respected() -> None:
    model = GraphModel.from_records(
        [node(1), node(2), node(3), node(4), node(5), node(6)],
        [
            link(1, 2),
            link(2, 3),
            link(3, 1),
            link(4, 5),
            link(5, 6),
            link(6, 4),
        ],
    )
    assert len(find_cycles(model, limit=1)) == 1
    assert len(find_cycles(model, limit=5)) == 2


def test_community_score_reflects_density() -> None:
    sparse = detect_communities(chain())[0]
    dense = detect_communities(triangle())[0]
    assert dense.score > sparse.score
