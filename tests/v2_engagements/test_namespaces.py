from __future__ import annotations

from typing import Any

import pytest

from redscribe.ui.web.v2.contracts import V2Error, V2ErrorCode
from redscribe.ui.web.v2.namespaces.engagements import (
    EngagementNamespace,
    configure,
    register,
    route_names,
)
from redscribe.v2.engagements.errors import EngagementErrorCode
from redscribe.v2.engagements.services import EngagementService

EXPECTED_ROUTES = {
    "engagements.list",
    "engagements.get",
    "engagements.create",
    "engagements.update",
    "engagements.transition",
    "engagements.delete",
    "engagements.dashboard",
    "engagements.portfolio",
    "engagements.workflows",
    "engagements.options",
    "engagements.activity",
    "engagements.seed_demo",
    "scope.list",
    "scope.add",
    "scope.remove",
    "scope.evaluate",
    "scope.import",
    "targets.list",
    "targets.get",
    "targets.create",
    "targets.update",
    "targets.transition",
    "targets.scope_transition",
    "targets.remove",
    "targets.coverage",
    "assets.list",
    "assets.get",
    "assets.create",
    "assets.update",
    "assets.remove",
    "services.list",
    "services.get",
    "services.create",
    "services.update",
    "services.transition",
    "services.remove",
    "credentials.list",
    "credentials.get",
    "credentials.create",
    "credentials.update",
    "credentials.rotate",
    "credentials.transition",
    "credentials.remove",
    "findings.list",
    "findings.get",
    "findings.create",
    "findings.update",
    "findings.transition",
    "findings.duplicate",
    "findings.link_cluster",
    "findings.duplicates",
    "findings.clusters",
    "findings.remove",
}

MUTATING_ROUTES = {
    "engagements.create",
    "engagements.update",
    "engagements.transition",
    "engagements.delete",
    "engagements.seed_demo",
    "scope.add",
    "scope.remove",
    "scope.import",
    "targets.create",
    "targets.update",
    "targets.transition",
    "targets.scope_transition",
    "targets.remove",
    "assets.create",
    "assets.update",
    "assets.remove",
    "services.create",
    "services.update",
    "services.transition",
    "services.remove",
    "credentials.create",
    "credentials.update",
    "credentials.rotate",
    "credentials.transition",
    "credentials.remove",
    "findings.create",
    "findings.update",
    "findings.transition",
    "findings.duplicate",
    "findings.link_cluster",
    "findings.remove",
}


