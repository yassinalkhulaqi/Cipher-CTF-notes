"""Tests for the workbench facade and the graph API namespace."""

from __future__ import annotations

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import V3Router
from redscribe.v3.capabilities import Capabilities
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities import EntityService
from redscribe.v3.events import EventBus
from redscribe.v3.graph_workbench.service import GraphWorkbench, WorkbenchFilters
from redscribe.v3.namespaces import graph as graph_namespace
from tests.v3_graph_workbench import build_service


def make_workbench() -> GraphWorkbench:
    """Build a service with deterministic time and an event bus."""
    return GraphWorkbench(build_service(), bus=EventBus(), clock=FixedClock(50.0))


def test_filters_from_dict_and_apply() -> None:
    filters = WorkbenchFilters.from_dict(
        {"kinds": "note", "tags": ["#alpha"], "severities": ["high"], "query": "Root"}
    )
    assert filters.kinds == ("note",)
    assert filters.tags == ("alpha",)
    graph = make_workbench().graph(filters=filters)
    assert len(graph) == 1
    assert "note:root" in graph.nodes
    with pytest.raises(ValueError, match="max_nodes"):
        WorkbenchFilters.from_dict({"max_nodes": -1})
    with pytest.raises(ValueError, match="cluster dimension"):
        WorkbenchFilters.from_dict({"cluster_dimension": "color"})


def test_filters_cluster_and_max_nodes() -> None:
    workbench = make_workbench()
    filters = WorkbenchFilters.from_dict(
        {"cluster_dimension": "tag", "cluster_key": "alpha", "max_nodes": 1}
    )
    assert len(workbench.graph(filters=filters)) == 1
    assert filters.as_dict()["cluster_key"] == "alpha"


def test_service_layout_clusters_and_path() -> None:
    workbench = make_workbench()
    layout = workbench.layout("radial", options=None)
    assert layout.strategy == "radial"
    assert len(layout) == 4
    assert len(workbench.cluster_dashboard()["chips"]["tag"]) == 2
    result = workbench.path("note:root", "evidence:cap-01")
    assert result.found
    assert result.as_dict()["hops"] == 2
    assert workbench.neighborhood("note:root", depth=1)["count"] == 3
    assert workbench.articulation()["summary"]["cut_vertices"] == 2
    assert "alpha" in workbench.tag_index()


def test_service_inspect_and_overview() -> None:
    workbench = make_workbench()
    inspected = workbench.inspect("note:root")
    assert inspected["entity"]["title"] == "Root note"
    assert inspected["node"]["severity"] == "high"
    assert inspected["degree"] == 2
    assert inspected["clusters"]["tag"] == "alpha"
    overview = workbench.overview()
    assert overview["stats"]["nodes"] == 4
    assert overview["layouts"] == ["force", "hierarchical", "radial", "timeline"]
    assert overview["snapshots"] == 0


def test_service_snapshots_export_and_events() -> None:
    workbench = make_workbench()
    assert workbench.bus is not None
    before = workbench.capture(label="baseline")
    workbench.connect("note:root", "evidence:cap-01", label="cites")
    after = workbench.capture(label="updated")
    assert workbench.compare(before.meta.id, after.meta.id).changed
    assert workbench.export("json").fmt == "json"
    assert '"nodes"' in workbench.export("json").content
    assert workbench.export("mermaid").content.startswith("flowchart")
    kinds = [record.kind for record in workbench.bus.records()]
    assert "graph.snapshot.captured" in kinds
    assert "graph.export.created" in kinds
    assert "graph.link.added" in kinds


def test_service_capability_gate() -> None:
    workbench = GraphWorkbench(EntityService(), capabilities=Capabilities(enabled=frozenset()))
    with pytest.raises(Exception, match="disabled"):
        workbench.graph()


def test_register_creates_all_graph_routes() -> None:
    router = V3Router()
    graph_namespace.register(router)
    assert router.namespaces() == ("graph",)
    assert router.size() == 22
    paths = {route.path for route in router.routes()}
    assert "/api/v3/graph/layout" in paths
    assert "/api/v3/graph/cluster-dashboard" in paths
    assert "/api/v3/graph/tag-index" in paths


