"""Tests for release data contracts and report rendering."""

from __future__ import annotations

import pytest

from redscribe.v3.release.models import (
    RELEASE_ACTIONS,
    RELEASE_NAMESPACE,
    RELEASE_VERSION,
    AnimationAudit,
    CheckSeverity,
    DocBundle,
    DocSection,
    EmptyStateSpec,
    GateDefinition,
    GateReport,
    GateResult,
    GateStatus,
    OnboardingSpec,
    PolishCheck,
    ReleasePhase,
    ScenarioResult,
    ScenarioStep,
    ShowcaseEntry,
    SmokeCheck,
    SmokeReport,
    phase_values,
)


def test_release_constants() -> None:
    assert RELEASE_VERSION == "3.0.0"
    assert RELEASE_NAMESPACE == "release"
    assert RELEASE_ACTIONS[0] == "manifest"
    assert "gate_audit" in RELEASE_ACTIONS
    assert len(RELEASE_ACTIONS) == len(set(RELEASE_ACTIONS))


def test_phase_ordering_and_labels() -> None:
    assert list(phase_values()) == [
        "capture",
        "finding",
        "evidence",
        "report",
        "export",
        "import",
        "merge",
    ]
    assert ReleasePhase.CAPTURE.position == 0
    assert ReleasePhase.MERGE.position == 6
    assert ReleasePhase.EVIDENCE.label == "Evidence"
    assert ReleasePhase.ordered()[-1] is ReleasePhase.MERGE


def test_severity_and_gate_status_ranks() -> None:
    assert CheckSeverity.BLOCKER.rank > CheckSeverity.INFO.rank
    assert GateStatus.PASS.ok is True
    assert GateStatus.WARN.ok is True
    assert GateStatus.FAIL.ok is False


def test_scenario_result_aggregation() -> None:
    steps = (
        ScenarioStep(ReleasePhase.CAPTURE, "a", "detail", "1", "1", True),
        ScenarioStep(ReleasePhase.CAPTURE, "b", "detail", "2", "3", False),
        ScenarioStep(ReleasePhase.MERGE, "c", "detail", "4", "4", True),
    )
    result = ScenarioResult(name="sample", description="sample run", steps=steps)
    assert result.passed_count == 2
    assert result.failed_count == 1
    assert result.ok is False
    assert result.phases == ("capture", "merge")
    payload = result.as_dict()
    assert payload["steps"][1]["actual"] == "3"
    assert payload["ok"] is False


def test_empty_scenario_result_is_not_ok() -> None:
    result = ScenarioResult(name="empty", description="no steps", steps=())
    assert result.ok is False
    assert result.phases == ()


def test_smoke_report_markdown_and_failures() -> None:
    checks = (
        SmokeCheck("a", "First", CheckSeverity.BLOCKER, True, "ok", "ok"),
        SmokeCheck("b", "Second", CheckSeverity.MAJOR, False, "1", "2", "mismatch"),
    )
    report = SmokeReport(checks=checks)
    assert report.ok is False
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert report.failures()[0].check_id == "b"
    rendered = report.markdown()
    assert "| Check | Severity | Result | Expected |" in rendered
    assert "`b`" in rendered
    payload = report.as_dict()
    assert payload["checks"][1]["detail"] == "mismatch"


def test_smoke_report_requires_checks() -> None:
    assert SmokeReport(checks=()).ok is False


def test_gate_report_markdown_and_status_counts() -> None:
    results = (
        GateResult("g1", "First", GateStatus.PASS, "fine"),
        GateResult("g2", "Second", GateStatus.WARN, "review", ("evidence",)),
    )
    report = GateReport(results=results)
    assert report.ok is True
    assert report.as_dict()["warnings"] == 1
    assert report.as_dict()["failed"] == 0
    assert "| Gate | Status | Detail |" in report.markdown()
    failing = GateResult("g3", "Third", GateStatus.FAIL, "bad")
    failed_report = GateReport(results=(*results, failing))
    assert failed_report.ok is False
    assert failed_report.failures == (failing,)


def test_gate_definition_as_dict() -> None:
    definition = GateDefinition("g", "Gate", "blocker")
    assert definition.as_dict() == {"id": "g", "title": "Gate", "severity": "blocker"}


def test_doc_bundle_render() -> None:
    bundle = DocBundle(
        title="Guide",
        version="3.0.0",
        sections=(DocSection("intro", "Intro", "Body text."),),
    )
    rendered = bundle.render()
    assert rendered.startswith("# Guide\n")
    assert "Release: `3.0.0`" in rendered
    assert "## Intro" in rendered
    assert "Body text." in rendered
    assert bundle.as_dict()["sections"][0]["id"] == "intro"


@pytest.mark.parametrize(
    "contract",
    [
        OnboardingSpec("s", "T", "D", "control", "hint"),
        EmptyStateSpec("notes", "T", "D", "Action", "route"),
        PolishCheck("p", "Area", "Label", "Detail"),
        AnimationAudit("surface", "opacity", "--v3-motion-fast", True),
        ShowcaseEntry("--v3-surface", "Label", "note", "panel"),
    ],
)
def test_polish_contracts_are_serialisable(contract: object) -> None:
    payload = contract.as_dict()  # type: ignore[attr-defined]
    assert isinstance(payload, dict)


def test_onboarding_default_required() -> None:
    spec = OnboardingSpec("s", "T", "D", "control", "hint")
    assert spec.required is True
    assert spec.as_dict()["required"] is True