class RecordingRegistry:
    def __init__(self) -> None:
        self.routes: dict[str, dict[str, Any]] = {}

    def _register(
        self,
        name: str,
        handler: Any,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None:
        self.routes[name] = {
            "handler": handler,
            "description": description,
            "required": required,
            "optional": optional,
            "mutating": mutating,
            "entity_type": entity_type,
        }


@pytest.fixture
def namespace(service: EngagementService) -> EngagementNamespace:
    return EngagementNamespace(service)


def _target(namespace: EngagementNamespace, engagement_id: int) -> dict[str, Any]:
    result = namespace.targets_create({"engagement_id": engagement_id, "value": "app.example.test"})
    return result.data


def _finding(
    namespace: EngagementNamespace,
    engagement_id: int,
    target_id: int,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "engagement_id": engagement_id,
        "target_id": target_id,
        "title": "SQL injection in login",
        "summary": "The login form passes user input to SQL.",
        "severity": "high",
        "confidence": "confirmed",
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "reproduction_steps": "Submit a quoted payload.",
        "tags": ["web", "sqli"],
    }
    payload.update(overrides)
    result = namespace.findings_create(payload)
    return result.data


def test_route_inventory_is_stable() -> None:
    specs = EngagementNamespace().specs()
    names = [spec.name for spec in specs]
    assert set(names) == EXPECTED_ROUTES
    assert len(names) == len(EXPECTED_ROUTES)
    assert set(route_names()) == EXPECTED_ROUTES
    assert all(spec.description for spec in specs)
    assert all(isinstance(spec.required, tuple) for spec in specs)
    assert all(isinstance(spec.optional, tuple) for spec in specs)
    assert {spec.name for spec in specs if spec.mutating} == MUTATING_ROUTES


def test_register_adds_all_routes_with_metadata(service: EngagementService) -> None:
    registry = RecordingRegistry()
    returned = register(registry, service)
    assert isinstance(returned, EngagementNamespace)
    assert set(registry.routes) == EXPECTED_ROUTES
    assert registry.routes["engagements.create"]["mutating"] is True
    assert registry.routes["engagements.create"]["entity_type"] == "engagement"
    assert registry.routes["engagements.list"]["required"] == ()
    assert registry.routes["engagements.get"]["required"] == ("id",)
    result = registry.routes["engagements.create"]["handler"]({"name": "Registered"})
    assert result.status == 201
    assert result.data["name"] == "Registered"
    assert service.store.engagements.count() == 1


def test_register_requires_registration_hook(service: EngagementService) -> None:
    with pytest.raises(TypeError, match="registration hook"):
        EngagementNamespace(service).register(object())


def test_configure_controls_bare_register(service: EngagementService) -> None:
    configured = configure(service)
    try:
        registry = RecordingRegistry()
        assert register(registry) is configured
        result = registry.routes["engagements.create"]["handler"]({"name": "Configured"})
        assert result.data["name"] == "Configured"
    finally:
        configure()


def test_engagement_handlers_cover_crud_and_dashboard_views(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    listed = namespace.engagements_list({"query": "alpha", "limit": 10})
    assert [item["id"] for item in listed.data] == [engagement_id]
    assert listed.page is not None
    assert listed.page.total == 1
    assert listed.etag is not None
    assert listed.etag.startswith("sha256:")
    detail = namespace.engagements_get({"id": engagement_id})
    assert detail.data["key"] == "alpha-engagement"
    updated = namespace.engagements_update({"id": engagement_id, "name": "Renamed"})
    assert updated.data["name"] == "Renamed"
    transitioned = namespace.engagements_transition({"id": engagement_id, "action": "activate"})
    assert transitioned.data["status"] == "active"
    dashboard = namespace.engagements_dashboard({"id": engagement_id})
    assert dashboard.data["engagement"]["id"] == engagement_id
    portfolio = namespace.engagements_portfolio({"limit": 10})
    assert portfolio.data["page"]["total"] == 1
    workflows = namespace.engagements_workflows({})
    assert workflows.data["workflows"]
    options = namespace.engagements_options({})
    assert options.data["severity"] == ["info", "low", "medium", "high", "critical"]
    activity = namespace.engagements_activity({"id": engagement_id})
    assert isinstance(activity.data, list)


def test_engagement_delete_handler_removes_engagement(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    result = namespace.engagements_delete({"id": engagement["id"]})
    assert result.data["deleted"] is True
    assert namespace.service.store.engagements.count() == 0


def test_seed_demo_handler_uses_empty_service(namespace: EngagementNamespace) -> None:
    result = namespace.engagements_seed_demo({})
    assert result.data["created"] is True
    assert result.data["engagement"]["key"]
    second = namespace.engagements_seed_demo({})
    assert second.data["created"] is False


def test_scope_handlers_manage_rules(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    created = namespace.scope_add(
        {
            "engagement_id": engagement_id,
            "kind": "domain",
            "value": "example.test",
            "action": "include",
        }
    )
    assert created.status == 201
    listed = namespace.scope_list({"engagement_id": engagement_id})
    assert [item["id"] for item in listed.data] == [created.data["id"]]
    evaluated = namespace.scope_evaluate(
        {"engagement_id": engagement_id, "value": "api.example.test"}
    )
    assert evaluated.data["decision"] == "included"
    assert evaluated.data["in_scope"] is True
    imported = namespace.scope_import(
        {
            "engagement_id": engagement_id,
            "rules": [
                {"kind": "domain", "value": "example.test", "action": "include"},
                {"kind": "keyword", "value": "admin", "action": "exclude"},
            ],
        }
    )
    assert imported.data["total"] == 1
    assert imported.data["skipped"] == 1
    removed = namespace.scope_remove({"engagement_id": engagement_id, "id": created.data["id"]})
    assert removed.data["id"] == created.data["id"]
    assert namespace.service.store.scope_rules.get(created.data["id"]) is None


def test_target_handlers_cover_crud_transitions_and_coverage(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(namespace, engagement_id)
    target_id = target["id"]
    listed = namespace.targets_list({"engagement_id": engagement_id, "query": "app"})
    assert [item["id"] for item in listed.data] == [target_id]
    detail = namespace.targets_get({"id": target_id})
    assert detail.data["value"] == "app.example.test"
    updated = namespace.targets_update({"id": target_id, "name": "Renamed"})
    assert updated.data["name"] == "Renamed"
    confirmed = namespace.targets_transition({"id": target_id, "action": "confirm"})
    assert confirmed.data["status"] == "confirmed"
    scoped = namespace.targets_scope_transition({"id": target_id, "action": "accept"})
    assert scoped.data["scope_status"] == "in_scope"
    coverage = namespace.targets_coverage({"engagement_id": engagement_id})
    assert coverage.data["engagement_id"] == engagement_id
    removed = namespace.targets_remove({"id": target_id})
    assert removed.data["id"] == target_id
    assert namespace.service.store.targets.get(target_id) is None


def test_inventory_handlers_cover_assets_services_and_credentials(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(namespace, engagement_id)
    target_id = target["id"]
    asset = namespace.assets_create(
        {
            "engagement_id": engagement_id,
            "target_id": target_id,
            "name": "web-01",
            "kind": "server",
            "identifier": "10.0.0.10",
            "criticality": "high",
        }
    )
    assert asset.status == 201
    asset_id = asset.data["id"]
    assets = namespace.assets_list({"engagement_id": engagement_id, "query": "10.0.0"})
    assert [item["id"] for item in assets.data] == [asset_id]
    assert namespace.assets_get({"id": asset_id}).data["name"] == "web-01"
    updated_asset = namespace.assets_update({"id": asset_id, "status": "assessed"})
    assert updated_asset.data["status"] == "assessed"
    service = namespace.services_create(
        {
            "engagement_id": engagement_id,
            "target_id": target_id,
            "asset_id": asset_id,
            "name": "https",
            "port": 443,
            "protocol": "tcp",
        }
    )
    assert service.status == 201
    service_id = service.data["id"]
    verified = namespace.services_transition({"id": service_id, "action": "verify"})
    assert verified.data["status"] == "verified"
    services = namespace.services_list({"engagement_id": engagement_id, "port": 443})
    assert [item["id"] for item in services.data] == [service_id]
    assert namespace.services_get({"id": service_id}).data["port"] == 443
    credential = namespace.credentials_create(
        {
            "engagement_id": engagement_id,
            "target_id": target_id,
            "username": "admin",
            "secret_ref": "vault://eng/app",
        }
    )
    assert credential.status == 201
    credential_id = credential.data["id"]
    assert namespace.credentials_get({"id": credential_id}).data["id"] == credential_id
    validated = namespace.credentials_transition({"id": credential_id, "action": "validate"})
    assert validated.data["status"] == "valid"
    rotated = namespace.credentials_rotate({"id": credential_id})
    assert rotated.data["status"] == "rotated"
    credentials = namespace.credentials_list({"engagement_id": engagement_id, "status": "rotated"})
    assert [item["id"] for item in credentials.data] == [credential_id]
    assert namespace.services_remove({"id": service_id}).data["id"] == service_id
    assert namespace.assets_remove({"id": asset_id}).data["id"] == asset_id
    assert namespace.credentials_remove({"id": credential_id}).data["id"] == credential_id
    assert namespace.service.store.services.get(service_id) is None
    assert namespace.service.store.assets.get(asset_id) is None
    assert namespace.service.store.credentials.get(credential_id) is None


def test_finding_handlers_cover_crud_workflow_and_duplicates(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    target = _target(namespace, engagement_id)
    target_id = target["id"]
    finding = _finding(namespace, engagement_id, target_id)
    finding_id = finding["id"]
    listed = namespace.findings_list(
        {"engagement_id": engagement_id, "severity": "high", "tag": "web"}
    )
    assert [item["id"] for item in listed.data] == [finding_id]
    assert namespace.findings_get({"id": finding_id}).data["title"] == finding["title"]
    updated = namespace.findings_update({"id": finding_id, "title": "Updated issue"})
    assert updated.data["title"] == "Updated issue"
    submitted = namespace.findings_transition({"id": finding_id, "action": "submit"})
    assert submitted.data["status"] == "open"
    duplicate = _finding(namespace, engagement_id, target_id, title="SQL injection in signin")
    duplicate_id = duplicate["id"]
    marked = namespace.findings_duplicate({"id": duplicate_id, "canonical_id": finding_id})
    assert marked.data["duplicate_of"] == finding_id
    candidates = namespace.findings_duplicates({"id": finding_id, "threshold": 90})
    assert isinstance(candidates.data["candidates"], list)
    clusters = namespace.findings_clusters({"engagement_id": engagement_id, "threshold": 90})
    assert isinstance(clusters.data["clusters"], list)
    third = _finding(namespace, engagement_id, target_id, title="SQL injection in login form")
    linked = namespace.findings_link_cluster(
        {"canonical_id": finding_id, "duplicate_ids": [third["id"]]}
    )
    assert linked.data["canonical_id"] == finding_id
    assert linked.data["skipped"] == []
    assert namespace.findings_remove({"id": duplicate_id}).data["id"] == duplicate_id
    assert namespace.service.store.findings.get(duplicate_id) is None


def test_invalid_payloads_raise_stable_v2_errors(
    namespace: EngagementNamespace, engagement: dict[str, Any]
) -> None:
    engagement_id = engagement["id"]
    with pytest.raises(V2Error) as missing:
        namespace.engagements_get({})
    assert missing.value.code == V2ErrorCode.INVALID_TYPE.value
    assert missing.value.details["field"] == "id"
    with pytest.raises(V2Error) as limit:
        namespace.engagements_list({"limit": 201})
    assert limit.value.code == V2ErrorCode.INVALID_REQUEST.value
    assert limit.value.details["field"] == "limit"
    with pytest.raises(V2Error) as rules:
        namespace.scope_import({"engagement_id": engagement_id, "rules": "bad"})
    assert rules.value.code == V2ErrorCode.INVALID_TYPE.value
    with pytest.raises(V2Error) as duplicate_ids:
        namespace.findings_link_cluster({"canonical_id": 1, "duplicate_ids": [1, True]})
    assert duplicate_ids.value.code == V2ErrorCode.INVALID_TYPE.value
    with pytest.raises(V2Error) as retested:
        namespace.findings_transition({"id": 1, "action": "close", "retested": "yes"})
    assert retested.value.code == V2ErrorCode.INVALID_TYPE.value


def test_engagement_errors_are_translated_to_v2_errors(
    namespace: EngagementNamespace,
) -> None:
    registry = RecordingRegistry()
    register(registry, namespace.service)
    with pytest.raises(V2Error) as missing:
        registry.routes["engagements.get"]["handler"]({"id": 9999})
    assert missing.value.status == 404
    assert missing.value.code == EngagementErrorCode.NOT_FOUND.value
    with pytest.raises(V2Error) as invalid:
        registry.routes["engagements.create"]["handler"]({"name": ""})
    assert invalid.value.status == 400
    assert invalid.value.code == EngagementErrorCode.VALIDATION.value
    assert invalid.value.details["issues"]
