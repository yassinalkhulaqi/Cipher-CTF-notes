"""Tests for the reports V3 namespace registration and routes."""

from __future__ import annotations

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import V3Router, default_router
from redscribe.v3.namespaces.reports import register


def payload() -> dict[str, object]:
    return {
        "key": "ns-report",
        "title": "Namespace Report",
        "client": "Acme",
        "findings": [
            {
                "value": "f-1",
                "title": "Broken access control",
                "severity": "high",
                "status": "open",
                "evidence": [{"value": "e-1", "title": "Proof", "content": "mail a@b.com"}],
            }
        ],
        "sections": [{"key": "intro", "title": "Introduction", "body": "Assessed acme.com."}],
        "redactions": [{"name": "email", "pattern": r"\b\S+@\S+\b"}],
        "options": {"cover": True, "toc": True},
    }


@pytest.fixture
def router() -> V3Router:
    instance = V3Router()
    register(instance)
    return instance


def test_register_adds_only_reports_routes(router: V3Router) -> None:
    assert router.namespaces() == ("reports",)
    actions = {route.action for route in router.routes()}
    assert actions == {
        "health",
        "themes",
        "formats",
        "design",
        "preview",
        "paginate",
        "render",
        "manifest",
        "redact",
        "validate",
    }
    assert router.size() == 10
    manifest = router.manifest()
    assert "/api/v3/reports/design" in [route["path"] for route in manifest["routes"]]


def test_health_themes_and_formats(router: V3Router) -> None:
    health = router.dispatch("reports", "health")
    assert health["status"] == "ok"
    assert health["capability"] == "reports"
    assert health["enabled"] is True
    assert len(health["formats"]) == 4
    themes = router.dispatch("reports", "themes")
    assert themes["default"] == "client"
    assert len(themes["themes"]) == 4
    formats = router.dispatch("reports", "formats")
    assert formats["extensions"]["print"] == "css"
    assert "application/json" in formats["mime_types"]["json"]


def test_design_preview_paginate_manifest(router: V3Router) -> None:
    body = payload()
    designed = router.dispatch("reports", "design", body)
    assert designed["document"]["key"] == "ns-report"
    assert len(designed["outputs"]) == 4
    preview = router.dispatch("reports", "preview", body)
    assert preview["design_digest"] == designed["manifest"]["design_digest"]
    assert preview["redaction"]["total_matches"] >= 1
    assert preview["selection"]["included"] == ["broken-access-control"]
    assert preview["toc"]
    plan = router.dispatch("reports", "paginate", body)
    assert plan["plan"]["total_pages"] >= 1
    assert plan["entries"]
    manifest = router.dispatch("reports", "manifest", body)
    assert manifest["manifest"]["design_digest"] == preview["design_digest"]
    assert manifest["sections"] >= 3


def test_render_and_redact_routes(router: V3Router) -> None:
    body = payload()
    rendered = router.dispatch("reports", "render", {**body, "format": "html"})
    assert rendered["format"] == "html"
    assert "<!doctype html>" in rendered["content"]
    assert "[EMAIL]" in rendered["content"] or "a@b.com" not in rendered["content"]
    redact = router.dispatch("reports", "redact", body)
    assert redact["preview"]["total_matches"] >= 1
    assert redact["applied"]
    validated = router.dispatch("reports", "validate", body)
    assert validated["valid"] is True
    assert validated["rules"]["includes"] == 0


def test_invalid_format_and_duplicate_registration(router: V3Router) -> None:
    with pytest.raises(V3Error):
        router.dispatch("reports", "render", {**payload(), "format": "pdf"})
    with pytest.raises(V3Error):
        register(router)
    with pytest.raises(V3Error):
        router.dispatch("reports", "missing")


def test_dynamic_discovery_installs_reports() -> None:
    router = V3Router()
    installed = router.install_namespaces()
    assert installed >= 2
    assert "reports" in router.namespaces()
    assert "system" in router.namespaces()
    assert router.install_namespaces() == 0
    health = default_router().dispatch("reports", "health")
    assert health["status"] == "ok"
