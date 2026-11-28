"""Tests for v4 inbox API envelopes, validation, pagination, and gates."""

from __future__ import annotations

from typing import Any

import pytest

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    ErrorCode,
    PageMeta,
    fail,
    ok,
)
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.inbox.api import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ROUTE_SPECS,
    InboxRoutes,
    error_envelope,
    optional_confidence,
    optional_int,
    optional_tags,
    register,
    require_str,
)
from redscribe.v4.inbox.service import (
    CaptureNotFoundError,
    InboxService,
    MissingTemplateKeyError,
    TransitionError,
    UnknownTemplateError,
)
from redscribe.v4.inbox.types import TriageState
from redscribe.v4.pagination import Cursor, PaginationError

ITEM_ID = "11111111-2222-3333-4444-555555555555"
ITEM_ID_2 = "22222222-3333-4444-5555-666666666666"
ITEM_ID_3 = "33333333-4444-5555-6666-777777777777"
TIMESTAMP = "2026-01-02T03:04:05.000Z"


def fixed_clock() -> str:
    return TIMESTAMP


def fixed_request_id() -> str:
    return "req-fixed"


def make_routes(
    capabilities: CapabilitySet | None = None,
    bus: EventBus | None = None,
) -> InboxRoutes:
    return InboxRoutes(
        service=InboxService(bus=bus, clock=fixed_clock),
        capabilities=capabilities,
        request_id_factory=fixed_request_id,
    )


def seed(routes: InboxRoutes, count: int = 3) -> list[str]:
    ids = [ITEM_ID, ITEM_ID_2, ITEM_ID_3]
    for index in range(count):
        routes.create({"raw": f"note {index}", "item_id": ids[index]})
    return ids[:count]


def envelope_data(payload: dict[str, Any]) -> dict[str, Any]:
    assert "data" in payload
    assert "meta" in payload
    return payload["data"]


def test_contract_envelope_helpers() -> None:
    meta = PageMeta(request_id="r1", page=2, page_size=10, etag='W/"x"')
    success = ok({"value": 1}, meta)
    assert success["data"] == {"value": 1}
    assert success["meta"]["request_id"] == "r1"
    assert success["meta"]["etag"] == 'W/"x"'
    error = fail(ApiError(ErrorCode.INVALID_INPUT, "bad", ("raw",)))
    assert error["error"]["code"] == "invalid_input"
    assert error["error"]["details"] == ["raw"]


def test_list_returns_v4_envelope_with_meta() -> None:
    routes = make_routes()
    seed(routes, 2)
    payload = routes.list({})
    data = envelope_data(payload)
    assert payload["meta"]["version"] == "v4"
    assert payload["meta"]["request_id"] == "req-fixed"
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["page_size"] == DEFAULT_PAGE_SIZE
    assert payload["meta"]["etag"].startswith('W/"')
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["filters"]["state"] == ""
    assert "next_cursor" in data


def test_list_pagination_pages_and_cursor() -> None:
    routes = make_routes()
    seed(routes, 3)
    first = envelope_data(routes.list({"page_size": 1}))
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = envelope_data(routes.list({"page_size": 1, "page": 2}))
    assert len(second["items"]) == 1
    assert second["items"][0]["raw"] != first["items"][0]["raw"]
    cursor = Cursor.decode(first["next_cursor"])
    assert cursor.offset == 1
    from_cursor = envelope_data(routes.list({"page_size": 2, "cursor": first["next_cursor"]}))
    assert len(from_cursor["items"]) == 2


def test_list_filters_state_source_tag_and_query() -> None:
    routes = make_routes()
    routes.create({"raw": "flag{alpha}", "tags": ["ctf"]})
    routes.create({"raw": "https://example.test", "tags": ["web"]})
    second = envelope_data(routes.list({"query": "example"}))["items"][0]
    routes.triage({"id": second["id"], "state": "accepted"})
    assert len(envelope_data(routes.list({"state": "accepted"}))["items"]) == 1
    assert len(envelope_data(routes.list({"state": "untriaged"}))["items"]) == 1
    assert len(envelope_data(routes.list({"source": "flag"}))["items"]) == 1
    assert len(envelope_data(routes.list({"source": "link"}))["items"]) == 1
    assert len(envelope_data(routes.list({"tag": "web"}))["items"]) == 1
    assert envelope_data(routes.list({"query": "nope"}))["total"] == 0


