from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from redscribe.v2.engagements.errors import EngagementError, EngagementErrorCode
from redscribe.v2.engagements.services import EngagementService, build_demo_service


def _target(service: EngagementService, engagement_id: int, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"value": "app.example.test", "name": "Application"}
    payload.update(overrides)
    return service.add_target(engagement_id, payload)


def _finding(service: EngagementService, engagement_id: int, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "SQL injection in login",
        "summary": "User input is concatenated into a SQL query.",
        "severity": "high",
        "confidence": "confirmed",
        "cwe": "CWE-89",
        "cves": ["CVE-2024-0001"],
        "tags": ["web", "sqli"],
        "reproduction_steps": "Submit a quoted username.",
        "impact": "Authentication can be bypassed.",
        "remediation": "Use parameterized queries.",
    }
    payload.update(overrides)
    cleaned = {key: value for key, value in payload.items() if value is not None}
    return service.create_finding(engagement_id, cleaned)


def test_create_engagement_derives_key_and_logs_activity(service: EngagementService) -> None:
    created = service.create_engagement({"name": "  Alpha Engagement  ", "owner": "tester"})
    assert created["key"] == "alpha-engagement"
    assert created["name"] == "Alpha Engagement"
    assert created["status"] == "planning"
    assert created["kind"] == "pentest"
    assert created["counts"]["targets"] == 0
    assert "activate" in created["allowed_actions"]
    assert len(service.activity(created["id"])) == 1


def test_create_engagement_rejects_missing_name(service: EngagementService) -> None:
    with pytest.raises(EngagementError) as excinfo:
        service.create_engagement({"key": "broken"})
    assert excinfo.value.code is EngagementErrorCode.VALIDATION
    assert excinfo.value.status == 400
    assert excinfo.value.details["issues"][0]["field"] == "name"


def test_create_engagement_rejects_duplicate_key(service: EngagementService) -> None:
    service.create_engagement({"name": "First", "key": "same-key"})
    with pytest.raises(EngagementError) as excinfo:
        service.create_engagement({"name": "Second", "key": "same-key"})
    assert excinfo.value.code is EngagementErrorCode.CONFLICT
    assert excinfo.value.status == 409
    assert excinfo.value.details["field"] == "key"


def test_create_engagement_rejects_inverted_dates(service: EngagementService) -> None:
    with pytest.raises(EngagementError) as excinfo:
        service.create_engagement(
            {"name": "Dated", "start_date": "2026-03-01", "end_date": "2026-02-01"}
        )
    assert excinfo.value.details["field"] == "end_date"


