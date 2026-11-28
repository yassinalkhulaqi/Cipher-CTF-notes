from __future__ import annotations

import json
from typing import Any

import pytest

from redscribe.v4 import discover_modules
from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import ApiError, Capability, CapabilitySet, EntityKind
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.graph_v4 import register
from redscribe.v4.graph_v4.api import GRAPH_ROUTES, GraphApi, GraphRequest
from redscribe.v4.graph_v4.service import GraphBuilder
from redscribe.v4.graph_v4.storage import GraphStore
from redscribe.v4.graph_v4.types import GraphFilter, LayoutKind

from .conftest import NODE_A, NODE_C, NODE_D, NODE_E, NODE_F


@pytest.fixture
def api(
    sample_builder: GraphBuilder,
    fixed_clock: Any,
    fixed_id: Any,
) -> GraphApi:
    store = GraphStore(clock=fixed_clock)
    store.save(
        "alpha-view",
        sample_builder.build(),
        GraphFilter().with_kind(EntityKind.NOTE),
        LayoutKind.CIRCULAR,
        ("reviewed",),
    )
    store.save_filter("notes", GraphFilter().with_kind(EntityKind.NOTE))
    return GraphApi(
        builder=sample_builder,
        store=store,
        bus=EventBus(),
        capabilities=CapabilitySet.full(),
        gate=FeatureGate(CapabilitySet.full()),
        id_factory=fixed_id,
        clock=fixed_clock,
    )


def data_of(envelope: dict[str, Any]) -> Any:
    assert "data" in envelope
    assert "meta" in envelope
    return envelope["data"]


def error_of(envelope: dict[str, Any]) -> dict[str, Any]:
    assert "error" in envelope
    return envelope["error"]


def test_graph_routes_metadata() -> None:
    prefixes = tuple(prefix for prefix, _ in GRAPH_ROUTES)
    names = tuple(name for _, name in GRAPH_ROUTES)
    assert prefixes[0] == "graph"
    assert "graph/nodes" in prefixes
    assert "graph/export" in prefixes
    assert len(names) == len(set(names))
    assert len(prefixes) == 10


def test_request_defaults() -> None:
    request = GraphRequest()
    assert request.page() == 1
    assert request.page_size() == 50
    assert request.min_weight() == 0.0
    assert request.label_contains() == ""
    assert request.kinds() == ()
    assert request.relations() == ()
    assert request.layout() is LayoutKind.FORCE
    assert request.seed() == 0
    assert request.width() == 960.0
    assert request.height() == 600.0
    assert request.iterations() == 24


def test_request_explicit_values() -> None:
    request = GraphRequest(
        {
            "page": "2",
            "page_size": "10",
            "min_weight": "0.4",
            "label_contains": " beta ",
            "kinds": "note, target,note",
            "relations": "linked_to,MENTIONS,linked_to",
            "layout": "grid",
            "seed": "7",
            "width": "800",
            "height": "500",
            "iterations": "5",
            "request_id": "req-42",
        }
    )
    assert request.page() == 2
    assert request.page_size() == 10
    assert request.min_weight() == 0.4
    assert request.label_contains() == "beta"
    assert request.kinds() == (EntityKind.NOTE, EntityKind.TARGET)
    assert request.relations() == ("linked_to", "mentions")
    assert request.layout() is LayoutKind.GRID
    assert (request.seed(), request.width(), request.height(), request.iterations()) == (
        7,
        800.0,
        500.0,
        5,
    )
    assert request.request_id(lambda: "fallback") == "req-42"


def test_request_rejects_invalid_integers() -> None:
    with pytest.raises(ApiError):
        GraphRequest({"page": "0"}).page()
    with pytest.raises(ApiError):
        GraphRequest({"page_size": "999"}).page_size()
    with pytest.raises(ApiError):
        GraphRequest({"seed": "bad"}).seed()
    with pytest.raises(ApiError):
        GraphRequest({"iterations": "-1"}).iterations()


