from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from redscribe.v2.engagements.coverage import (
    COVERAGE_WEIGHTS,
    CoverageLevel,
    assess_target,
    compute_coverage,
    coverage_gap_summary,
    coverage_label,
    coverage_level,
    coverage_percent,
    criticality_distribution,
    out_of_scope_count,
    priority_ranking,
)
from redscribe.v2.engagements.models import (
    Confidence,
    Criticality,
    EngagementStatus,
    FindingStatus,
    ScopeStatus,
    Severity,
    severity_index,
)
from redscribe.v2.engagements.rollups import (
    AGE_BUCKETS,
    CONFIDENCE_MULTIPLIERS,
    SEVERITY_WEIGHTS,
    age_bucket,
    age_buckets,
    confidence_counts,
    engagement_rollup,
    finding_risk,
    merge_status_counts,
    portfolio_rollup,
    risk_band,
    risk_score,
    severity_counts,
    severity_matrix,
    sort_findings,
    status_counts,
    top_findings,
    widget_cards,
)


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0.0, "missing"),
        (0.34, "missing"),
        (0.35, "partial"),
        (0.59, "partial"),
        (0.6, "good"),
        (0.84, "good"),
        (0.85, "complete"),
        (1.0, "complete"),
    ],
)
def test_coverage_level_bands(score: float, level: str) -> None:
    assert coverage_level(score) == level
    assert isinstance(CoverageLevel(), str)


def test_coverage_weights_sum_to_one() -> None:
    assert sum(COVERAGE_WEIGHTS.values()) == pytest.approx(1.0)


def test_assess_target_full_coverage(
    target_factory: Any, asset_factory: Any, service_factory: Any, finding_factory: Any
) -> None:
    target = target_factory(scope_status=ScopeStatus.IN_SCOPE)
    assets = [asset_factory(id=1, target_id=1), asset_factory(id=2, target_id=1)]
    services = [service_factory(id=1, target_id=1), service_factory(id=2, target_id=1)]
    findings = [
        finding_factory(id=1, target_id=1, status=FindingStatus.VERIFIED),
        finding_factory(id=2, target_id=1),
    ]
    result = assess_target(target, assets, services, findings)
    assert result.score == pytest.approx(1.0)
    assert result.level == "complete"
    assert result.asset_count == 2
    assert result.service_count == 2
    assert result.finding_count == 2
    assert result.verified_count == 1
    assert result.evidence_count == 2
    assert result.gaps == []
    payload = result.as_dict()
    assert payload["target_id"] == 1
    assert payload["score"] == 1.0


def test_assess_target_reports_gaps(target_factory: Any) -> None:
    target = target_factory(scope_status=ScopeStatus.PENDING)
    result = assess_target(target, [], [], [])
    assert result.level == "missing"
    assert "target is not confirmed in scope" in result.gaps
    assert "no assets identified" in result.gaps
    assert "no services enumerated" in result.gaps
    assert "no findings recorded" in result.gaps
    assert result.score == pytest.approx(0.05)


def test_assess_target_includes_services_linked_by_asset(
    target_factory: Any, asset_factory: Any, service_factory: Any, finding_factory: Any
) -> None:
    target = target_factory(scope_status=ScopeStatus.IN_SCOPE)
    asset = asset_factory(id=7, target_id=1)
    service = service_factory(id=1, target_id=0, asset_id=7)
    finding = finding_factory(id=1, target_id=1, reproduction_steps="", references=[])
    result = assess_target(target, [asset], [service], [finding])
    assert result.service_count == 1
    assert result.evidence_count == 0
    assert "some findings lack evidence" not in result.gaps


def test_assess_target_flags_partial_evidence(target_factory: Any, finding_factory: Any) -> None:
    target = target_factory(scope_status=ScopeStatus.IN_SCOPE)
    with_evidence = finding_factory(id=1, target_id=1, reproduction_steps="steps")
    without_evidence = finding_factory(id=2, target_id=1, reproduction_steps="", references=[])
    result = assess_target(target, [], [], [with_evidence, without_evidence])
    assert result.evidence_count == 1
    assert "some findings lack evidence" in result.gaps


def test_compute_coverage_filters_by_engagement(
    target_factory: Any, asset_factory: Any, service_factory: Any, finding_factory: Any
) -> None:
    targets = [target_factory(id=1), target_factory(id=2), target_factory(id=3, engagement_id=2)]
    assets = [asset_factory(id=1, target_id=1)]
    services = [service_factory(id=1, target_id=1)]
    findings = [finding_factory(id=1, target_id=1)]
    report = compute_coverage(1, targets, assets, services, findings)
    assert report.engagement_id == 1
    assert [detail.target_id for detail in report.targets] == [1, 2]
    assert set(report.uncovered) == {2}
    assert set(report.partial) == {2}
    payload = report.as_dict()
    assert payload["score"] == round(report.score, 4)
    assert payload["priority"] == report.priority


def test_compute_coverage_handles_empty_engagement() -> None:
    report = compute_coverage(9, [], [], [], [])
    assert report.score == 0.0
    assert report.level == "missing"
    assert report.targets == []
    assert report.priority == []
    assert coverage_percent(report) == 0
    assert coverage_label(report) == "0% missing"


