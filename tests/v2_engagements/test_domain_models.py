from __future__ import annotations

from typing import Any

from redscribe.v2.engagements.models import (
    ActivityAction,
    Confidence,
    Criticality,
    EngagementKind,
    EngagementStatus,
    Finding,
    FindingEvent,
    FindingStatus,
    ScopeAction,
    ScopeStatus,
    Severity,
    StrEnum,
    TargetKind,
    TargetStatus,
    severity_index,
)


def test_strenum_labels_are_readable() -> None:
    assert EngagementStatus.PLANNING.label == "Planning"
    assert TargetStatus.OUT_OF_SERVICE.label == "Out Of Service"
    assert TargetKind.IP_ADDRESS.label == "Ip Address"
    assert FindingStatus.ACCEPTED_RISK.label == "Accepted Risk"
    assert isinstance(Severity.HIGH, str)
    assert Severity.HIGH == "high"


def test_severity_helpers_expose_representative_scores() -> None:
    assert Severity.INFO.numeric_score() == 0.0
    assert Severity.LOW.numeric_score() == 3.9
    assert Severity.MEDIUM.numeric_score() == 6.9
    assert Severity.HIGH.numeric_score() == 8.9
    assert Severity.CRITICAL.numeric_score() == 10.0
    assert severity_index(Severity.INFO) == 0
    assert severity_index(Severity.CRITICAL) == 4


def test_engagement_snapshot_roundtrip_is_stable(engagement_factory: Any) -> None:
    engagement = engagement_factory()
    payload = engagement.as_dict()
    assert payload["kind"] == "pentest"
    assert payload["status"] == "planning"
    assert payload["tags"] == ["demo"]
    restored = type(engagement).from_dict(payload)
    assert restored.as_dict() == payload
    assert restored.display_name == "Test Engagement"


def test_engagement_display_name_falls_back_to_key_and_id(engagement_factory: Any) -> None:
    assert engagement_factory(name="", key="alpha").display_name == "alpha"
    assert engagement_factory(name="", key="", id=42).display_name == "Engagement 42"


def test_target_snapshot_preserves_scope_and_criticality(target_factory: Any) -> None:
    target = target_factory(scope_status=ScopeStatus.WAIVED, criticality=Criticality.CRITICAL)
    payload = target.as_dict()
    assert payload["scope_status"] == "waived"
    assert payload["criticality"] == "critical"
    assert type(target).from_dict(payload).as_dict() == payload
    assert target.display_name == "Application"


def test_asset_snapshot_preserves_identifiers(asset_factory: Any) -> None:
    asset = asset_factory(owner="ops", notes="internally managed")
    payload = asset.as_dict()
    assert payload["identifier"] == "10.0.0.10"
    assert payload["owner"] == "ops"
    assert type(asset).from_dict(payload).as_dict() == payload


def test_service_endpoint_is_derived(service_factory: Any) -> None:
    service = service_factory()
    assert service.endpoint == "https:443/tcp"
    assert service_factory(port=0, name="ssh").endpoint == "ssh"
    payload = service.as_dict()
    assert type(service).from_dict(payload).as_dict() == payload


def test_credential_secret_is_masked_only_by_safe_dict(credential_factory: Any) -> None:
    credential = credential_factory()
    assert credential.as_dict()["secret_ref"] == "vault://eng/app"
    masked = credential.safe_dict()
    assert masked["secret_ref"] == "***"
    assert type(credential).from_dict(credential.as_dict()).as_dict() == credential.as_dict()


def test_scope_rule_roundtrip(scope_rule_factory: Any) -> None:
    rule = scope_rule_factory(action=ScopeAction.EXCLUDE, kind="port", value="8080")
    payload = rule.as_dict()
    assert payload["action"] == "exclude"
    assert type(rule).from_dict(payload).as_dict() == payload


def test_activity_roundtrip(activity_factory: Any) -> None:
    activity = activity_factory(action=ActivityAction.TRANSITIONED)
    payload = activity.as_dict()
    assert payload["action"] == "transitioned"
    assert type(activity).from_dict(payload).as_dict() == payload


def test_finding_event_roundtrip(finding_event_factory: Any) -> None:
    event = finding_event_factory()
    payload = event.as_dict()
    assert payload["from_status"] == "open"
    assert payload["to_status"] == "verified"
    assert FindingEvent.from_dict(payload).as_dict() == payload


def test_finding_snapshot_preserves_all_editor_fields(
    finding_factory: Any, finding_event_factory: Any
) -> None:
    finding = finding_factory(
        transitions=[finding_event_factory()],
        cwes=["CWE-89", "CWE-20"],
        references=["https://example.test/report"],
        tags=["web"],
    )
    payload = finding.as_dict()
    assert payload["severity"] == "high"
    assert payload["confidence"] == "confirmed"
    assert payload["status"] == "open"
    assert payload["transitions"][0]["action"] == "verify"
    assert type(finding).from_dict(payload).as_dict() == payload


def test_finding_from_dict_ignores_malformed_values() -> None:
    restored = Finding.from_dict(
        {
            "id": "bad",
            "severity": Severity.HIGH.value,
            "confidence": 12,
            "status": None,
            "cvss_score": "9.8",
            "cwes": "CWE-89",
            "cves": [1, "CVE-2024-0001"],
            "transitions": [None, {"action": "verify"}],
            "tags": ["web", 4],
        }
    )
    assert restored.id == 0
    assert restored.severity is Severity.HIGH
    assert restored.confidence is Confidence.MEDIUM
    assert restored.status is FindingStatus.DRAFT
    assert restored.cvss_score == 0.0
    assert restored.cwes == []
    assert restored.cves == ["CVE-2024-0001"]
    assert restored.tags == ["web"]
    assert len(restored.transitions) == 1
    assert restored.transitions[0].action == "verify"


def test_finding_predicates_and_effective_score(finding_factory: Any) -> None:
    finding = finding_factory()
    assert finding.is_open is True
    assert finding.effective_score == 9.8
    assert finding_factory(cvss_score=0, severity=Severity.CRITICAL).effective_score == 10.0
    assert finding_factory(status=FindingStatus.CLOSED).is_open is False
    assert finding_factory(status=FindingStatus.DUPLICATE).is_open is False
    assert finding_factory(status=FindingStatus.ACCEPTED_RISK).is_open is True


def test_entity_base_contract_is_explicit() -> None:
    from redscribe.v2.engagements.models import Entity

    entity = Entity()
    try:
        entity.as_dict()
    except NotImplementedError:
        pass
    else:
        raise AssertionError("as_dict must be abstract")
    try:
        Entity.from_dict({})
    except NotImplementedError:
        pass
    else:
        raise AssertionError("from_dict must be abstract")


def test_enum_membership_uses_string_values() -> None:
    assert "active" in [item.value for item in EngagementStatus]
    assert "red_team" in [item.value for item in EngagementKind]
    assert "in_scope" in [item.value for item in ScopeStatus]
    assert [item.value for item in Severity] == ["info", "low", "medium", "high", "critical"]


def test_strenum_is_string_compatible() -> None:
    assert isinstance(StrEnum, type)
    assert Severity.CRITICAL.value == "critical"
    assert str(Severity.LOW.value).upper() == "LOW"
