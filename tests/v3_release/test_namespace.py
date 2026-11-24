"""Tests for the release namespace registration and dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.namespaces import has_namespace, namespace_names
from redscribe.v3.namespaces.release import register
from redscribe.v3.release.models import RELEASE_ACTIONS


def _namespace_source() -> str:
    lines = ["def register(router):"]
    lines.extend(f'    router.add("release", "{action}", handler)' for action in RELEASE_ACTIONS)
    return "\n".join(lines)


def _router() -> V3Router:
    router = V3Router()
    register(router)
    return router


def test_namespace_is_discoverable() -> None:
    assert "release" in namespace_names()
    assert has_namespace("release") is True


def test_register_adds_every_action() -> None:
    router = _router()
    assert router.size() == len(RELEASE_ACTIONS)
    assert router.namespaces() == ("release",)
    for action in RELEASE_ACTIONS:
        spec = router.get("release", action)
        assert spec is not None
        assert spec.path == f"/api/v3/release/{action}"


def test_register_rejects_duplicate_actions() -> None:
    router = _router()
    with pytest.raises(V3Error) as caught:
        register(router)
    assert caught.value.code is V3ErrorCode.CONFLICT


def test_manifest_route() -> None:
    router = _router()
    data = router.dispatch("release", "manifest")
    assert data["namespace"] == "release"
    assert data["offline_only"] is True
    assert data["executes_user_code"] is False
    assert len(data["actions"]) == len(RELEASE_ACTIONS)


def test_golden_route_lists_scenarios() -> None:
    router = _router()
    data = router.dispatch("release", "golden")
    assert data["ok"] is True
    assert len(data["scenarios"]) == 4
    assert data["catalogue"]["phase_count"] == 7


def test_golden_route_runs_one_scenario() -> None:
    router = _router()
    data = router.dispatch("release", "golden", {"name": "capture-to-merge"})
    assert len(data["scenarios"]) == 1
    assert data["scenarios"][0]["name"] == "capture-to-merge"


def test_smoke_route() -> None:
    router = _router()
    data = router.dispatch("release", "smoke")
    assert data["ok"] is True
    assert data["failed"] == 0
    assert data["total"] >= 20


def test_gates_route_is_static_catalogue() -> None:
    router = _router()
    data = router.dispatch("release", "gates")
    assert data["offline_only"] is True
    assert data["executes_user_code"] is False
    assert len(data["gates"]) == 10


def test_gate_audit_route_without_inputs() -> None:
    router = _router()
    data = router.dispatch("release", "gate_audit", {})
    assert data["ok"] is True
    assert len(data["gates"]) == 10
    statuses = {gate["status"] for gate in data["gates"]}
    assert "warn" in statuses


def test_gate_audit_route_with_sources() -> None:
    router = _router()
    source = _namespace_source()
    body = {
        "sources": {"namespaces/release.py": source},
        "pyproject": "dependencies = []",
        "manifest": '["release-polish-v3.test.ts"]',
        "docs": "## Quickstart\n## Golden paths\n## Gates\nREADME.md\nCHANGELOG.md",
        "css": {"release.css": "color: var(--v3-text);"},
        "components": {"Panel.tsx": 'data-surface="release" aria-label="Release"'},
    }
    data = router.dispatch("release", "gate_audit", body)
    assert data["ok"] is True


def test_docs_route() -> None:
    router = _router()
    data = router.dispatch("release", "docs")
    assert len(data["sections"]) == 13
    assert data["manifest"]["gate_count"] == 10
    assert data["proposals"]["README.md"].startswith("# RedScribe")
    assert "rendered" not in data


def test_docs_route_can_render_markdown() -> None:
    router = _router()
    data = router.dispatch("release", "docs", {"rendered": True})
    assert "# RedScribe V3 Release Guide" in data["rendered"]


def test_changelog_route() -> None:
    router = _router()
    data = router.dispatch("release", "changelog")
    assert data["version"] == "3.0.0"
    assert "### Added" in data["rendered"]
    assert any(entry["reference"] == "B14" for entry in data["entries"])


def test_migration_notes_route() -> None:
    router = _router()
    data = router.dispatch("release", "migration_notes")
    assert len(data["notes"]) >= 3
    assert "# V3 migration notes" in data["rendered"]


def test_readiness_route_requires_gate_evidence() -> None:
    router = _router()
    data = router.dispatch("release", "readiness", {})
    assert data["verdict"] == "hold"
    assert data["checks"]["golden_paths"] is True
    assert data["checks"]["smoke_suite"] is True
    assert data["checks"]["hardening_gates"] is False


def test_readiness_route_with_gate_evidence() -> None:
    router = _router()
    body = {
        "gates_evaluated": True,
        "sources": {"namespaces/release.py": _namespace_source()},
        "pyproject": "dependencies = []",
        "manifest": '["release-polish-v3.test.ts"]',
        "docs": "## Quickstart\n## Golden paths\n## Gates\nREADME.md\nCHANGELOG.md",
        "css": {"release.css": "color: var(--v3-text);"},
        "components": {"Panel.tsx": 'data-x="a" aria-label="b"'},
    }
    data = router.dispatch("release", "readiness", body)
    assert data["verdict"] == "ship"
    assert data["ready"] is True
    assert data["evidence"]["scenarios"] == 4


def test_onboarding_route() -> None:
    router = _router()
    data = router.dispatch("release", "onboarding")
    assert len(data["steps"]) == 5
    assert data["required"] == 4
    assert len(data["empty_states"]) == 5
    assert data["steps"][0]["control"] == "welcome-card"


def test_showcase_route() -> None:
    router = _router()
    data = router.dispatch("release", "showcase")
    assert len(data["entries"]) == 12
    assert len(data["icons"]) == 12
    assert "finding" in data["kind_colors"]


def test_polish_route() -> None:
    router = _router()
    data = router.dispatch("release", "polish")
    assert len(data["checks"]) >= 12
    assert len(data["animations"]) == 5
    assert len(data["breakpoints"]) == 3
    assert data["showcase_count"] == 12


def test_release_routes_accept_headers_without_effect() -> None:
    router: V3Router = _router()
    headers: Mapping[str, str] = {"X-Request-ID": "req_test"}
    first: dict[str, Any] = router.dispatch("release", "manifest", {}, headers)
    second: dict[str, Any] = router.dispatch("release", "manifest", {})
    assert first == second