def test_request_rejects_invalid_floats() -> None:
    with pytest.raises(ApiError):
        GraphRequest({"min_weight": "1.5"}).min_weight()
    with pytest.raises(ApiError):
        GraphRequest({"min_weight": "not-a-number"}).min_weight()
    with pytest.raises(ApiError):
        GraphRequest({"width": "50"}).width()
    with pytest.raises(ApiError):
        GraphRequest({"height": "nan"}).height()


def test_request_rejects_invalid_kinds_and_relations() -> None:
    with pytest.raises(ApiError):
        GraphRequest({"kinds": "bogus"}).kinds()
    with pytest.raises(ApiError):
        GraphRequest({"relations": ",".join(f"rel{i}" for i in range(40))}).relations()
    with pytest.raises(ApiError):
        GraphRequest({"relations": "bad relation"}).to_filter()


def test_request_rejects_invalid_layout() -> None:
    with pytest.raises(ApiError):
        GraphRequest({"layout": "radial"}).layout()


def test_request_requires_parameters() -> None:
    for method in ("node_id", "source", "target", "snapshot_name"):
        with pytest.raises(ApiError):
            getattr(GraphRequest({}), method)()


def test_request_to_filter_combines_all_fields() -> None:
    flt = GraphRequest(
        {
            "kinds": "note,finding",
            "relations": "linked_to",
            "min_weight": "0.3",
            "label_contains": "alpha",
        }
    ).to_filter()
    assert flt.kinds == (EntityKind.NOTE, EntityKind.FINDING)
    assert flt.relations == ("linked_to",)
    assert flt.min_weight == 0.3
    assert flt.label_contains == "alpha"


def test_read_capability_is_required(api: GraphApi) -> None:
    api.capabilities = CapabilitySet(frozenset())
    envelope = api.dispatch("graph")
    error = error_of(envelope)
    assert error["code"] == "forbidden"


def test_export_capability_is_required(api: GraphApi) -> None:
    api.capabilities = CapabilitySet(frozenset({Capability.READ}))
    envelope = api.dispatch("graph/export")
    assert error_of(envelope)["code"] == "forbidden"


def test_feature_gate_can_block_workbench(api: GraphApi) -> None:
    api.gate = FeatureGate(CapabilitySet.full(), version="v3")
    assert not api.gate.is_enabled(FeatureFlag.GRAPH_WORKBENCH)
    assert error_of(api.dispatch("graph"))["code"] == "forbidden"


def test_filtered_event_is_published(api: GraphApi) -> None:
    api.dispatch("graph", {"kinds": "note"})
    events = api.bus.published
    assert len(events) == 1
    assert events[0].kind is EventKind.GRAPH_FILTERED
    assert events[0].payload["source"] == "overview"
    assert events[0].payload["visible_nodes"] == 3
    assert events[0].payload["hidden_nodes"] == 4
    assert events[0].event_id == "fixed-id-2"
    assert events[0].occurred_at.startswith("2026-01-01")


def test_event_outbox_stores_redacted_payload(api: GraphApi) -> None:
    outbox = InMemoryOutbox()
    api.bus = EventBus(outbox)
    api.dispatch("graph/nodes", {"relations": "linked_to"})
    records = outbox.records(EventKind.GRAPH_FILTERED)
    assert len(records) == 1
    assert records[0].payload["filter"] == "relations=linked_to"
    assert api.bus.outbox is not None
    assert len(api.bus.outbox.replay(EventKind.GRAPH_FILTERED)) == 1


def test_overview_envelope(api: GraphApi) -> None:
    envelope = api.dispatch("graph", {"request_id": "req-overview"})
    payload = data_of(envelope)
    assert envelope["meta"]["version"] == "v4"
    assert envelope["meta"]["request_id"] == "req-overview"
    assert envelope["meta"]["etag"].startswith('W/"')
    assert payload["node_count"] == 7
    assert payload["edge_count"] == 5
    assert payload["component_count"] == 3
    assert payload["isolated_count"] == 1
    assert len(payload["legend"]) == 5
    assert payload["hidden_nodes"] == 0
    assert payload["filter"]["kinds"] == []


