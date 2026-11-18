from __future__ import annotations

import pytest
from tests.v2_graph.conftest import seed_vault

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import V2Error
from redscribe.ui.web.v2.namespaces.graph import get_service, register
from redscribe.ui.web.v2.routes import ApiV2

ROUTES = (
    "graph.overview",
    "graph.nodes",
    "graph.edges",
    "graph.neighbors",
    "graph.backlinks",
    "graph.outlinks",
    "graph.dangling",
    "graph.path",
    "graph.components",
    "graph.centrality",
    "graph.clustering",
    "graph.communities",
    "graph.cycles",
    "graph.recommend",
    "graph.related",
    "graph.tags",
    "graph.resolve",
    "graph.layout",
    "graph.insights",
    "graph.snapshot.create",
    "graph.snapshot.list",
    "graph.snapshot.get",
    "graph.snapshot.restore",
    "graph.snapshot.diff",
    "graph.snapshot.delete",
)


def api(vault: Vault) -> ApiV2:
    instance = ApiV2(vault)
    register(instance)
    return instance


def test_register_is_idempotent_and_adds_every_route(vault: Vault) -> None:
    instance = api(vault)
    before = set(instance.routes)
    register(instance)
    assert set(instance.routes) == before
    assert set(ROUTES) <= before
    for name in ROUTES:
        route = instance.route(name)
        assert route.name == name
        assert route.as_schema()["name"] == name
        assert isinstance(route.description, str)
        assert route.entity_type


def test_service_is_cached_per_api_instance(vault: Vault) -> None:
    instance = api(vault)
    assert get_service(instance) is get_service(instance)
    other = api(vault)
    assert get_service(other) is not get_service(instance)


