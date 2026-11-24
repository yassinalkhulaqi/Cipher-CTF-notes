"""Search namespace route registration and dispatch."""

from __future__ import annotations

import pytest

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.entities.types import EntityKind
from redscribe.v3.namespaces import search as search_namespace
from tests.v3_search_intel.helpers import ref


@pytest.fixture
def router() -> V3Router:
    search_namespace.reset_service()
    instance = V3Router()
    search_namespace.register(instance)
    return instance


def test_register_adds_expected_actions(router: V3Router) -> None:
    assert "search" in router.namespaces()
    assert router.size() >= 19
    for action in (
        "parse",
        "grammar",
        "search",
        "facets",
        "clusters",
        "pivots",
        "autocomplete",
        "templates",
        "template_render",
        "saved_list",
        "saved_create",
        "saved_update",
        "saved_delete",
        "facet_sets_list",
        "facet_sets_create",
        "facet_sets_delete",
        "index_state",
        "snapshot",
        "load",
    ):
        assert router.get("search", action) is not None


def test_grammar_route(router: V3Router) -> None:
    result = router.dispatch("search", "grammar")
    assert result["grammar"]["version"] == 2


def test_parse_route(router: V3Router) -> None:
    result = router.dispatch("search", "parse", {"query": "kind:finding"})
    assert result["parsed"]["valid"]


def test_parse_route_requires_query(router: V3Router) -> None:
    with pytest.raises(V3Error) as exc:
        router.dispatch("search", "parse", {})
    assert exc.value.code is V3ErrorCode.MISSING_FIELD


def test_search_route(router: V3Router) -> None:
    service = search_namespace.get_service()
    service.entities.create(EntityKind.FINDING, title="Route finding", value="r1")
    result = router.dispatch("search", "search", {"query": "kind:finding", "fields": ["kind"]})
    assert result["total"] == 1
    assert result["facets"]


def test_search_route_validates_selected(router: V3Router) -> None:
    with pytest.raises(V3Error) as exc:
        router.dispatch("search", "search", {"query": "x", "selected": []})
    assert exc.value.code is V3ErrorCode.INVALID_REQUEST


def test_autocomplete_route(router: V3Router) -> None:
    result = router.dispatch("search", "autocomplete", {"text": "ki"})
    assert result["completions"]


def test_saved_crud_routes(router: V3Router) -> None:
    created = router.dispatch("search", "saved_create", {"name": "Saved", "query": "kind:finding"})
    item_id = created["item"]["id"]
    assert router.dispatch("search", "saved_list")["items"][0]["id"] == item_id
    updated = router.dispatch("search", "saved_update", {"id": item_id, "name": "Renamed"})
    assert updated["item"]["name"] == "Renamed"
    assert router.dispatch("search", "saved_delete", {"id": item_id})["deleted"]


def test_saved_routes_missing_and_not_found(router: V3Router) -> None:
    with pytest.raises(V3Error, match="Unknown saved search"):
        router.dispatch("search", "saved_delete", {"id": "missing"})
    with pytest.raises(V3Error, match="Invalid 'saved_search'"):
        router.dispatch("search", "saved_create", {"name": "", "query": "x"})


def test_facet_set_routes(router: V3Router) -> None:
    created = router.dispatch(
        "search", "facet_sets_create", {"name": "Triage", "fields": ["kind", "severity"]}
    )
    item_id = created["item"]["id"]
    assert router.dispatch("search", "facet_sets_list")["items"][0]["id"] == item_id
    assert router.dispatch("search", "facet_sets_delete", {"id": item_id})["deleted"]


def test_template_routes(router: V3Router) -> None:
    templates = router.dispatch("search", "templates")["templates"]
    assert templates
    rendered = router.dispatch(
        "search",
        "template_render",
        {"template_id": "critical-findings", "values": {}},
    )
    assert rendered["query"] == "kind:finding severity:critical"


def test_template_render_errors(router: V3Router) -> None:
    with pytest.raises(V3Error, match="Unknown template"):
        router.dispatch("search", "template_render", {"template_id": "none", "values": {}})
    with pytest.raises(V3Error, match="Invalid 'values'"):
        router.dispatch(
            "search",
            "template_render",
            {"template_id": "critical-findings", "values": {"extra": 1}},
        )


def test_pivots_and_index_state_routes(router: V3Router) -> None:
    service = search_namespace.get_service()
    finding = service.entities.create(EntityKind.FINDING, title="Finding", value="p1")
    context = router.dispatch("search", "pivots", {"ref": str(finding.entity_id)})
    assert context["context"]["origin"] == ref("finding", "p1")
    state = router.dispatch("search", "index_state")
    assert state["state"]["documents"] == 1


def test_snapshot_and_load_routes(router: V3Router) -> None:
    router.dispatch("search", "saved_create", {"name": "A", "query": "kind:note"})
    snapshot = router.dispatch("search", "snapshot")["snapshot"]
    search_namespace.reset_service()
    result = router.dispatch("search", "load", {"snapshot": snapshot})
    assert result["imported"] == 1
    assert router.dispatch("search", "saved_list")["items"][0]["name"] == "A"


def test_capability_gate(router: V3Router) -> None:
    result = router.dispatch("search", "grammar", {}, {"X-Capability": "search_v2"})
    assert result["grammar"]["version"] == 2
    with pytest.raises(V3Error) as exc:
        router.dispatch("search", "grammar", {}, {"X-Capability": "reports"})
    assert exc.value.code is V3ErrorCode.FORBIDDEN


def test_invalid_body_types(router: V3Router) -> None:
    with pytest.raises(V3Error, match="expected a string"):
        router.dispatch("search", "parse", {"query": 42})
    with pytest.raises(V3Error, match="expected an object"):
        router.dispatch("search", "load", {"snapshot": []})