def test_list_etag_not_modified() -> None:
    routes = make_routes()
    seed(routes, 1)
    first = routes.list({})
    etag = first["meta"]["etag"]
    second = routes.list({}, {"If-None-Match": etag})
    assert envelope_data(second)["not_modified"] is True
    assert envelope_data(second)["items"] == []
    assert second["meta"]["etag"] == etag


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ({"page": "0"}, "page"),
        ({"page_size": str(MAX_PAGE_SIZE + 1)}, "page_size"),
        ({"page_size": "many"}, "page_size"),
        ({"state": "deleted"}, "state"),
        ({"source": "email"}, "source"),
        ({"cursor": "bad-cursor"}, "cursor"),
    ],
)
def test_list_rejects_invalid_query(query: dict[str, str], field: str) -> None:
    routes = make_routes()
    with pytest.raises(ApiError) as exc_info:
        routes.list(query)
    assert exc_info.value.code is ErrorCode.INVALID_INPUT
    assert field in str(exc_info.value) or field in exc_info.value.details


def test_list_requires_read_capability() -> None:
    routes = make_routes(CapabilitySet(frozenset({Capability.WRITE})))
    with pytest.raises(ApiError) as exc_info:
        routes.list({})
    assert exc_info.value.code is ErrorCode.FORBIDDEN
    routes_full = make_routes(CapabilitySet.full())
    assert envelope_data(routes_full.list({}))["total"] == 0


def test_create_envelope_and_events() -> None:
    outbox = InMemoryOutbox()
    routes = make_routes(bus=EventBus(outbox))
    payload = routes.create(
        {"raw": "flag{alpha}", "tags": ["CTF"], "source": "flag", "confidence": 0.8},
        {"X-Request-ID": "custom-id"},
    )
    data = envelope_data(payload)
    assert payload["meta"]["request_id"] == "custom-id"
    assert data["created"] is True
    assert data["duplicate"] is False
    assert data["capture"]["source"] == "flag"
    assert data["capture"]["tags"] == ["ctf", "flag"]
    assert data["capture"]["state"] == "untriaged"
    assert len(outbox.records(EventKind.CAPTURE_CREATED)) == 1


def test_create_dedupe_reports_existing_item() -> None:
    outbox = InMemoryOutbox()
    routes = make_routes(bus=EventBus(outbox))
    first = envelope_data(routes.create({"raw": "note"}))
    second = envelope_data(routes.create({"raw": "  NOTE  "}))
    assert first["created"] is True
    assert second["created"] is False
    assert second["duplicate"] is True
    assert second["capture"]["id"] == first["capture"]["id"]
    assert len(outbox.records(EventKind.CAPTURE_CREATED)) == 1


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({}, "raw"),
        ({"raw": ""}, "raw"),
        ({"raw": "  "}, "raw"),
        ({"raw": 42}, "raw"),
        ({"raw": "note", "source": "email"}, "source"),
        ({"raw": "note", "tags": "not-a-list"}, "tags"),
        ({"raw": "note", "tags": [1, 2]}, "tags"),
        ({"raw": "note", "tags": ["!!!"]}, "tags"),
        ({"raw": "note", "confidence": "high"}, "confidence"),
        ({"raw": "note", "confidence": 4}, "confidence"),
    ],
)
def test_create_rejects_invalid_body(body: dict[str, Any], detail: str) -> None:
    routes = make_routes()
    with pytest.raises(ApiError) as exc_info:
        routes.create(body)
    assert exc_info.value.code is ErrorCode.INVALID_INPUT
    assert detail in str(exc_info.value) or detail in exc_info.value.details


def test_create_requires_write_capability() -> None:
    routes = make_routes(CapabilitySet(frozenset({Capability.READ})))
    with pytest.raises(ApiError) as exc_info:
        routes.create({"raw": "note"})
    assert exc_info.value.code is ErrorCode.FORBIDDEN


def test_triage_by_state() -> None:
    outbox = InMemoryOutbox()
    routes = make_routes(bus=EventBus(outbox))
    item_id = envelope_data(routes.create({"raw": "note"}))["capture"]["id"]
    payload = routes.triage(
        {"id": item_id, "state": "accepted"},
        {"X-Actor": "triager"},
    )
    data = envelope_data(payload)
    assert data["from_state"] == "untriaged"
    assert data["to_state"] == "accepted"
    assert data["capture"]["state"] == "accepted"
    assert outbox.records(EventKind.CAPTURE_TRAGED)[0].payload["actor"] == "triager"


def test_triage_by_action() -> None:
    routes = make_routes()
    item_id = envelope_data(routes.create({"raw": "note"}))["capture"]["id"]
    data = envelope_data(routes.triage({"id": item_id, "action": "Reject"}))
    assert data["to_state"] == "rejected"
    archived = envelope_data(routes.triage({"id": item_id, "action": "archive"}))
    assert archived["from_state"] == "rejected"
    assert archived["to_state"] == "archived"


