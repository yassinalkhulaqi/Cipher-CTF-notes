"""Combined tests for the findings v4 API envelopes, errors and workflows."""

from __future__ import annotations

import pytest

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.contracts import Capability, CapabilitySet
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.findings_v4.api import FindingApi, FindingRequest, FindingResponse
from redscribe.v4.findings_v4.service import FindingService
from redscribe.v4.findings_v4.storage import FindingStore
from redscribe.v4.findings_v4.types import (
    CvssV4Vector,
    Finding,
    LifecycleState,
    Severity,
)

STRONG_VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
WEAK_VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:N/SA:N"
READ_WRITE = CapabilitySet(frozenset({Capability.READ, Capability.WRITE}))
READ_ONLY = CapabilitySet(frozenset({Capability.READ}))
WRITE_ONLY = CapabilitySet(frozenset({Capability.WRITE}))
Bundle = tuple[FindingApi, FindingService, EventBus, FindingStore]

EXPORT_CAPS = CapabilitySet(frozenset({Capability.READ, Capability.WRITE, Capability.EXPORT}))


def fixed_clock() -> str:
    return "2026-07-01T09:30:00.000Z"


@pytest.fixture
def bundle() -> tuple[FindingApi, FindingService, EventBus, FindingStore]:
    store = FindingStore()
    bus = EventBus(InMemoryOutbox())
    service = FindingService(store=store, bus=bus, clock=fixed_clock)
    return FindingApi(service), service, bus, store


def request(
    method: str = "GET",
    query: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
    capabilities: CapabilitySet | None = None,
    if_none_match: str = "",
    request_id: str = "req-fixed",
) -> FindingRequest:
    return FindingRequest(
        method=method,
        query=query or {},
        body=body or {},
        capabilities=capabilities or CapabilitySet.full(),
        if_none_match=if_none_match,
        request_id=request_id,
    )


def error_code(response: FindingResponse) -> str:
    return str(response.payload["error"]["code"])


def test_get_empty_list_envelope(bundle: Bundle) -> None:
    api = bundle[0]
    response = api.list_findings(request())
    assert response.status == 200
    data = response.payload["data"]
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["next_cursor"] == ""
    assert data["etag"]
    meta = response.payload["meta"]
    assert meta["version"] == "v4"
    assert meta["request_id"] == "req-fixed"
    assert meta["page"] == 1
    assert meta["page_size"] == 50
    assert meta["etag"].startswith('W/"')


def test_get_returns_finding_dicts(bundle: Bundle) -> None:
    api, service = bundle[0], bundle[1]
    service.create(title="First", vector_text=STRONG_VECTOR, finding_id="api-1")
    response = api.list_findings(request())
    item = response.payload["data"]["items"][0]
    assert item["id"] == "api-1"
    assert item["title"] == "First"
    assert item["severity"] == "critical"
    assert item["vector"].startswith("CVSS:4.0/")


def test_get_pagination_and_cursor(bundle: Bundle) -> None:
    api, service = bundle[0], bundle[1]
    for index in range(5):
        service.create(title=f"Finding {index}", finding_id=f"page-{index}")
    first = api.list_findings(request(query={"page": "1", "page_size": "2"}))
    assert first.payload["data"]["total"] == 5
    assert len(first.payload["data"]["items"]) == 2
    assert first.payload["data"]["next_cursor"]
    second = api.list_findings(request(query={"page": "2", "page_size": "2"}))
    assert second.payload["data"]["page"] == 2
    assert len(second.payload["data"]["items"]) == 2
    third = api.list_findings(request(query={"page": "3", "page_size": "2"}))
    assert len(third.payload["data"]["items"]) == 1
    assert third.payload["data"]["next_cursor"] == ""


def test_get_etag_not_modified(bundle: Bundle) -> None:
    api, service = bundle[0], bundle[1]
    service.create(title="Cached", finding_id="cache-1")
    original = api.list_findings(request())
    etag = str(original.payload["meta"]["etag"])
    cached = api.list_findings(request(if_none_match=etag))
    assert cached.status == 304
    assert cached.payload["data"] is None
    assert cached.payload["meta"]["etag"] == etag


@pytest.mark.parametrize(
    "query",
    [
        {"page": "0"},
        {"page": "abc"},
        {"page_size": "0"},
        {"page_size": "501"},
        {"page_size": "many"},
    ],
)
def test_get_rejects_bad_pagination(
    bundle: Bundle,
    query: dict[str, str],
) -> None:
    api = bundle[0]
    response = api.list_findings(request(query=query))
    assert response.status == 400
    assert error_code(response) == "invalid_input"