def test_priority_ranking_uses_criticality_then_low_coverage(target_factory: Any) -> None:
    low = target_factory(id=1, criticality=Criticality.LOW)
    high = target_factory(id=2, criticality=Criticality.HIGH)
    critical = target_factory(id=3, criticality=Criticality.CRITICAL)
    from redscribe.v2.engagements.coverage import TargetCoverage

    coverage = {
        1: TargetCoverage(1, "low", "in_scope", "low", 0.9, "complete", 0, 0, 0, 0, 0),
        2: TargetCoverage(2, "high", "in_scope", "high", 0.2, "missing", 0, 0, 0, 0, 0),
        3: TargetCoverage(3, "critical", "in_scope", "critical", 0.7, "good", 0, 0, 0, 0, 0),
    }
    assert priority_ranking([low, high, critical], coverage) == [3, 2, 1]


def test_counting_helpers_for_targets(target_factory: Any) -> None:
    targets = [
        target_factory(id=1, scope_status=ScopeStatus.IN_SCOPE, criticality=Criticality.HIGH),
        target_factory(id=2, scope_status=ScopeStatus.OUT_OF_SCOPE, criticality=Criticality.HIGH),
        target_factory(id=3, scope_status=ScopeStatus.WAIVED, criticality=Criticality.LOW),
    ]
    assert out_of_scope_count(targets) == 2
    distribution = criticality_distribution(targets)
    assert distribution["high"] == 2
    assert distribution["low"] == 1
    assert distribution["critical"] == 0


def test_coverage_gap_summary_counts_and_sorts(
    target_factory: Any, asset_factory: Any, service_factory: Any, finding_factory: Any
) -> None:
    first = assess_target(target_factory(id=1), [], [], [])
    second = assess_target(target_factory(id=2), [], [service_factory(id=1, target_id=2)], [])
    from redscribe.v2.engagements.coverage import CoverageReport

    report = CoverageReport(
        engagement_id=1,
        score=0.2,
        level="missing",
        targets=[first, second],
        uncovered=[1, 2],
        partial=[1, 2],
        priority=[1, 2],
        gaps=[],
    )
    summary = coverage_gap_summary(report)
    assert summary[0]["gap"] == "no assets identified"
    assert summary[0]["count"] == 2
    assert all({"gap", "count"} == set(item) for item in summary)


@pytest.mark.parametrize(
    ("score", "band"),
    [(0.0, "none"), (0.1, "low"), (15.0, "medium"), (35.0, "high"), (60.0, "critical")],
)
def test_risk_bands(score: float, band: str) -> None:
    assert risk_band(score) == band


def test_risk_weights_and_multipliers_are_complete() -> None:
    assert set(SEVERITY_WEIGHTS) == set(Severity)
    assert set(CONFIDENCE_MULTIPLIERS) == set(Confidence)
    assert set(AGE_BUCKETS) == {"today", "week", "month", "older"}


def test_finding_risk_ignores_closed_and_duplicate(finding_factory: Any) -> None:
    active = finding_factory(severity=Severity.HIGH, confidence=Confidence.CONFIRMED, cvss_score=0)
    assert finding_risk(active) == 7.0
    assert finding_risk(finding_factory(severity=Severity.CRITICAL, cvss_score=9.9)) == 15.0
    assert finding_risk(finding_factory(status=FindingStatus.DUPLICATE)) == 0.0
    assert finding_risk(finding_factory(status=FindingStatus.CLOSED)) == 0.0
    assert finding_risk(finding_factory(confidence=Confidence.LOW)) < finding_risk(
        finding_factory(confidence=Confidence.HIGH)
    )


def test_risk_score_uses_diminishing_returns_and_cap(finding_factory: Any) -> None:
    findings = [finding_factory(id=n + 1) for n in range(20)]
    score = risk_score(findings)
    assert 0.0 < score <= 100.0
    assert risk_score(findings, cap=5.0) == 5.0
    assert risk_score([finding_factory(status=FindingStatus.CLOSED)]) == 0.0


def test_severity_status_and_confidence_counts(finding_factory: Any) -> None:
    findings = [
        finding_factory(
            id=1, severity=Severity.HIGH, status=FindingStatus.OPEN, confidence=Confidence.HIGH
        ),
        finding_factory(
            id=2, severity=Severity.HIGH, status=FindingStatus.VERIFIED, confidence=Confidence.LOW
        ),
        finding_factory(
            id=3, severity=Severity.LOW, status=FindingStatus.CLOSED, confidence=Confidence.HIGH
        ),
        finding_factory(
            id=4,
            severity=Severity.LOW,
            status=FindingStatus.REMEDIATED,
            confidence=Confidence.MEDIUM,
        ),
    ]
    severities = severity_counts(findings)
    assert [item.severity for item in severities] == [item.value for item in Severity]
    high = severities[severity_index(Severity.HIGH)]
    assert (high.total, high.open, high.verified, high.closed) == (2, 1, 1, 0)
    assert status_counts(findings)["verified"] == 1
    assert confidence_counts(findings)["high"] == 2