def test_triage_rejects_illegal_transition() -> None:
    routes = make_routes()
    item_id = envelope_data(routes.create({"raw": "note"}))["capture"]["id"]
    routes.triage({"id": item_id, "state": "accepted"})
    with pytest.raises(ApiError) as exc_info:
        routes.triage({"id": item_id, "state": "rejected"})
    assert exc_info.value.code is ErrorCode.CONFLICT
    assert exc_info.value.details == ("archived",)


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"state": "accepted"}, "id"),
        ({"id": "@id"}, "either state or action"),
        ({"id": "@id", "state": "unknown"}, "state"),
        ({"id": "@id", "action": "delete"}, "action"),
    ],
)
def test_triage_rejects_invalid_body(body: dict[str, Any], detail: str) -> None:
    routes = make_routes()
    item_id = envelope_data(routes.create({"raw": "note"}))["capture"]["id"]
    resolved = {key: (item_id if value == "@id" else value) for key, value in body.items()}
    with pytest.raises(ApiError) as exc_info:
        routes.triage(resolved)
    assert exc_info.value.code is ErrorCode.INVALID_INPUT
    assert detail in str(exc_info.value) or detail in exc_info.value.details


def test_triage_missing_item_maps_to_not_found() -> None:
    routes = make_routes()
    with pytest.raises(ApiError) as exc_info:
        routes.triage({"id": ITEM_ID_3, "state": "accepted"})
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_triage_requires_write_capability() -> None:
    routes = make_routes(CapabilitySet(frozenset({Capability.READ})))
    with pytest.raises(ApiError) as exc_info:
        routes.triage({"id": ITEM_ID, "state": "accepted"})
    assert exc_info.value.code is ErrorCode.FORBIDDEN


def test_error_envelope_translates_domain_errors() -> None:
    assert error_envelope(ApiError(ErrorCode.CONFLICT, "x"))["error"]["code"] == "conflict"
    assert error_envelope(CaptureNotFoundError(ITEM_ID))["error"]["code"] == "not_found"
    assert (
        error_envelope(
            TransitionError(TriageState.ACCEPTED, TriageState.REJECTED, (TriageState.ARCHIVED,))
        )["error"]["code"]
        == "conflict"
    )
    assert error_envelope(ValueError("bad"))["error"]["code"] == "invalid_input"
    assert error_envelope(UnknownTemplateError("x"))["error"]["code"] == "invalid_input"
    assert error_envelope(MissingTemplateKeyError("raw", "note"))["error"]["code"] == (
        "invalid_input"
    )
    assert error_envelope(RuntimeError("boom"))["error"]["code"] == "internal"


def test_request_helpers() -> None:
    assert require_str({"raw": " value "}, "raw") == "value"
    with pytest.raises(ApiError, match="non-empty"):
        require_str({"raw": 5}, "raw")
    assert optional_int({}, "page", 7, 1, 10) == 7
    assert optional_int({"page": "3"}, "page", 1, 1, 10) == 3
    with pytest.raises(ApiError, match="between"):
        optional_int({"page": 99}, "page", 1, 1, 10)
    with pytest.raises(ApiError, match="integer"):
        optional_int({"page": True}, "page", 1, 1, 10)
    assert optional_tags({"tags": ["Alpha"]}) == ("alpha",)
    assert optional_confidence({"confidence": 0.3}) == 0.3
    with pytest.raises(ApiError, match="number"):
        optional_confidence({"confidence": True})


def test_register_routes_is_idempotent() -> None:
    registry = RouteRegistry()
    first = register(registry)
    second = register(registry)
    assert len(first) == len(ROUTE_SPECS) == 3
    assert [route.name for route in second] == [route.name for route in first]
    assert len(registry) == 3
    assert {route.full_path for route in registry.all()} == {
        "/api/v4/inbox",
        "/api/v4/inbox/capture",
        "/api/v4/inbox/triage",
    }
    assert registry.get("/api/v4/inbox") is not None


def test_register_uses_global_registry() -> None:
    from redscribe.v4.api_v4 import global_registry

    routes = register()
    assert len(routes) == len(ROUTE_SPECS)
    assert global_registry().get("/api/v4/inbox") is not None


def test_feature_flag_is_inbox() -> None:
    from redscribe.v4.capabilities import DEFAULT_REQUIREMENTS

    assert FeatureFlag.INBOX.value == "inbox"
    assert FeatureFlag.INBOX in DEFAULT_REQUIREMENTS
    assert Capability.READ in DEFAULT_REQUIREMENTS[FeatureFlag.INBOX].required


def test_pagination_error_is_validation_error() -> None:
    assert error_envelope(PaginationError("bad"))["error"]["code"] == "invalid_input"
    assert error_envelope(TypeError("bad"))["error"]["code"] == "invalid_input"
