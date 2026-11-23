from __future__ import annotations

import pytest

from redscribe.storage.db import Vault
from redscribe.v2.graph.model import GraphEdge, GraphModel, GraphNode
from redscribe.v2.graph.service import GraphFilters, GraphIntelligenceService
from redscribe.v2.graph.snapshot import SnapshotStore, diff_snapshots
from tests.v2_graph.conftest import seed_vault


def service(vault: Vault) -> GraphIntelligenceService:
    return GraphIntelligenceService(vault)


def test_graph_filters_from_dict_validates_inputs() -> None:
    filters = GraphFilters.from_dict(
        {
            "kinds": ["note", "tag"],
            "tags": [" #Web ", "RECON"],
            "statuses": ["active"],
            "query": "  Alpha ",
            "max_nodes": 3,
        }
    )
    assert filters.kinds == ("note", "tag")
    assert filters.tags == ("web", "recon")
    assert filters.statuses == ("active",)
    assert filters.query == "alpha"
    assert filters.max_nodes == 3
    assert filters.as_dict() == {
        "kinds": ["note", "tag"],
        "tags": ["web", "recon"],
        "statuses": ["active"],
        "query": "alpha",
        "max_nodes": 3,
    }


def test_graph_filters_from_dict_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        GraphFilters.from_dict({"kinds": ["artifact"]})
    with pytest.raises(ValueError):
        GraphFilters.from_dict({"kinds": "note, tag"})
    with pytest.raises(ValueError):
        GraphFilters.from_dict({"max_nodes": -1})
    with pytest.raises(ValueError):
        GraphFilters.from_dict({"query": 7})
    with pytest.raises(ValueError):
        GraphFilters.from_dict({"tags": [1]})


def test_graph_filters_match_semantics() -> None:
    filters = GraphFilters.from_dict({"tags": ["web"], "statuses": ["active"], "query": "alpha"})
    assert filters.matches("Alpha", ("WEB",), "active", "note")
    assert not filters.matches("Beta", ("web",), "active", "note")
    assert not filters.matches("Alpha", ("web",), "done", "note")
    assert not filters.matches("Alpha", ("recon",), "active", "note")
    assert not filters.matches("Alpha", ("web",), "active", "tag")
    assert GraphFilters().matches("Anything", (), "todo", "note")


def test_service_lazily_builds_and_refreshes_store(vault: Vault) -> None:
    seed_vault(vault)
    instance = service(vault)
    assert instance._store is None
    first = instance.store()
    assert instance.store() is first
    instance.store(refresh=True)
    assert instance.store() is not first


def test_service_overview_and_metrics(vault: Vault) -> None:
    seed_vault(vault)
    overview = service(vault).overview()
    assert overview["stats"]["notes"] == 4
    assert overview["stats"]["edges"] >= 5
    assert overview["metrics"]["nodes"] >= 8
    assert "web" in overview["tags"]
    assert overview["snapshot_count"] == 0


def test_service_nodes_edges_and_filters(vault: Vault) -> None:
    seed_vault(vault)
    instance = service(vault)
    all_nodes = instance.nodes()
    assert len(all_nodes) >= 8
    filtered = instance.nodes(filters=GraphFilters.from_dict({"tags": ["web"]}))
    titles = {item["label"] for item in filtered}
    assert {"Alpha", "Beta"} <= titles
    assert "Island" not in titles
    limited = instance.nodes(filters=GraphFilters.from_dict({"max_nodes": 2}))
    assert len(limited) == 2
    kinds = instance.edges(kinds=("link",))
    assert all(item["kind"] == "link" for item in kinds)


def test_service_neighbors_depth_and_validation(vault: Vault) -> None:
    _, alpha_id, beta_id = seed_vault(vault)
    instance = service(vault)
    direct = instance.neighbors(alpha_id, depth=1)
    assert direct["node_id"] == alpha_id
    assert beta_id in {item["id"] for item in direct["nodes"]}
    deeper = instance.neighbors(alpha_id, depth=2)
    assert len(deeper["nodes"]) >= len(direct["nodes"])
    assert deeper["edges"]
    with pytest.raises(ValueError):
        instance.neighbors(alpha_id, depth=0)
    with pytest.raises(ValueError):
        instance.neighbors(9999)


def test_service_centrality_and_clustering(vault: Vault) -> None:
    seed_vault(vault)
    instance = service(vault)
    for measure in ("degree", "closeness", "betweenness", "eigenvector"):
        scores = instance.centrality(measure, limit=3)
        assert len(scores) == 3
        assert all(item["measure"] == measure for item in scores)
    with pytest.raises(ValueError):
        instance.centrality("pagerank")
    with pytest.raises(ValueError):
        instance.centrality("degree", limit=0)
    clustering = instance.clustering()
    assert "average" in clustering
    assert isinstance(clustering["scores"], list)


def test_service_components_communities_cycles(vault: Vault) -> None:
    seed_vault(vault)
    instance = service(vault)
    assert instance.components()
    assert instance.components(min_size=100) == []
    assert instance.communities()
    assert all("node_ids" in item for item in instance.communities())
    assert isinstance(instance.cycles(limit=5), list)


