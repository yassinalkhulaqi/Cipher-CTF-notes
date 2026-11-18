from __future__ import annotations

from typing import Any

import pytest

from redscribe.v2.engagements.models import (
    Activity,
    ActivityAction,
    Asset,
    AssetKind,
    AssetStatus,
    Confidence,
    Credential,
    CredentialKind,
    CredentialStatus,
    Criticality,
    Engagement,
    EngagementKind,
    EngagementStatus,
    Finding,
    FindingEvent,
    FindingStatus,
    ScopeAction,
    ScopeRule,
    ScopeRuleKind,
    ScopeStatus,
    Service,
    ServiceStatus,
    Severity,
    Target,
    TargetKind,
    TargetStatus,
)
from redscribe.v2.engagements.services import EngagementService


def _merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    payload = dict(defaults)
    payload.update(overrides)
    return payload


@pytest.fixture
def service() -> EngagementService:
    return EngagementService(actor="tester")


@pytest.fixture
def engagement(service: EngagementService) -> dict[str, Any]:
    return service.create_engagement(
        {
            "name": "Alpha Engagement",
            "key": "alpha-engagement",
            "client": "Example Corp",
            "owner": "tester",
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
            "tags": ["alpha", "web"],
        }
    )


@pytest.fixture
def engagement_factory():
    def build(**overrides: Any) -> Engagement:
        defaults: dict[str, Any] = {
            "id": 1,
            "key": "test-engagement",
            "name": "Test Engagement",
            "client": "Example Corp",
            "description": "A validation fixture",
            "owner": "tester",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "tags": ["demo"],
            "kind": EngagementKind.PENTEST,
            "status": EngagementStatus.PLANNING,
        }
        return Engagement(**_merge(defaults, overrides))

    return build


@pytest.fixture
def target_factory():
    def build(**overrides: Any) -> Target:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "value": "app.example.test",
            "name": "Application",
            "kind": TargetKind.DOMAIN,
            "status": TargetStatus.CONFIRMED,
            "scope_status": ScopeStatus.IN_SCOPE,
            "criticality": Criticality.HIGH,
        }
        return Target(**_merge(defaults, overrides))

    return build


@pytest.fixture
def asset_factory():
    def build(**overrides: Any) -> Asset:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "target_id": 1,
            "name": "web-01",
            "kind": AssetKind.SERVER,
            "identifier": "10.0.0.10",
            "status": AssetStatus.ASSESSED,
            "criticality": Criticality.HIGH,
        }
        return Asset(**_merge(defaults, overrides))

    return build


@pytest.fixture
def service_factory():
    def build(**overrides: Any) -> Service:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "target_id": 1,
            "asset_id": 1,
            "name": "https",
            "port": 443,
            "protocol": "tcp",
            "product": "nginx",
            "version": "1.25",
            "status": ServiceStatus.VERIFIED,
        }
        return Service(**_merge(defaults, overrides))

    return build


@pytest.fixture
def credential_factory():
    def build(**overrides: Any) -> Credential:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "target_id": 1,
            "username": "admin",
            "secret_ref": "vault://eng/app",
            "kind": CredentialKind.PASSWORD,
            "status": CredentialStatus.VALID,
        }
        return Credential(**_merge(defaults, overrides))

    return build


@pytest.fixture
def finding_factory():
    def build(**overrides: Any) -> Finding:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "target_id": 1,
            "title": "SQL injection in login",
            "summary": "The login form passes user input to SQL.",
            "severity": Severity.HIGH,
            "confidence": Confidence.CONFIRMED,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "cvss_score": 9.8,
            "cwe": "CWE-89",
            "cwes": ["CWE-89"],
            "cves": ["CVE-2024-0001"],
            "status": FindingStatus.OPEN,
            "owner": "tester",
            "impact": "Authentication can be bypassed.",
            "remediation": "Use parameterized queries.",
            "reproduction_steps": "Submit a quoted payload.",
            "references": ["https://owasp.org"],
            "tags": ["web", "sqli"],
            "created_at": "2026-01-05T10:00:00+00:00",
            "updated_at": "2026-01-06T10:00:00+00:00",
        }
        return Finding(**_merge(defaults, overrides))

    return build


@pytest.fixture
def scope_rule_factory():
    def build(**overrides: Any) -> ScopeRule:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "kind": ScopeRuleKind.DOMAIN,
            "value": "example.test",
            "action": ScopeAction.INCLUDE,
            "notes": "Primary domain",
        }
        return ScopeRule(**_merge(defaults, overrides))

    return build


@pytest.fixture
def activity_factory():
    def build(**overrides: Any) -> Activity:
        defaults: dict[str, Any] = {
            "id": 1,
            "engagement_id": 1,
            "entity_type": "finding",
            "entity_id": 1,
            "action": ActivityAction.UPDATED,
            "summary": "Updated finding",
            "actor": "tester",
            "created_at": "2026-01-06T10:00:00+00:00",
        }
        return Activity(**_merge(defaults, overrides))

    return build


@pytest.fixture
def finding_event_factory():
    def build(**overrides: Any) -> FindingEvent:
        defaults: dict[str, Any] = {
            "at": "2026-01-06T10:00:00+00:00",
            "actor": "tester",
            "action": "verify",
            "from_status": "open",
            "to_status": "verified",
            "note": "Reproduced",
        }
        return FindingEvent(**_merge(defaults, overrides))

    return build
