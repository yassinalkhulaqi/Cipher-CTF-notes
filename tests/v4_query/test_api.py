"""Tests for v4 envelopes, capability checks, pagination, and route registration."""

from __future__ import annotations

import pytest

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import ApiError, Capability, CapabilitySet, ErrorCode
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.pagination import Cursor
from redscribe.v4.query.api import QueryApi, register_routes
from redscribe.v4.query.service import SavedQueryService
from redscribe.v4.query.types import QuerySyntaxError, SavedQuery

ID_ONE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ID_TWO = "11111111-2222-3333-4444-555555555555"
TIME = "2026-02-03T04:05:06.000Z"


def sample_documents() -> list[dict[str, object]]:
    return [
        {
            "id": "n1",
            "title": "SQL injection playbook",
            "tags": ["web", "ctf"],
            "kind": "note",
            "status": "open",
            "author": "ada",
        },
        {
            "id": "n2",
            "title": "Web cache deception",
            "tags": ["web"],
            "kind": "finding",
            "status": "closed",
            "author": "grace",
        },
        {
            "id": "n3",
            "title": "SQL map recipes",
            "tags": ["ctf"],
            "kind": "note",
            "status": "open",
            "author": "ada",
        },
    ]


def make_api(
    capabilities: CapabilitySet | None = None,
    gate: FeatureGate | None = None,
    service: SavedQueryService | None = None,
) -> QueryApi:
    counter = {"value": 0}

    def next_request_id() -> str:
        counter["value"] += 1
        return f"req-{counter['value']}"

    return QueryApi(
        service=service,
        capabilities=capabilities,
        gate=gate,
        documents=sample_documents(),
        request_id_factory=next_request_id,
    )


