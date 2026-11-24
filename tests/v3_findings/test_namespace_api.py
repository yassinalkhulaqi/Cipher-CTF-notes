"""Tests for the findings API namespace, routes, pagination, and ETags."""

from __future__ import annotations

import pytest

from redscribe.v3.api import V3Error
from redscribe.v3.api.router import V3Router
from redscribe.v3.findings.routes import FindingRoutes
from redscribe.v3.findings.service import FindingService
from redscribe.v3.namespaces import namespace_names
from redscribe.v3.namespaces.findings import handlers, register, reset_default_routes

VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def router() -> V3Router:
    """Build a router with the findings namespace installed."""
    reset_default_routes()
    instance = V3Router()
    register(instance)
    return instance


def create(router_instance: V3Router, title: str = "Finding") -> dict[str, object]:
    """Create a finding through the API."""
    response = router_instance.dispatch(
        "findings", "create", {"title": title, "vector": VECTOR, "tags": ["web"]}
    )
    finding = response["finding"]
    assert isinstance(finding, dict)
    return finding


def test_register_adds_all_actions() -> None:
    """Registration is additive and exposes a stable action set."""
    instance = router()
    assert instance.namespaces() == ("findings",)
    assert instance.size() == len(handlers()) == 22
    assert "findings" in namespace_names()
    paths = [route["path"] for route in instance.manifest()["routes"]]
    assert "/api/v3/findings/create" in paths
    assert "/api/v3/findings/score_preview" in paths
    with pytest.raises(V3Error):
        register(instance)


def test_create_get_update_and_detail() -> None:
    """CRUD routes round-trip immutable finding snapshots."""
    instance = router()
    finding = create(instance, "Broken access control")
    ref = str(finding["ref"])
    fetched = instance.dispatch("findings", "get", {"ref": ref})["finding"]
    assert fetched == finding
    updated = instance.dispatch(
        "findings", "update", {"ref": ref, "title": "Renamed", "tags": ["web", "api"]}
    )["finding"]
    assert isinstance(updated, dict)
    assert updated["title"] == "Renamed"
    detail = instance.dispatch("findings", "detail", {"ref": ref})
    assert detail["finding"]["title"] == "Renamed"
    assert detail["lifecycle"]["actions"] == ["confirm"]
    assert detail["score"]["final"] == 9.3
    assert detail["mappings"]["cwes"] == []


def test_create_is_idempotent() -> None:
    """Repeating an idempotency key does not create a second finding."""
    instance = router()
    body = {"title": "Idempotent finding"}
    first = instance.dispatch("findings", "create", body, {"Idempotency-Key": "key-1"})
    second = instance.dispatch("findings", "create", body, {"Idempotency-Key": "key-1"})
    assert first["finding"] == second["finding"]
    assert second["replayed"] is True
    assert instance.dispatch("findings", "summary")["total"] == 1


def test_score_routes_and_preview() -> None:
    """Live scoring previews and stored scoring use the same calculator."""
    instance = router()
    finding = create(instance)
    ref = str(finding["ref"])
    preview = instance.dispatch("findings", "score_preview", {"vector": VECTOR})
    assert preview["final"] == 9.3
    assert preview["severity"] == "critical"
    assert instance.dispatch("findings", "validate_vector", {"vector": VECTOR})["valid"] is True
    stored = instance.dispatch("findings", "score", {"ref": ref, "vector": VECTOR})
    assert stored["finding"]["score"] == 9.3
    bands = instance.dispatch("findings", "severity_bands")
    assert [band["value"] for band in bands["bands"]] == [
        "none",
        "low",
        "medium",
        "high",
        "critical",
    ]


def test_list_pagination_cursor_and_etag() -> None:
    """Finding lists paginate with opaque cursors and strong ETags."""
    instance = router()
    for index in range(5):
        create(instance, f"Finding {index}")
    first = instance.dispatch("findings", "list", {"size": 2})
    assert len(first["items"]) == 2
    assert first["page"]["total"] == 5
    assert first["page"]["has_next"] is True
    assert first["next_cursor"]
    second = instance.dispatch("findings", "list", {"size": 2, "cursor": first["next_cursor"]})
    assert len(second["items"]) == 2
    assert second["page"]["page"] == 2
    assert {item["ref"] for item in first["items"]}.isdisjoint(
        {item["ref"] for item in second["items"]}
    )
    not_modified = instance.dispatch(
        "findings", "list", {"size": 2}, {"If-None-Match": first["etag"]}
    )
    assert not_modified["not_modified"] is True
    assert not_modified["items"] == []