def test_service_paths_and_label_resolution(vault: Vault) -> None:
    _, alpha_id, beta_id = seed_vault(vault)
    instance = service(vault)
    assert instance.resolve_label("alpha") == alpha_id
    assert instance.resolve_label("[[Alpha]]") == alpha_id
    assert instance.resolve_label("Unknown") is None
    path = instance.path(alpha_id, beta_id)
    assert path is not None
    assert path["node_ids"][0] == alpha_id
    assert path["node_ids"][-1] == beta_id
    assert instance.path(alpha_id, alpha_id)["hops"] == 0
    assert instance.path(alpha_id, 9999) is None


def test_service_links_and_dangling(vault: Vault) -> None:
    _, alpha_id, beta_id = seed_vault(vault)
    links = service(vault).links()
    assert any(item.node_id == alpha_id for item in links.backlinks(beta_id))
    assert any(item.node_id == beta_id for item in links.outlinks(alpha_id))
    detail = links.detail(alpha_id)
    assert detail.node_id == alpha_id
    assert detail.out_degree >= 1
    assert detail.as_dict()["in_degree"] == detail.in_degree
    assert links.dangling()
    assert links.content(alpha_id)
    assert links.content(9999) == ""


def test_service_recommendations(vault: Vault) -> None:
    _, alpha_id, _ = seed_vault(vault)
    instance = service(vault)
    recommendations = instance.recommendations()
    dashboard = recommendations.dashboard()
    assert set(dashboard) >= {"missing_links", "popular", "notes", "unresolved"}
    assert dashboard["notes"] == 4
    assert dashboard["unresolved"] >= 1
    assert isinstance(recommendations.related(alpha_id, limit=3), tuple)
    assert isinstance(recommendations.by_tag("web", limit=2), tuple)
    assert isinstance(recommendations.popular(limit=2), tuple)
    with pytest.raises(ValueError):
        recommendations.related(alpha_id, limit=0)


def test_service_layout_and_insights(vault: Vault) -> None:
    seed_vault(vault)
    instance = service(vault)
    layout = instance.layout()
    assert set(layout) == {"nodes", "edges"}
    assert all("id" in item for item in layout["nodes"])
    assert all("source" in item for item in layout["edges"])
    filtered = instance.layout(filters=GraphFilters.from_dict({"tags": ["web"]}))
    assert len(filtered["nodes"]) < len(layout["nodes"])
    insights = instance.insights(limit=3)
    assert set(insights) >= {
        "overview",
        "centrality",
        "components",
        "communities",
        "clusters",
        "recommendations",
        "dangling",
    }
    assert len(insights["centrality"]) == 3


def test_snapshot_store_capture_list_get_restore(vault: Vault) -> None:
    seed_vault(vault)
    instance = service(vault)
    first = instance.capture(label="first")
    assert first.meta.label == "first"
    assert first.meta.node_count >= 8
    assert first.meta.edge_count >= 5
    payload = instance.snapshots()
    assert payload["count"] == 1
    assert payload["latest_id"] == first.meta.id
    assert payload["snapshots"][0]["label"] == "first"
    stored = instance.snapshot(first.meta.id)
    assert stored.meta.id == first.meta.id
    full = stored.as_dict(include_records=True)
    assert full["nodes"]
    assert full["edges"]
    restored = instance.diff(first.meta.id, first.meta.id)
    assert restored["changed"] is False


def test_snapshot_diff_detects_node_and_edge_changes(vault: Vault) -> None:
    instance = service(vault)
    before = instance.capture(label="before")
    vault.create_node("Later", content="[[Missing]]")
    after = instance.capture(label="after")
    diff = instance.diff(before.meta.id, after.meta.id)
    assert diff["changed"] is True
    assert diff["added_nodes"]
    assert diff["added_edges"]
    assert not diff["removed_nodes"]


def test_snapshot_delete_and_errors(vault: Vault) -> None:
    instance = service(vault)
    snapshot = instance.capture()
    assert instance.delete_snapshot(snapshot.meta.id) == snapshot.meta.id
    assert instance.snapshots()["count"] == 0
    with pytest.raises(ValueError):
        instance.snapshot(snapshot.meta.id)
    with pytest.raises(ValueError):
        instance.delete_snapshot(snapshot.meta.id)


def test_snapshot_store_capacity_and_pruning() -> None:
    model = GraphModel.from_records([GraphNode(id=1, label="One")])
    store = SnapshotStore(capacity=2)
    first = store.capture(model, label="one")
    second = store.capture(model, label="two")
    third = store.capture(model, label="three")
    assert [item.meta.id for item in store.list()] == [third.meta.id, second.meta.id]
    assert store.get(first.meta.id) is None
    assert store.latest() is third
    assert store.prune() == 0
    with pytest.raises(ValueError):
        SnapshotStore(capacity=0)


def test_diff_snapshots_identifies_removals() -> None:
    store = SnapshotStore()
    left = store.capture(
        GraphModel.from_records([GraphNode(id=1), GraphNode(id=2)], [GraphEdge(1, 2)])
    )
    right = store.capture(GraphModel.from_records([GraphNode(id=1)]))
    diff = diff_snapshots(left, right)
    assert diff.removed_nodes == (2,)
    assert diff.removed_edges == ((1, 2, "link"),)
    assert diff.added_nodes == ()
    assert diff.as_dict()["changed"] is True


def test_snapshot_digest_changes_with_content() -> None:
    store = SnapshotStore()
    first = store.capture(GraphModel.from_records([GraphNode(id=1, label="One")]))
    second = store.capture(GraphModel.from_records([GraphNode(id=1, label="Two")]))
    assert first.meta.digest != second.meta.digest
    assert first.meta.id != second.meta.id