def assert_success(envelope: dict[str, object]) -> dict[str, object]:
    assert "error" not in envelope
    assert "data" in envelope
    assert "meta" in envelope
    meta = envelope["meta"]
    assert isinstance(meta, dict)
    assert meta["version"] == "v4"
    assert str(meta["request_id"]).startswith("req-")
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def assert_error(envelope: dict[str, object], code: str) -> dict[str, object]:
    assert "data" not in envelope
    error = envelope["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], list)
    return error


def test_search_envelope_shape() -> None:
    api = make_api()
    envelope = api.execute("GET", {"action": "search", "expression": "title:contains(sql)"})
    data = assert_success(envelope)
    assert data["expression"] == "title:contains(sql)"
    assert data["normalized"] == "title:contains(sql)"
    assert data["token_count"] == 1
    assert data["cursor_applied"] is False
    hits = data["hits"]
    assert isinstance(hits, dict)
    assert hits["total"] == 2
    assert len(hits["items"]) == 2
    assert hits["items"][0]["id"] == "n1"
    meta = envelope["meta"]
    assert isinstance(meta, dict)
    assert meta["page"] == 1
    assert meta["page_size"] == 20
    assert str(meta["etag"]).startswith('W/"')


def test_search_empty_query_matches_all() -> None:
    api = make_api()
    data = assert_success(api.execute("GET", {"action": "search"}))
    hits = data["hits"]
    assert isinstance(hits, dict)
    assert hits["total"] == 3
    warnings = data["warnings"]
    assert isinstance(warnings, list)
    assert any("empty query" in warning for warning in warnings)


def test_search_accepts_q_alias_and_documents_override() -> None:
    api = make_api()
    documents = [{"id": "custom", "title": "Only result"}]
    data = assert_success(
        api.execute(
            "POST",
            {"action": "search", "q": "title:contains(only)", "documents": documents},
        )
    )
    hits = data["hits"]
    assert isinstance(hits, dict)
    assert hits["total"] == 1
    assert hits["items"][0]["id"] == "custom"


def test_search_pagination_and_cursor() -> None:
    api = make_api()
    first_envelope = api.execute("GET", {"action": "search", "expression": "", "page_size": 2})
    assert_success(first_envelope)
    meta = first_envelope["meta"]
    assert isinstance(meta, dict)
    assert meta["next_cursor"]
    cursor = str(meta["next_cursor"])
    assert Cursor.decode(cursor).offset == 2

    second_envelope = api.execute(
        "GET",
        {"action": "search", "expression": "", "page_size": 2, "page": 2},
    )
    second = assert_success(second_envelope)
    hits = second["hits"]
    assert isinstance(hits, dict)
    assert len(hits["items"]) == 1
    next_meta = second_envelope["meta"]
    assert isinstance(next_meta, dict)
    assert next_meta["next_cursor"] == ""

    cursor_envelope = api.execute(
        "GET",
        {"action": "search", "expression": "", "page_size": 2, "cursor": cursor},
    )
    via_cursor = assert_success(cursor_envelope)
    assert via_cursor["cursor_applied"] is True
    cursor_hits = via_cursor["hits"]
    assert isinstance(cursor_hits, dict)
    assert len(cursor_hits["items"]) == 1
    cursor_meta = cursor_envelope["meta"]
    assert isinstance(cursor_meta, dict)
    assert cursor_meta["page"] == 1


def test_search_facets_and_selections() -> None:
    api = make_api()
    data = assert_success(
        api.execute(
            "GET",
            {
                "action": "search",
                "expression": "",
                "facets": "tag,status",
                "facet_selections": {"tag": ["web"]},
            },
        )
    )
    facets = data["facets"]
    assert isinstance(facets, list)
    assert [facet["field"] for facet in facets] == ["tag", "status"]
    assert facets[0]["values"][0]["selected"] is True
    hits = data["hits"]
    assert isinstance(hits, dict)
    assert hits["total"] == 2


def test_search_clustering_and_ranking() -> None:
    api = make_api()
    data = assert_success(
        api.execute(
            "GET",
            {"action": "search", "expression": "", "cluster_field": "status", "rank": "true"},
        )
    )
    clusters = data["clusters"]
    assert isinstance(clusters, list)
    assert [cluster["key"] for cluster in clusters] == ["open", "closed"]
    summary = data["cluster_summary"]
    assert isinstance(summary, dict)
    assert summary["results"] == 3
    hits = data["hits"]
    assert isinstance(hits, dict)
    assert hits["total"] == 3


def test_search_rejects_bad_input() -> None:
    api = make_api()
    error = assert_error(
        api.execute("GET", {"action": "search", "expression": "bogus:x"}),
        "invalid_input",
    )
    assert any("position=0" in detail for detail in error["details"])
    assert_error(api.execute("GET", {"action": "search", "facets": "unknown"}), "invalid_input")
    assert_error(
        api.execute("GET", {"action": "search", "facet_selections": {"nope": ["x"]}}),
        "invalid_input",
    )
    assert_error(
        api.execute("GET", {"action": "search", "facet_selections": "{bad json"}),
        "invalid_input",
    )
    assert_error(api.execute("GET", {"action": "search", "page": 0}), "invalid_input")
    assert_error(api.execute("GET", {"action": "search", "page_size": 501}), "invalid_input")
    assert_error(api.execute("GET", {"action": "search", "documents": ["bad"]}), "invalid_input")
    assert_error(
        api.execute("GET", {"action": "search", "cluster_field": "bogus"}),
        "invalid_input",
    )
    assert_error(api.execute("GET", {"action": "search", "cursor": "garbage"}), "invalid_input")


def test_dispatch_rejects_unknown_routes() -> None:
    api = make_api()
    assert_error(api.execute("GET", {"action": "save"}), "invalid_input")
    assert_error(api.execute("POST", {"action": "list"}), "invalid_input")
    assert_error(api.execute("PATCH", {"action": "search"}), "invalid_input")


def test_capability_checks() -> None:
    read_only = CapabilitySet(frozenset({Capability.READ}))
    api = make_api(capabilities=read_only)
    assert_success(api.execute("GET", {"action": "search", "expression": ""}))
    error = assert_error(
        api.execute("POST", {"action": "save", "name": "x", "expression": "title:x"}),
        "forbidden",
    )
    assert "missing capability: write" in error["message"]

    no_read = CapabilitySet(frozenset({Capability.WRITE}))
    error = assert_error(make_api(capabilities=no_read).execute("GET", {}), "forbidden")
    assert "missing capability: read" in error["message"]


def test_feature_gate_check() -> None:
    api = make_api(gate=FeatureGate(CapabilitySet.full(), version="v3"))
    error = assert_error(api.execute("GET", {}), "forbidden")
    assert "feature disabled: query_language" in error["message"]
    assert FeatureFlag.QUERY_LANGUAGE.value == "query_language"


def test_saved_query_crud_via_api() -> None:
    ids_values = iter([ID_ONE, ID_TWO])
    bus = EventBus(InMemoryOutbox())
    service = SavedQueryService(bus=bus, clock=lambda: TIME, id_factory=lambda: next(ids_values))
    api = QueryApi(service=service, request_id_factory=lambda: "req-fixed")

    created = assert_success(
        api.execute(
            "POST",
            {"action": "save", "name": "sql hunt", "expression": "title:contains(sql)"},
        )
    )
    assert created["id"] == ID_ONE
    assert created["name"] == "sql hunt"
    assert len(bus.published) == 1
    assert bus.published[0].kind is EventKind.QUERY_SAVED

    listed = assert_success(api.execute("GET", {"action": "list"}))
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == ID_ONE

    fetched = assert_success(api.execute("GET", {"action": "get", "id": ID_ONE}))
    assert fetched["expression"] == "title:contains(sql)"

    renamed = assert_success(
        api.execute("POST", {"action": "rename", "id": ID_ONE, "name": "sql renamed"})
    )
    assert renamed["name"] == "sql renamed"
    assert len(bus.published) == 2

    exported = assert_success(api.execute("POST", {"action": "export"}))
    assert exported["count"] == 1
    assert '"sql renamed"' in exported["json"]

    deleted = assert_success(api.execute("POST", {"action": "delete", "id": ID_ONE}))
    assert deleted["deleted"]["id"] == ID_ONE
    assert len(bus.published) == 3


def test_saved_query_errors_via_api() -> None:
    ids_values = iter([ID_ONE, ID_TWO])
    service = SavedQueryService(clock=lambda: TIME, id_factory=lambda: next(ids_values))
    api = QueryApi(service=service, request_id_factory=lambda: "req-fixed")
    assert_success(
        api.execute("POST", {"action": "save", "name": "sql", "expression": "title:contains(sql)"})
    )
    assert_error(
        api.execute("POST", {"action": "save", "name": "SQL", "expression": "title:x"}),
        "conflict",
    )
    assert_error(api.execute("GET", {"action": "get", "id": ID_TWO}), "not_found")
    assert_error(
        api.execute(
            "POST",
            {"action": "save", "name": "bad", "expression": "bogus:x"},
        ),
        "invalid_input",
    )
    assert_error(api.execute("GET", {"action": "list", "page_size": 0}), "invalid_input")
    assert_error(api.execute("GET", {"action": "list", "cursor": "x"}), "invalid_input")


def test_api_error_passthrough() -> None:
    class ExplodingService(SavedQueryService):
        def list(self) -> tuple[SavedQuery, ...]:
            raise ApiError(ErrorCode.INTERNAL, "boom")

    api = QueryApi(service=ExplodingService(), request_id_factory=lambda: "r")
    error = assert_error(api.execute("GET", {"action": "list"}), "internal")
    assert error["message"] == "boom"


def test_route_registration_is_idempotent() -> None:
    registry = RouteRegistry()
    result = register_routes(registry)
    assert result is registry
    assert len(registry) == 2
    paths = [route.full_path for route in registry.all()]
    assert paths == ["/api/v4/query", "/api/v4/query/saved"]
    assert registry.get("/api/v4/query") is not None
    register_routes(registry)
    assert len(registry) == 2


def test_query_syntax_error_conversion_detail() -> None:
    api = make_api()
    with pytest.raises(QuerySyntaxError):
        api.parser.parse("nope:x")
    error = assert_error(
        api.execute("GET", {"action": "search", "expression": "title:"}), "invalid_input"
    )
    assert error["message"] == "expected a value"