def test_list_filters_and_cursor_tampering() -> None:
    """Filters are hash-bound to cursors and tampered cursors are rejected."""
    instance = router()
    create(instance, "SQL injection")
    create(instance, "Cross-site scripting")
    filtered = instance.dispatch("findings", "list", {"query": "sql", "size": 1})
    assert filtered["page"]["total"] == 1
    assert filtered["filter_hash"]
    with pytest.raises(V3Error):
        instance.dispatch("findings", "list", {"cursor": "not-a-cursor"})


def test_remediation_retest_and_transition_routes() -> None:
    """Remediation, retest, and lifecycle routes compose end to end."""
    instance = router()
    ref = str(create(instance)["ref"])
    added = instance.dispatch(
        "findings", "remediation_add", {"ref": ref, "lines": "Patch the endpoint"}
    )
    assert added["remediation"]["total"] == 1
    task_id = added["remediation"]["tasks"][0]["task_id"]
    updated = instance.dispatch(
        "findings",
        "remediation_update",
        {"ref": ref, "task_id": task_id, "status": "done"},
    )
    assert updated["remediation"]["complete"] is True
    instance.dispatch("findings", "transition", {"ref": ref, "action": "confirm"})
    instance.dispatch("findings", "transition", {"ref": ref, "action": "remediate"})
    retest = instance.dispatch(
        "findings",
        "retest",
        {"ref": ref, "verdict": "pass", "tested_by": "tester", "proof_refs": ["evidence:e1"]},
    )
    assert retest["retest"]["verdict"] == "pass"
    instance.dispatch("findings", "transition", {"ref": ref, "action": "retest"})
    closed = instance.dispatch("findings", "transition", {"ref": ref, "action": "pass"})
    assert closed["finding"]["state"] == "closed"
    actions = instance.dispatch("findings", "actions", {"ref": ref})
    assert "reopen" in actions["actions"]
    assert any(edge["action"] == "reopen" for edge in actions["graph"]["closed"])


def test_proof_and_duplicate_routes() -> None:
    """Proof and duplicate routes return validated, serializable data."""
    instance = router()
    first = str(create(instance, "SQL injection login")["ref"])
    second = str(create(instance, "SQL injection login")["ref"])
    proof = instance.dispatch(
        "findings",
        "proof_add",
        {
            "ref": first,
            "block_id": "p1",
            "target": "evidence:log-1",
            "excerpt": "stack trace excerpt",
            "role": "supporting",
        },
    )
    assert proof["proof"]["verified"] is True
    report = instance.dispatch("findings", "proof_report", {"ref": first})
    assert report["proof"]["integrity"] is True
    duplicates = instance.dispatch("findings", "duplicates", {"ref": first, "threshold": 0.5})
    assert duplicates["count"] >= 1
    linked = instance.dispatch(
        "findings", "mark_duplicate", {"ref": second, "canonical": first, "note": "Same root cause"}
    )
    assert linked["finding"]["duplicate_of"] == first


def test_cwe_routes_and_error_translation() -> None:
    """Catalog routes work offline and domain errors map to V3 errors."""
    instance = router()
    catalog = instance.dispatch("findings", "cwe_catalog", {"query": "sql"})
    assert any(entry["cwe_id"] == "CWE-89" for entry in catalog["entries"])
    resolved = instance.dispatch("findings", "cwe_lookup", {"cwe_id": "cwe-89"})
    assert resolved["resolution"]["known"] is True
    with pytest.raises(Exception) as error:
        instance.dispatch("findings", "get", {"ref": "finding:missing"})
    assert getattr(error.value, "code", None) is not None
    with pytest.raises(V3Error):
        instance.dispatch("findings", "create", {})
    with pytest.raises(V3Error):
        instance.dispatch("findings", "score_preview", {"vector": "CVSS:3.1/AV:N"})


def test_standalone_routes_and_default_bundle_reset() -> None:
    """The namespace uses a shared handler bundle that tests can reset."""
    routes = FindingRoutes(FindingService())
    assert len(routes.handlers()) == 22
    assert routes.summary({}, {})["total"] == 0
    old = reset_default_routes()
    assert isinstance(old, FindingRoutes)
    assert len(handlers()) == 22