@pytest.mark.parametrize(
    ("created", "expected"),
    [
        ("2026-01-15T10:00:00Z", "today"),
        ("2026-01-12T10:00:00Z", "week"),
        ("2025-12-20T10:00:00Z", "month"),
        ("2025-01-01T10:00:00Z", "older"),
        ("not-a-date", "older"),
    ],
)
def test_age_bucket(created: str, expected: str) -> None:
    assert age_bucket(created, today=date(2026, 1, 15)) == expected


def test_age_buckets_counts_all_findings(finding_factory: Any) -> None:
    findings = [
        finding_factory(id=1, created_at="2026-01-15T10:00:00Z"),
        finding_factory(id=2, created_at="2026-01-12T10:00:00Z"),
        finding_factory(id=3, created_at="2025-01-01T10:00:00Z"),
    ]
    buckets = age_buckets(findings, today=date(2026, 1, 15))
    assert buckets["today"] == 1
    assert buckets["week"] == 1
    assert buckets["older"] == 1
    assert sum(buckets.values()) == 3


def test_sort_and_top_findings(finding_factory: Any) -> None:
    low = finding_factory(id=1, cvss_score=2.0)
    high = finding_factory(id=2, cvss_score=9.8, title="Critical issue")
    medium = finding_factory(id=3, cvss_score=5.0)
    ordered = sort_findings([low, medium, high])
    assert [item.id for item in ordered] == [2, 3, 1]
    assert sort_findings([low, medium, high], limit=1) == [high]
    top = top_findings([low, medium, high], limit=2)
    assert [row["id"] for row in top] == [2, 3]
    assert top[0]["severity"] == "high"
    assert top[0]["risk"] > 0


def test_engagement_rollup_counts_and_serializes(
    engagement_factory: Any, target_factory: Any, finding_factory: Any
) -> None:
    engagement = engagement_factory()
    findings = [
        finding_factory(id=1, status=FindingStatus.OPEN),
        finding_factory(id=2, status=FindingStatus.VERIFIED),
        finding_factory(id=3, status=FindingStatus.DUPLICATE),
        finding_factory(id=4, status=FindingStatus.CLOSED),
    ]
    rollup = engagement_rollup(
        engagement,
        targets=[target_factory()],
        assets=[object()],
        services=[object(), object()],
        credentials=[object()],
        findings=findings,
        coverage_score=0.75,
        today=date(2026, 1, 15),
    )
    assert rollup.target_count == 1
    assert rollup.asset_count == 1
    assert rollup.service_count == 2
    assert rollup.credential_count == 1
    assert rollup.finding_count == 4
    assert rollup.open_finding_count == 2
    assert rollup.verified_count == 1
    assert rollup.duplicate_count == 1
    assert rollup.coverage_score == 0.75
    payload = rollup.as_dict()
    assert payload["risk_band"] in {"none", "low", "medium", "high", "critical"}
    assert len(payload["severity"]) == 5
    assert len(payload["top_findings"]) <= 5


def test_portfolio_rollup_aggregates_engagements(
    engagement_factory: Any, finding_factory: Any
) -> None:
    first = engagement_factory(id=1, key="first", status=EngagementStatus.ACTIVE)
    second = engagement_factory(id=2, key="second", status=EngagementStatus.CLOSED)
    first_rollup = engagement_rollup(
        first,
        findings=[finding_factory(id=1, severity=Severity.CRITICAL, engagement_id=1)],
    )
    second_rollup = engagement_rollup(
        second,
        findings=[finding_factory(id=2, severity=Severity.LOW, engagement_id=2)],
    )
    portfolio = portfolio_rollup([first, second], [second_rollup, first_rollup])
    assert portfolio.engagement_count == 2
    assert portfolio.active_count == 1
    assert portfolio.finding_count == 2
    assert portfolio.critical_count == 1
    assert [item.engagement_id for item in portfolio.engagements] == [1, 2]
    payload = portfolio.as_dict()
    assert payload["risk_score"] == round(portfolio.risk_score, 2)


def test_widget_cards_and_severity_matrix(engagement_factory: Any, finding_factory: Any) -> None:
    rollup = engagement_rollup(
        engagement_factory(),
        findings=[finding_factory(severity=Severity.CRITICAL, confidence=Confidence.CONFIRMED)],
    )
    cards = widget_cards(rollup)
    assert [card["label"] for card in cards] == ["Targets", "Findings", "Open", "Critical", "Risk"]
    assert cards[3]["tone"] == "danger"
    matrix = severity_matrix([finding_factory(severity=Severity.HIGH, confidence=Confidence.LOW)])
    assert matrix["high"]["low"] == 1
    assert matrix["critical"]["confirmed"] == 0


def test_merge_status_counts() -> None:
    assert merge_status_counts({"open": 2, "draft": 1}, {"open": 3, "closed": 4}) == {
        "open": 5,
        "draft": 1,
        "closed": 4,
    }
    assert merge_status_counts({}, {}) == {}