def test_get_filters_by_severity(bundle: Bundle) -> None:
    api, service = bundle[0], bundle[1]
    service.create(title="Critical", vector_text=STRONG_VECTOR, finding_id="filter-1")
    service.create(title="None", vector_text=WEAK_VECTOR, finding_id="filter-2")
    response = api.list_findings(request(query={"severity": "critical"}))
    assert response.payload["data"]["total"] == 1
    assert response.payload["data"]["items"][0]["id"] == "filter-1"
    none_response = api.list_findings(request(query={"severity": "none"}))
    assert none_response.payload["data"]["items"][0]["id"] == "filter-2"


def test_get_filters_by_state(bundle: Bundle) -> None:
    api, service = bundle[0], bundle[1]
    service.create(title="Draft", finding_id="filter-3")
    opened = service.create(
        title="Open",
        finding_id="filter-4",
        lifecycle_state=LifecycleState.OPEN,
    )
    assert opened.lifecycle_state is LifecycleState.OPEN
    response = api.list_findings(request(query={"state": "open"}))
    assert response.payload["data"]["total"] == 1
    assert response.payload["data"]["items"][0]["id"] == "filter-4"


def test_get_filters_by_severity_and_state(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    service.create(
        title="Critical open",
        vector_text=STRONG_VECTOR,
        finding_id="filter-5",
        lifecycle_state=LifecycleState.OPEN,
    )
    service.create(title="Critical draft", vector_text=STRONG_VECTOR, finding_id="filter-6")
    response = api.list_findings(request(query={"severity": "critical", "state": "open"}))
    assert response.payload["data"]["total"] == 1
    assert response.payload["data"]["items"][0]["id"] == "filter-5"


@pytest.mark.parametrize(
    "query",
    [{"severity": "ultra"}, {"state": "unknown"}, {"severity": "OPEN"}],
)
def test_get_rejects_bad_filters(
    bundle: Bundle,
    query: dict[str, str],
) -> None:
    api = bundle[0]
    response = api.list_findings(request(query=query))
    assert response.status == 400
    assert error_code(response) == "invalid_input"


def test_get_without_read_capability(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.list_findings(request(capabilities=WRITE_ONLY))
    assert response.status == 403
    assert error_code(response) == "forbidden"
    assert "cvss_v4" in response.payload["error"]["message"]


def test_get_without_cvss_feature(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.list_findings(request(capabilities=READ_ONLY))
    assert response.status == 403
    assert error_code(response) == "forbidden"


def test_get_snapshot_view(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    service.create(title="Snapshot", finding_id="snap-1")
    response = api.dispatch(request(query={"view": "snapshot"}, capabilities=EXPORT_CAPS))
    assert response.status == 200
    assert response.payload["data"]["version"] == 1
    assert response.payload["data"]["findings"][0]["id"] == "snap-1"


def test_get_snapshot_requires_export(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.dispatch(request(query={"view": "snapshot"}, capabilities=READ_WRITE))
    assert response.status == 403
    assert error_code(response) == "forbidden"


def test_post_creates_and_scores(
    bundle: Bundle,
) -> None:
    api, service, bus, store = bundle
    response = api.create_finding(
        request(
            method="POST",
            body={"title": "Command injection", "vector": STRONG_VECTOR, "description": "d"},
        )
    )
    assert response.status == 201
    data = response.payload["data"]
    assert data["finding"]["title"] == "Command injection"
    assert data["finding"]["severity"] == "critical"
    assert data["score"]["base"] == 9.8
    assert store.count() == 1
    assert [event.kind for event in bus.published] == [
        EventKind.FINDING_CREATED,
        EventKind.FINDING_SCORED,
    ]
    assert service.get(data["finding"]["id"]).description == "d"


def test_post_uses_default_vector(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.create_finding(request(method="POST", body={"title": "Default"}))
    assert response.status == 201
    assert response.payload["data"]["finding"]["severity"] == "none"


def test_post_requires_title(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.create_finding(request(method="POST", body={}))
    assert response.status == 400
    assert error_code(response) == "invalid_input"
    assert "title is required" in response.payload["error"]["message"]


def test_post_rejects_invalid_vector(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.create_finding(
        request(method="POST", body={"title": "Bad", "vector": "CVSS:4.0/AV:N"})
    )
    assert response.status == 400
    assert error_code(response) == "invalid_input"
    assert "invalid_vector" in response.payload["error"]["details"]


def test_post_requires_write_capability(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.create_finding(
        request(method="POST", body={"title": "No write"}, capabilities=READ_ONLY)
    )
    assert response.status == 403
    assert error_code(response) == "forbidden"


def _seed(
    service: FindingService,
    finding_id: str,
    title: str = "Seeded",
    vector: str = STRONG_VECTOR,
    state: LifecycleState = LifecycleState.DRAFT,
) -> Finding:
    return service.create(
        title=title,
        vector_text=vector,
        finding_id=finding_id,
        lifecycle_state=state,
    )


def test_put_score_action(
    bundle: Bundle,
) -> None:
    api, service, bus = bundle[0], bundle[1], bundle[2]
    _seed(service, "put-1", vector=WEAK_VECTOR)
    service.get("put-1").vector = CvssV4Vector.parse(STRONG_VECTOR)
    response = api.update_finding(request(method="PUT", body={"id": "put-1", "action": "score"}))
    assert response.status == 200
    assert response.payload["data"]["finding"]["severity"] == "critical"
    assert response.payload["data"]["score"]["base"] == 9.8
    assert bus.published[-1].kind is EventKind.FINDING_SCORED


def test_put_transition_action(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-2")
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-2", "action": "transition", "state": "open"},
        )
    )
    assert response.status == 200
    assert response.payload["data"]["finding"]["lifecycle_state"] == "open"


def test_put_illegal_transition_conflict(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-3")
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-3", "action": "transition", "state": "closed"},
        )
    )
    assert response.status == 409
    assert error_code(response) == "conflict"
    assert "illegal_transition" in response.payload["error"]["details"]


def test_put_unknown_transition_state(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-4")
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-4", "action": "transition", "state": "bogus"},
        )
    )
    assert response.status == 400
    assert error_code(response) == "invalid_input"


def test_put_remediation_action(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-5")
    response = api.update_finding(
        request(
            method="PUT",
            body={
                "id": "put-5",
                "action": "remediation",
                "due": "2026-11-30",
                "notes": "Upgrade library",
            },
        )
    )
    assert response.status == 200
    finding = response.payload["data"]["finding"]
    assert finding["remediation_due"] == "2026-11-30"
    assert finding["remediation_notes"] == "Upgrade library"


@pytest.mark.parametrize("due", ["bogus", "2026-02-30", "2026/11/30"])
def test_put_remediation_rejects_bad_due(
    bundle: Bundle,
    due: str,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-6")
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-6", "action": "remediation", "due": due},
        )
    )
    assert response.status == 400
    assert error_code(response) == "invalid_input"


def test_put_retest_action(
    bundle: Bundle,
) -> None:
    api, service, bus = bundle[0], bundle[1], bundle[2]
    _seed(service, "put-7", state=LifecycleState.REMEDIATING)
    response = api.update_finding(
        request(
            method="PUT",
            body={
                "id": "put-7",
                "action": "retest",
                "verdict": "fail",
                "note": "still exploitable",
            },
        )
    )
    assert response.status == 200
    data = response.payload["data"]
    assert data["retest"]["sequence"] == 1
    assert data["retest"]["score"] == 9.8
    assert data["finding"]["retest_count"] == 1
    assert bus.published[-1].kind is EventKind.FINDING_RETESTED


def test_put_retest_rejects_bad_verdict(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-8", state=LifecycleState.RETEST)
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-8", "action": "retest", "verdict": "maybe"},
        )
    )
    assert response.status == 400
    assert error_code(response) == "invalid_input"


def test_put_retest_rejects_invalid_state(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-9")
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-9", "action": "retest", "verdict": "pass"},
        )
    )
    assert response.status == 409
    assert error_code(response) == "conflict"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"id": "x", "action": "unknown"},
        {"id": "x", "action": "transition"},
        {"id": "x", "action": "remediation"},
        {"id": "x", "action": "retest"},
    ],
)
def test_put_rejects_incomplete_requests(
    bundle: Bundle,
    body: dict[str, object],
) -> None:
    api = bundle[0]
    response = api.update_finding(request(method="PUT", body=body))
    assert response.status == 400
    assert error_code(response) == "invalid_input"


def test_put_missing_finding_is_not_found(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.update_finding(request(method="PUT", body={"id": "missing", "action": "score"}))
    assert response.status == 404
    assert error_code(response) == "not_found"


def test_put_requires_write_capability(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "put-10")
    response = api.update_finding(
        request(
            method="PUT",
            body={"id": "put-10", "action": "score"},
            capabilities=READ_ONLY,
        )
    )
    assert response.status == 403
    assert error_code(response) == "forbidden"


def test_dispatch_routes_all_methods(
    bundle: Bundle,
) -> None:
    api, service = bundle[0], bundle[1]
    _seed(service, "dispatch-1")
    assert api.dispatch(request(method="GET")).status == 200
    assert api.dispatch(request(method="POST", body={"title": "Dispatched"})).status == 201
    assert (
        api.dispatch(request(method="PUT", body={"id": "dispatch-1", "action": "score"})).status
        == 200
    )
    unsupported = api.dispatch(request(method="DELETE"))
    assert unsupported.status == 400
    assert error_code(unsupported) == "invalid_input"


def test_register_route(bundle: Bundle) -> None:
    api = bundle[0]
    registry = RouteRegistry()
    api.register(registry)
    route = registry.get("/api/v4/findings")
    assert route is not None
    assert route.name == "findings-v4"
    assert len(registry) == 1


def test_error_envelopes_have_details(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.create_finding(request(method="POST", body={}))
    assert set(response.payload) == {"error"}
    error = response.payload["error"]
    assert set(error) == {"code", "message", "details"}
    assert isinstance(error["details"], list)


def test_request_id_is_propagated(
    bundle: Bundle,
) -> None:
    api = bundle[0]
    response = api.list_findings(request(request_id="trace-me"))
    assert response.payload["meta"]["request_id"] == "trace-me"


def test_full_finding_workflow(
    bundle: Bundle,
) -> None:
    api, service, bus, store = bundle

    created = api.create_finding(
        request(
            method="POST",
            body={
                "title": "Stored XSS in comments",
                "vector": STRONG_VECTOR,
                "description": "Unescaped markdown",
            },
        )
    )
    finding_id = str(created.payload["data"]["finding"]["id"])

    opened = api.update_finding(
        request(
            method="PUT",
            body={"id": finding_id, "action": "transition", "state": "open"},
        )
    )
    assert opened.payload["data"]["finding"]["lifecycle_state"] == "open"
    confirmed = api.update_finding(
        request(
            method="PUT",
            body={"id": finding_id, "action": "transition", "state": "confirmed"},
        )
    )
    assert confirmed.payload["data"]["finding"]["lifecycle_state"] == "confirmed"
    remediation = api.update_finding(
        request(
            method="PUT",
            body={
                "id": finding_id,
                "action": "remediation",
                "due": "2026-12-01",
                "notes": "Sanitize markup",
            },
        )
    )
    assert remediation.payload["data"]["finding"]["remediation_due"] == "2026-12-01"
    fixing = api.update_finding(
        request(
            method="PUT",
            body={"id": finding_id, "action": "transition", "state": "remediating"},
        )
    )
    assert fixing.payload["data"]["finding"]["lifecycle_state"] == "remediating"
    retesting = api.update_finding(
        request(
            method="PUT",
            body={"id": finding_id, "action": "transition", "state": "retest"},
        )
    )
    assert retesting.payload["data"]["finding"]["lifecycle_state"] == "retest"
    passed = api.update_finding(
        request(
            method="PUT",
            body={"id": finding_id, "action": "retest", "verdict": "pass", "note": "ok"},
        )
    )
    assert passed.payload["data"]["finding"]["lifecycle_state"] == "closed"
    assert passed.payload["data"]["finding"]["retest_count"] == 1

    listed = api.list_findings(request(query={"severity": "critical", "state": "closed"}))
    assert listed.payload["data"]["total"] == 1
    assert store.retest_count() == 1
    assert len(service.history(finding_id)) == 1
    assert [event.kind for event in bus.published] == [
        EventKind.FINDING_CREATED,
        EventKind.FINDING_SCORED,
        EventKind.FINDING_RETESTED,
    ]


def test_severity_counts_are_stable_after_updates(
    bundle: Bundle,
) -> None:
    api, _, store = bundle[0], bundle[1], bundle[3]
    api.create_finding(request(method="POST", body={"title": "A", "vector": STRONG_VECTOR}))
    api.create_finding(request(method="POST", body={"title": "B", "vector": WEAK_VECTOR}))
    assert store.severity_counts()["critical"] == 1
    assert store.severity_counts()["none"] == 1
    finding = next(item for item in store.all() if item.severity is Severity.CRITICAL)
    finding.vector = CvssV4Vector.parse(WEAK_VECTOR)
    api.update_finding(request(method="PUT", body={"id": finding.id, "action": "score"}))
    assert store.severity_counts()["none"] == 2
    assert store.severity_counts()["critical"] == 0
    assert Severity.NONE is Severity.from_score(0.0)