def test_overview_hidden_counts(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph", {"kinds": "note", "min_weight": "0.7"}))
    assert payload["hidden_nodes"] == 4
    assert payload["hidden_edges"] == 5
    assert payload["edge_count"] == 0


def test_nodes_are_paginated(api: GraphApi) -> None:
    envelope = api.dispatch("graph/nodes", {"page": "1", "page_size": "3"})
    payload = data_of(envelope)
    assert payload["total"] == 7
    assert payload["page"] == 1
    assert payload["page_size"] == 3
    assert len(payload["items"]) == 3
    assert payload["items"][0]["id"] == NODE_A
    assert envelope["meta"]["next_cursor"]
    assert envelope["meta"]["etag"]


def test_nodes_second_page_and_cursor(api: GraphApi) -> None:
    first = data_of(api.dispatch("graph/nodes", {"page": "1", "page_size": "4"}))
    second = data_of(api.dispatch("graph/nodes", {"page": "2", "page_size": "4"}))
    cursor = first["next_cursor"]
    assert cursor.startswith("v1.")
    assert len(second["items"]) == 3
    assert second["items"][0]["id"] == NODE_E
    assert data_of(api.dispatch("graph/nodes", {"page": "3", "page_size": "4"}))["items"] == []


def test_edges_are_paginated(api: GraphApi) -> None:
    envelope = api.dispatch("graph/edges", {"page": "1", "page_size": "2"})
    payload = data_of(envelope)
    assert payload["total"] == 5
    assert len(payload["items"]) == 2
    assert payload["items"][0]["relation"] == "linked_to"
    assert envelope["meta"]["next_cursor"]


def test_metrics_handler(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/metrics"))
    assert payload["node_count"] == 7
    assert payload["edge_count"] == 5
    assert payload["component_count"] == 3
    assert payload["degree"][NODE_C] == 3
    assert payload["density"] == 0.2381


def test_metrics_handler_with_filter(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/metrics", {"kinds": "note"}))
    assert payload["node_count"] == 3
    assert payload["edge_count"] == 0
    assert payload["isolated_count"] == 3


def test_layout_handler_supports_all_kinds(api: GraphApi) -> None:
    for name in ("force", "circular", "grid"):
        payload = data_of(api.dispatch("graph/layout", {"layout": name}))
        assert payload["kind"] == name
        assert len(payload["points"]) == 7
        assert payload["width"] == 960.0
        assert payload["height"] == 600.0


def test_layout_handler_seed_and_bounds(api: GraphApi) -> None:
    params = {"seed": "9", "iterations": "4", "width": "700", "height": "420"}
    first = data_of(api.dispatch("graph/layout", params))
    second = data_of(api.dispatch("graph/layout", params))
    assert first == second
    assert first["seed"] == 9
    assert first["iterations"] == 4
    assert first["width"] == 700.0
    assert all(0 <= point["x"] <= 700 for point in first["points"])
    assert all(0 <= point["y"] <= 420 for point in first["points"])


def test_path_handler_found(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/path", {"source": NODE_A, "target": NODE_D}))
    assert payload["found"] is True
    assert payload["path"] == [NODE_A, NODE_C, NODE_D]
    assert payload["hops"] == 2


def test_path_handler_unreachable_and_missing(api: GraphApi) -> None:
    unreachable = data_of(api.dispatch("graph/path", {"source": NODE_A, "target": NODE_F}))
    assert unreachable["found"] is False
    assert unreachable["path"] == []
    assert unreachable["hops"] == 0
    missing = error_of(api.dispatch("graph/path", {"source": NODE_A}))
    assert missing["code"] == "invalid_input"
    assert "target" in missing["message"]


def test_filters_handler_facets(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/filters", {"kinds": "note"}))
    assert payload["current"]["kinds"] == ["note"]
    assert "kinds=note" in payload["description"]
    assert set(payload["available_kinds"]) == {
        "note",
        "target",
        "finding",
        "evidence",
    }
    assert len(payload["available_relations"]) == 5
    assert payload["saved"]["notes"]["kinds"] == ["note"]
    assert len(payload["hidden_node_ids"]) == 4


def test_snapshots_handler_pagination(api: GraphApi) -> None:
    api.store.save("second-view", api.builder.build(), GraphFilter(), LayoutKind.FORCE)
    envelope = api.dispatch("graph/snapshots", {"page": "1", "page_size": "1"})
    payload = data_of(envelope)
    assert payload["total"] == 2
    assert payload["items"] == ["alpha-view"]
    assert envelope["meta"]["next_cursor"]


def test_snapshot_handler_and_missing(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/snapshot", {"name": "alpha-view"}))
    assert payload["name"] == "alpha-view"
    assert payload["layout"] == "circular"
    assert payload["tags"] == ["reviewed"]
    assert payload["filter"]["kinds"] == ["note"]
    missing = error_of(api.dispatch("graph/snapshot", {"name": "absent"}))
    assert missing["code"] == "not_found"


def test_export_named_snapshot(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/export", {"name": "alpha-view"}))
    assert payload["name"] == "alpha-view"
    assert json.dumps(payload)
    assert "notes" in payload["filter_index"]


def test_export_current_graph(api: GraphApi) -> None:
    payload = data_of(api.dispatch("graph/export", {"kinds": "note", "layout": "grid"}))
    assert payload["name"] == "current"
    assert payload["layout"] == "grid"
    assert len(payload["data"]["nodes"]) == 3
    assert payload["filter"]["kinds"] == ["note"]


def test_dispatch_unknown_route(api: GraphApi) -> None:
    error = error_of(api.dispatch("graph/does-not-exist"))
    assert error["code"] == "not_found"
    assert "unknown graph route" in error["message"]


def test_dispatch_invalid_inputs(api: GraphApi) -> None:
    cases = (
        ("graph", {"page": "0"}),
        ("graph", {"page_size": "999"}),
        ("graph", {"min_weight": "1.2"}),
        ("graph", {"kinds": "bogus"}),
        ("graph", {"relations": "bad relation"}),
        ("graph", {"layout": "radial"}),
        ("graph/layout", {"width": "10"}),
    )
    for route, params in cases:
        error = error_of(api.dispatch(route, params))
        assert error["code"] == "invalid_input"
        assert error["details"] or error["message"]


def test_request_id_fallback(api: GraphApi) -> None:
    envelope = api.dispatch("graph/metrics")
    assert envelope["meta"]["request_id"] == "fixed-id-1"


def test_handlers_match_registered_routes(api: GraphApi) -> None:
    assert tuple(api.handlers()) == tuple(prefix for prefix, _ in GRAPH_ROUTES)


def test_register_on_local_registry() -> None:
    registry = RouteRegistry()
    register(registry)
    assert len(registry) == 10
    paths = {route["path"] for route in registry.serialize()}
    assert "/api/v4/graph" in paths
    assert "/api/v4/graph/snapshot" in paths
    assert registry.get("/api/v4/graph/nodes") is not None


def test_namespace_discovery_includes_graph_v4() -> None:
    modules = discover_modules()
    assert "graph_v4" in modules
    assert callable(getattr(modules["graph_v4"], "register", None))


def test_dispatch_is_deterministic_for_same_request(api: GraphApi) -> None:
    params = {"kinds": "note", "request_id": "same-request"}
    first = api.dispatch("graph/metrics", params)
    second = api.dispatch("graph/metrics", params)
    assert first == second
    assert json.dumps(first)