def test_overview_nodes_edges_routes(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    overview = instance.invoke("graph.overview", {}).data
    assert overview["stats"]["notes"] == 4
    assert overview["metrics"]["nodes"] >= 8
    assert instance.invoke("graph.overview", {"refresh": True}).etag
    nodes = instance.invoke("graph.nodes", {"limit": 2}).data
    assert len(nodes["items"]) == 2
    assert nodes["page"]["limit"] == 2
    filtered = instance.invoke("graph.nodes", {"tags": ["web"], "limit": 20}).data
    assert all("web" in [tag.casefold() for tag in item["tags"]] for item in filtered["items"])
    edges = instance.invoke("graph.edges", {"kinds": ["link"], "limit": 20}).data
    assert all(item["kind"] == "link" for item in edges["items"])
    layout = instance.invoke("graph.layout", {"tags": ["web"]}).data
    assert layout["nodes"]
    assert layout["edges"]


def test_neighbor_and_link_routes(vault: Vault) -> None:
    _, alpha_id, beta_id = seed_vault(vault)
    instance = api(vault)
    neighbors = instance.invoke("graph.neighbors", {"id": alpha_id, "depth": 1}).data
    assert neighbors["node_id"] == alpha_id
    assert beta_id in {item["id"] for item in neighbors["nodes"]}
    backlinks = instance.invoke("graph.backlinks", {"id": beta_id}).data
    assert any(item["node_id"] == alpha_id for item in backlinks["backlinks"])
    outlinks = instance.invoke("graph.outlinks", {"id": alpha_id}).data
    assert any(item["node_id"] == beta_id for item in outlinks["outlinks"])
    assert outlinks["out_degree"] >= 1
    dangling = instance.invoke("graph.dangling", {"limit": 10}).data
    assert dangling["count"] >= 1
    assert dangling["items"][0]["target"]


def test_path_route_accepts_ids_and_labels(vault: Vault) -> None:
    _, alpha_id, beta_id = seed_vault(vault)
    instance = api(vault)
    by_id = instance.invoke("graph.path", {"source": alpha_id, "target": beta_id}).data
    by_label = instance.invoke("graph.path", {"from": "Alpha", "to": "Beta"}).data
    assert by_id["node_ids"] == by_label["node_ids"]
    assert by_id["hops"] >= 1
    weighted = instance.invoke(
        "graph.path", {"source": alpha_id, "target": beta_id, "weighted": True, "max_hops": 3}
    ).data
    assert weighted["hops"] == by_id["hops"]


def test_analysis_routes(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    assert instance.invoke("graph.components", {"min_size": 2}).data["items"]
    for measure in ("degree", "closeness", "betweenness", "eigenvector"):
        payload = instance.invoke("graph.centrality", {"measure": measure, "limit": 2}).data
        assert payload["measure"] == measure
        assert len(payload["items"]) == 2
    assert instance.invoke("graph.clustering", {}).data["scores"]
    assert instance.invoke("graph.communities", {}).data["count"] >= 1
    assert isinstance(instance.invoke("graph.cycles", {"limit": 3}).data["items"], list)
    dashboard = instance.invoke("graph.recommend", {"limit": 3}).data
    assert set(dashboard) >= {"missing_links", "popular", "notes", "unresolved"}
    insights = instance.invoke("graph.insights", {"limit": 2}).data
    assert len(insights["centrality"]) == 2


def test_recommendation_routes(vault: Vault) -> None:
    _, alpha_id, _ = seed_vault(vault)
    instance = api(vault)
    related = instance.invoke("graph.related", {"id": alpha_id, "limit": 3, "min_score": 0.2}).data
    assert related["node_id"] == alpha_id
    assert all(item["score"] >= 0.2 for item in related["items"])
    tags = instance.invoke("graph.tags", {"tag": "#web", "limit": 3}).data
    assert tags["tag"] == "#web"
    assert all(item["kind"] == "tag" for item in tags["items"])


def test_resolve_route(vault: Vault) -> None:
    _, alpha_id, _ = seed_vault(vault)
    instance = api(vault)
    resolved = instance.invoke("graph.resolve", {"label": "[[Alpha]]"}).data
    assert resolved["id"] == alpha_id
    assert resolved["key"] == "alpha"
    with pytest.raises(V2Error):
        instance.invoke("graph.resolve", {"label": "Does not exist"})


def test_snapshot_routes(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    created = instance.invoke("graph.snapshot.create", {"label": "checkpoint", "source": "test"})
    assert created.status == 201
    snapshot_id = created.data["meta"]["id"]
    assert created.data["nodes"]
    listed = instance.invoke("graph.snapshot.list", {}).data
    assert listed["count"] == 1
    assert listed["latest_id"] == snapshot_id
    fetched = instance.invoke("graph.snapshot.get", {"id": snapshot_id}).data
    assert fetched["meta"]["label"] == "checkpoint"
    restored = instance.invoke("graph.snapshot.restore", {"id": snapshot_id}).data
    assert restored["nodes"]
    assert restored["edges"]
    diff = instance.invoke("graph.snapshot.diff", {"left": snapshot_id, "right": snapshot_id}).data
    assert diff["changed"] is False
    deleted = instance.invoke("graph.snapshot.delete", {"id": snapshot_id}).data
    assert deleted["deleted"] == snapshot_id
    assert instance.invoke("graph.snapshot.list", {}).data["count"] == 0


def test_route_validation_errors(vault: Vault) -> None:
    seed_vault(vault)
    instance = api(vault)
    with pytest.raises(V2Error):
        instance.invoke("graph.nodes", {"limit": 0})
    with pytest.raises(V2Error):
        instance.invoke("graph.nodes", {"kinds": ["artifact"]})
    with pytest.raises(V2Error):
        instance.invoke("graph.neighbors", {})
    with pytest.raises(V2Error):
        instance.invoke("graph.neighbors", {"id": 1, "depth": 9})
    with pytest.raises(V2Error):
        instance.invoke("graph.path", {"source": 1, "target": 2, "weighted": "yes"})
    with pytest.raises(V2Error):
        instance.invoke("graph.path", {"source": 1, "target": 9999})
    with pytest.raises(V2Error):
        instance.invoke("graph.centrality", {"measure": "pagerank"})
    with pytest.raises(V2Error):
        instance.invoke("graph.related", {"id": 1, "min_score": 2})
    with pytest.raises(V2Error):
        instance.invoke("graph.tags", {"tag": "   "})
    with pytest.raises(V2Error):
        instance.invoke("graph.snapshot.get", {"id": "missing"})


def test_route_schemas_declare_required_and_optional_fields(vault: Vault) -> None:
    instance = api(vault)
    schema = instance.route("graph.path").as_schema()
    assert "source" in schema.get("required", schema.get("required_fields", []))
    assert "target" in schema.get("required", schema.get("required_fields", []))
    snapshot_schema = instance.route("graph.snapshot.create").as_schema()
    assert snapshot_schema.get("mutating") is True or snapshot_schema.get("idempotency") is not None