def test_namespace_dispatch_full_workflow() -> None:
    router = V3Router()
    graph_namespace.register(router)
    previous = graph_namespace.set_workbench(make_workbench())
    try:
        assert router.dispatch("graph", "overview")["stats"]["nodes"] == 4
        layout = router.dispatch("graph", "layout", {"strategy": "timeline", "seed": 4})
        assert layout["strategy"] == "timeline"
        assert len(layout["positions"]) == 4
        clusters = router.dispatch("graph", "clusters", {"dimension": "severity"})
        assert clusters["dimension"] == "severity"
        path = router.dispatch(
            "graph", "path", {"source": "note:root", "target": "evidence:cap-01"}
        )
        assert path["found"] is True
        assert path["steps"][0]["explanation"].startswith("Step 1")
        cut = router.dispatch("graph", "articulation")
        assert cut["summary"]["cut_vertices"] == 2
        inspect = router.dispatch("graph", "inspect", {"node": "finding:sql-001"})
        assert inspect["entity"]["title"] == "SQL finding"
        snapshot = router.dispatch("graph", "snapshot", {"label": "v1"})
        exported = router.dispatch("graph", "export", {"format": "json"})
        assert exported["format"] == "json"
        diff = router.dispatch(
            "graph",
            "diff",
            {"left": snapshot["meta"]["id"], "right": snapshot["meta"]["id"]},
        )
        assert diff["changed"] is False
        assert router.dispatch("graph", "snapshots")["count"] == 1
        assert router.dispatch("graph", "restore", {"id": snapshot["meta"]["id"]})["nodes"]
        assert router.dispatch("graph", "tag-index")["tags"]["alpha"]
    finally:
        graph_namespace.set_workbench(previous)


def test_namespace_relationship_editing_and_undo() -> None:
    router = V3Router()
    graph_namespace.register(router)
    previous = graph_namespace.set_workbench(make_workbench())
    try:
        created = router.dispatch(
            "graph",
            "connect",
            {"source": "note:root", "target": "evidence:cap-01", "kind": "references"},
        )
        assert created["action"] == "add"
        assert router.dispatch("graph", "graph")["nodes"]
        updated = router.dispatch(
            "graph",
            "update-relationship",
            {
                "source": "note:root",
                "target": "evidence:cap-01",
                "kind": "references",
                "label": "citation",
            },
        )
        assert updated["link"]["label"] == "citation"
        assert router.dispatch("graph", "undo")["applied"] is True
        assert router.dispatch("graph", "redo")["applied"] is True
        assert router.dispatch("graph", "history")["size"] == 2
        removed = router.dispatch(
            "graph",
            "disconnect",
            {
                "source": "note:root",
                "target": "evidence:cap-01",
                "kind": "references",
                "label": "citation",
            },
        )
        assert removed["action"] == "remove"
    finally:
        graph_namespace.set_workbench(previous)


def test_namespace_validation_and_capability_headers() -> None:
    router = V3Router()
    graph_namespace.register(router)
    previous = graph_namespace.set_workbench(make_workbench())
    try:
        with pytest.raises(V3Error) as missing:
            router.dispatch("graph", "path", {"source": "note:root"})
        assert missing.value.code.value == "missing_field"
        with pytest.raises(V3Error) as invalid:
            router.dispatch("graph", "layout", {"strategy": "spiral"})
        assert invalid.value.code.value == "invalid_request"
        with pytest.raises(V3Error) as forbidden:
            router.dispatch("graph", "overview", {}, {"X-Capability": "reports"})
        assert forbidden.value.code.value == "forbidden"
        with pytest.raises(V3Error) as unknown:
            router.dispatch("graph", "restore", {"id": "nope"})
        assert unknown.value.code.value == "not_found"
        assert (
            router.dispatch("graph", "overview", {}, {"X-Capability": "graph"})["stats"]["nodes"]
            == 4
        )
    finally:
        graph_namespace.set_workbench(previous)


def test_namespace_default_service_is_lazy() -> None:
    previous = graph_namespace.reset_workbench()
    try:
        first = graph_namespace.current_workbench()
        assert first is graph_namespace.current_workbench()
        assert graph_namespace.reset_workbench() is first
        assert graph_namespace.current_workbench() is not first
    finally:
        graph_namespace.set_workbench(previous)
