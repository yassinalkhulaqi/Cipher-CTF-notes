"""Tests for the release smoke suite."""

from __future__ import annotations

from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.release.models import RELEASE_ACTIONS
from redscribe.v3.release.smoke import _isolated_router, run_smoke, smoke_check_ids


def test_smoke_suite_is_clean() -> None:
    report = run_smoke()
    assert report.ok is True
    assert report.failed_count == 0
    assert len(report.checks) >= 20


def test_smoke_check_ids_are_unique_and_stable() -> None:
    first = smoke_check_ids()
    second = smoke_check_ids()
    assert first == second
    assert len(first) == len(set(first))


def test_isolated_router_has_system_and_release_routes() -> None:
    router = _isolated_router()
    assert router.get("system", "health") is not None
    for action in RELEASE_ACTIONS:
        assert router.get("release", action) is not None
    assert "system" in router.namespaces()
    assert "release" in router.namespaces()


def test_smoke_accepts_prepopulated_router() -> None:
    router = V3Router()
    register_system_routes(router)
    report = run_smoke(router)
    assert report.ok is True
    spec = router.get("release", "manifest")
    assert spec is not None
    assert spec.public is True


def test_smoke_handles_router_without_release_routes() -> None:
    router = V3Router()
    register_system_routes(router)
    report = run_smoke(router)
    assert report.ok is True
    assert all(router.get("release", action) is not None for action in RELEASE_ACTIONS)


def test_smoke_report_markdown_lists_every_check() -> None:
    report = run_smoke()
    rendered = report.markdown()
    for check in report.checks:
        assert f"`{check.check_id}`" in rendered
    assert "| Check | Severity | Result | Expected |" in rendered


def test_smoke_check_severities_are_declared() -> None:
    report = run_smoke()
    severities = {check.severity.value for check in report.checks}
    assert severities.issubset({"blocker", "major", "minor", "info"})
    assert "blocker" in severities