def test_update_engagement_applies_partial_changes(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    updated = service.update_engagement(
        engagement["id"], {"name": "Renamed", "owner": "new-owner", "tags": "web, api, web"}
    )
    assert updated["name"] == "Renamed"
    assert updated["owner"] == "new-owner"
    assert updated["tags"] == ["web", "api"]
    assert len(service.activity(engagement["id"])) == 2


def test_update_engagement_rejects_conflicting_key(service: EngagementService) -> None:
    first = service.create_engagement({"name": "First", "key": "first"})
    second = service.create_engagement({"name": "Second", "key": "second"})
    with pytest.raises(EngagementError) as excinfo:
        service.update_engagement(second["id"], {"key": "FIRST"})
    assert excinfo.value.code is EngagementErrorCode.CONFLICT
    assert first["key"] == "first"


def test_transition_engagement_enforces_guards_and_logs(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    active = service.transition_engagement(engagement["id"], "activate")
    assert active["status"] == "active"
    reporting = service.transition_engagement(engagement["id"], "report")
    assert reporting["status"] == "reporting"
    with pytest.raises(EngagementError) as excinfo:
        service.transition_engagement(engagement["id"], "close")
    assert excinfo.value.code is EngagementErrorCode.TRANSITION
    closed = service.transition_engagement(engagement["id"], "close", report_signed_off=True)
    assert closed["status"] == "closed"
    archived = service.transition_engagement(engagement["id"], "archive", note="done")
    assert archived["status"] == "archived"
    actions = [item["action"] for item in service.activity(engagement["id"])]
    assert "transitioned" in actions


def test_list_engagements_filters(service: EngagementService, engagement: dict[str, Any]) -> None:
    service.create_engagement(
        {
            "name": "Beta Engagement",
            "key": "beta",
            "status": "active",
            "kind": "lab",
            "client": "Other Client",
            "owner": "other",
        }
    )
    assert [item["key"] for item in service.list_engagements()] == ["alpha-engagement", "beta"]
    assert [item["key"] for item in service.list_engagements(status="active")] == ["beta"]
    assert [item["key"] for item in service.list_engagements(kind="lab")] == ["beta"]
    assert [item["key"] for item in service.list_engagements(owner="TESTER")] == [
        "alpha-engagement"
    ]
    assert [item["key"] for item in service.list_engagements(query="other client")] == ["beta"]
    assert service.list_engagements(query="nothing-matches") == []


def test_delete_engagement_removes_dependent_records(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    target = _target(service, engagement["id"])
    _finding(service, engagement["id"], target_id=target["id"])
    result = service.delete_engagement(engagement["id"])
    assert result == {"id": 1, "key": "alpha-engagement", "deleted": True}
    assert service.store.stats() == dict.fromkeys(service.store.repositories(), 0)


def test_not_found_errors_are_stable(service: EngagementService) -> None:
    with pytest.raises(EngagementError) as excinfo:
        service.engagement_detail(999)
    assert excinfo.value.code is EngagementErrorCode.NOT_FOUND
    assert excinfo.value.status == 404
    assert excinfo.value.details == {"entity": "engagement", "id": 999}


def test_scope_rules_evaluate_and_import(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    included = service.add_scope_rule(
        engagement_id, {"kind": "domain", "value": "example.test", "action": "include"}
    )
    excluded = service.add_scope_rule(
        engagement_id, {"kind": "keyword", "value": "admin", "action": "exclude"}
    )
    assert [rule["id"] for rule in service.list_scope_rules(engagement_id)] == [1, 2]
    evaluation = service.evaluate_scope(engagement_id, "admin.example.test")
    assert evaluation["decision"] == "excluded"
    assert evaluation["in_scope"] is False
    assert {item["id"] for item in evaluation["matched"]} == {included["id"], excluded["id"]}
    assert service.suggest_scope_status(engagement_id, "api.example.test").value == "in_scope"
    assert service.suggest_scope_status(engagement_id, "unknown.test").value == "pending"
    imported = service.import_scope_rules(
        engagement_id,
        [
            {"kind": "domain", "value": "example.test", "action": "include"},
            {"kind": "domain", "value": "new.test", "action": "include"},
        ],
    )
    assert imported["skipped"] == 1
    assert imported["total"] == 1
    service.remove_scope_rule(engagement_id, excluded["id"])
    assert [rule["id"] for rule in service.list_scope_rules(engagement_id)] == [1, 3]


def test_add_target_detects_kind_from_scope_and_value(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    service.add_scope_rule(engagement_id, {"value": "example.test", "action": "include"})
    domain = _target(service, engagement_id, value="app.example.test")
    ip = _target(service, engagement_id, value="10.0.0.5", scope_status="waived")
    assert domain["kind"] == "domain"
    assert domain["scope_status"] == "in_scope"
    assert ip["kind"] == "ip_address"
    assert ip["scope_status"] == "waived"
    assert [item["id"] for item in service.list_targets(engagement_id)] == [1, 2]
    assert [item["id"] for item in service.list_targets(engagement_id, scope_status="waived")] == [
        2
    ]
    assert [item["id"] for item in service.list_targets(engagement_id, query="APP.EXAMPLE")] == [1]


def test_add_target_rejects_duplicate_value(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    _target(service, engagement_id, value="dup.example.test")
    with pytest.raises(EngagementError) as excinfo:
        _target(service, engagement_id, value="DUP.EXAMPLE.TEST")
    assert excinfo.value.code is EngagementErrorCode.CONFLICT


def test_target_transitions_and_scope_review(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    target = _target(service, engagement["id"])
    confirmed = service.transition_target(target["id"], "confirm")
    assert confirmed["status"] == "confirmed"
    excluded = service.transition_target(target["id"], "exclude", reason="out of scope")
    assert excluded["status"] == "excluded"
    assert "out of scope" in excluded["notes"]
    restored = service.transition_target(target["id"], "restore")
    assert restored["status"] == "discovered"
    in_scope = service.transition_target_scope(target["id"], "accept")
    assert in_scope["scope_status"] == "in_scope"
    out_of_scope = service.transition_target_scope(target["id"], "exclude")
    assert out_of_scope["scope_status"] == "out_of_scope"
    waived = service.transition_target_scope(target["id"], "waive")
    assert waived["scope_status"] == "waived"
    with pytest.raises(EngagementError) as excinfo:
        service.transition_target_scope(target["id"], "accept")
    assert excinfo.value.code is EngagementErrorCode.TRANSITION


def test_update_and_remove_target_cascade(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(service, engagement_id)
    asset = service.add_asset(engagement_id, {"target_id": target["id"], "name": "web-01"})
    service.add_service(engagement_id, {"target_id": target["id"], "name": "https", "port": 443})
    service.add_credential(
        engagement_id, {"target_id": target["id"], "secret_ref": "vault://eng/web"}
    )
    updated = service.update_target(target["id"], {"name": "Renamed", "criticality": "critical"})
    assert updated["name"] == "Renamed"
    assert updated["criticality"] == "critical"
    service.remove_target(target["id"])
    assert service.store.assets.count() == 0
    assert service.store.services.count() == 0
    assert service.store.credentials.count() == 0
    assert asset["name"] == "web-01"


def test_asset_service_and_credential_workflows(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(service, engagement_id)
    asset = service.add_asset(
        engagement_id,
        {
            "target_id": target["id"],
            "name": "web-01",
            "kind": "server",
            "identifier": "10.0.0.10",
            "criticality": "high",
        },
    )
    assert asset["kind"] == "server"
    updated_asset = service.update_asset(asset["id"], {"status": "assessed"})
    assert updated_asset["status"] == "assessed"
    assert [item["id"] for item in service.list_assets(engagement_id, query="10.0.0")] == [
        asset["id"]
    ]
    added_service = service.add_service(
        engagement_id,
        {
            "target_id": target["id"],
            "asset_id": asset["id"],
            "name": "https",
            "port": 443,
            "protocol": "tcp",
        },
    )
    verified = service.transition_service(added_service["id"], "verify")
    assert verified["status"] == "verified"
    assert [
        item["id"]
        for item in service.list_services(engagement_id, target_id=target["id"], port=443)
    ] == [added_service["id"]]
    credential = service.add_credential(
        engagement_id,
        {"target_id": target["id"], "username": "admin", "secret_ref": "vault://eng/web"},
    )
    assert credential["secret_ref"] == "***"
    validated = service.transition_credential(credential["id"], "validate")
    assert validated["status"] == "valid"
    rotated = service.rotate_credential(credential["id"], secret_ref="vault://eng/web-v2")
    assert rotated["status"] == "rotated"
    assert rotated["secret_ref"] == "***"
    assert [item["id"] for item in service.list_credentials(engagement_id, kind="password")] == [
        credential["id"]
    ]
    service.remove_asset(asset["id"])
    assert service.store.assets.count() == 0
    assert service.store.services.get(added_service["id"]).asset_id == 0
    service.remove_service(added_service["id"])
    service.remove_credential(credential["id"])
    assert service.store.services.count() == 0
    assert service.store.credentials.count() == 0


def test_create_finding_derives_severity_from_cvss_and_validates_relations(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(service, engagement_id)
    finding = _finding(
        service,
        engagement_id,
        target_id=target["id"],
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        severity=None,
    )
    assert finding["severity"] == "critical"
    assert finding["cvss_score"] == pytest.approx(9.8, abs=0.1)
    assert finding["cvss"]["score"] == pytest.approx(9.8, abs=0.1)
    assert finding["target_name"] == "Application"
    assert finding["transitions"][0]["action"] == "created"
    with pytest.raises(EngagementError) as excinfo:
        _finding(service, engagement_id, target_id=999)
    assert excinfo.value.code is EngagementErrorCode.NOT_FOUND


def test_create_finding_requires_reproduction_for_verified_status(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    with pytest.raises(EngagementError) as excinfo:
        _finding(
            service,
            engagement["id"],
            status="verified",
            reproduction_steps="",
        )
    assert excinfo.value.details["issues"][0]["field"] == "reproduction_steps"


def test_finding_lifecycle_transitions_and_detail(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    finding = _finding(service, engagement_id)
    opened = service.transition_finding(finding["id"], "submit")
    assert opened["status"] == "open"
    verified = service.transition_finding(
        finding["id"], "verify", evidence="Screenshot of response"
    )
    assert verified["status"] == "verified"
    assert verified["reproduction_steps"] == "Submit a quoted username."
    remediated = service.transition_finding(finding["id"], "remediate", note="patched")
    assert remediated["status"] == "remediated"
    assert remediated["resolved_at"]
    closed = service.transition_finding(finding["id"], "close", retested=True)
    assert closed["status"] == "closed"
    assert closed["allowed_actions"] == ["reopen"]
    with pytest.raises(EngagementError) as excinfo:
        service.transition_finding(finding["id"], "verify")
    assert excinfo.value.code is EngagementErrorCode.TRANSITION


def test_update_finding_recomputes_cvss_and_fields(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    finding = _finding(service, engagement["id"])
    updated = service.update_finding(
        finding["id"],
        {
            "title": "Updated title",
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "cwe": "cwe20",
            "cves": ["cve-2024-4242"],
        },
    )
    assert updated["title"] == "Updated title"
    assert updated["severity"] == "critical"
    assert updated["cwe"] == "CWE-20"
    assert "CWE-20" in updated["cwes"]
    assert updated["cves"] == ["CVE-2024-4242"]


def test_duplicate_detection_and_canonical_linking(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    first = _finding(service, engagement_id)
    second = _finding(service, engagement_id, id=0)
    matches = service.find_duplicates_for(first["id"])
    assert [match["candidate_id"] for match in matches] == [second["id"]]
    assert service.suggest_duplicate(first["id"])["candidate_id"] == second["id"]
    assert service.finding_clusters(engagement_id)[0]["ids"] == [first["id"], second["id"]]
    linked = service.mark_finding_duplicate(second["id"], first["id"])
    assert linked["status"] == "duplicate"
    assert linked["duplicate_of"] == first["id"]
    assert linked["canonical_title"] == first["title"]
    service.remove_finding(first["id"])
    assert service.store.findings.get(second["id"]) is not None
    assert service.store.findings.get(second["id"]).duplicate_of == 0


def test_list_findings_filters_and_sorting(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(service, engagement_id)
    low = _finding(
        service,
        engagement_id,
        title="Low issue",
        severity="low",
        target_id=target["id"],
        tags=["api"],
    )
    high = _finding(
        service, engagement_id, title="High issue", severity="high", tags=["web"], owner="alice"
    )
    results = service.list_findings(engagement_id)
    assert [item["id"] for item in results] == [high["id"], low["id"]]
    assert [item["id"] for item in service.list_findings(engagement_id, severity="low")] == [
        low["id"]
    ]
    assert [item["id"] for item in service.list_findings(engagement_id, tag="web")] == [high["id"]]
    assert [
        item["id"] for item in service.list_findings(engagement_id, target_id=target["id"])
    ] == [low["id"]]
    assert [item["id"] for item in service.list_findings(engagement_id, owner="ALICE")] == [
        high["id"]
    ]
    assert [item["id"] for item in service.list_findings(engagement_id, query="HIGH ISSUE")] == [
        high["id"]
    ]


def test_create_finding_rejects_relation_from_another_target(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    first = _target(service, engagement_id, value="first.example.test")
    second = _target(service, engagement_id, value="second.example.test")
    asset = service.add_asset(engagement_id, {"target_id": first["id"], "name": "web-01"})
    with pytest.raises(EngagementError) as excinfo:
        _finding(service, engagement_id, target_id=second["id"], asset_id=asset["id"])
    assert excinfo.value.details["field"] == "asset_id"


def test_coverage_and_dashboard_payload(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(service, engagement_id, criticality="high", scope_status="in_scope")
    asset = service.add_asset(engagement_id, {"target_id": target["id"], "name": "web-01"})
    service.add_service(
        engagement_id,
        {"target_id": target["id"], "asset_id": asset["id"], "name": "https", "port": 443},
    )
    service.add_service(engagement_id, {"target_id": target["id"], "name": "http", "port": 80})
    finding = _finding(service, engagement_id, target_id=target["id"])
    service.transition_finding(finding["id"], "submit")
    coverage = service.coverage_report(engagement_id)
    assert coverage["engagement_id"] == engagement_id
    assert coverage["targets"][0]["asset_count"] == 1
    assert coverage["percent"] == round(coverage["score"] * 100)
    assert coverage["criticality_distribution"]["high"] == 1
    dashboard = service.dashboard(engagement_id, today=date(2026, 1, 15))
    assert dashboard["rollup"]["risk_band"] in {"none", "low", "medium", "high", "critical"}
    assert len(dashboard["cards"]) == 5
    assert dashboard["coverage"]["score"] == coverage["score"]
    assert dashboard["severity_matrix"]["high"]["confirmed"] == 1
    assert dashboard["age_buckets"]["today"] >= 1
    assert len(dashboard["recent_activity"]) <= 10
    assert dashboard["age_buckets"] == dashboard["rollup"]["age_buckets"]


def test_portfolio_workflows_options_and_seed(
    service: EngagementService, engagement: dict[str, Any]
) -> None:
    _finding(service, engagement["id"])
    portfolio = service.portfolio(today=date(2026, 1, 15))
    assert portfolio["engagement_count"] == 1
    assert portfolio["finding_count"] == 1
    assert portfolio["engagements"][0]["engagement_id"] == engagement["id"]
    workflows = service.workflows()
    assert [item["name"] for item in workflows] == [
        "engagement",
        "target",
        "scope",
        "finding",
        "service",
        "credential",
    ]
    options = service.status_options()
    assert options["severity"] == ["info", "low", "medium", "high", "critical"]
    assert "in_scope" in options["scope_status"]
    assert service.seed_demo() == {"created": False, "engagement": None}


def test_build_demo_service_is_preloaded() -> None:
    service = build_demo_service()
    assert service.store.engagements.count() == 1
    assert [item["key"] for item in service.list_engagements()] == ["demo-engagement"]
    assert service.dashboard(1)["rollup"]["finding_count"] == 1


def test_activity_limit(service: EngagementService, engagement: dict[str, Any]) -> None:
    for index in range(5):
        service.update_engagement(engagement["id"], {"name": f"Name {index}"})
    assert len(service.activity(engagement["id"], limit=2)) == 2
