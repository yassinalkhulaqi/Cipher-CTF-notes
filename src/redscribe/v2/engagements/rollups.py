"""Dashboard rollups and risk metrics for engagements."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from redscribe.v2.engagements.models import (
    SEVERITY_ORDER,
    Confidence,
    Engagement,
    Finding,
    FindingStatus,
    Severity,
    Target,
    severity_index,
)
from redscribe.v2.engagements.util import clamp, format_number

SEVERITY_WEIGHTS = {
    Severity.INFO: 0.0,
    Severity.LOW: 1.0,
    Severity.MEDIUM: 3.0,
    Severity.HIGH: 7.0,
    Severity.CRITICAL: 15.0,
}

CONFIDENCE_MULTIPLIERS = {
    Confidence.LOW: 0.4,
    Confidence.MEDIUM: 0.7,
    Confidence.HIGH: 0.9,
    Confidence.CONFIRMED: 1.0,
}

AGE_BUCKETS = ("today", "week", "month", "older")


@dataclass(slots=True)
class SeverityCount:
    severity: str
    total: int
    open: int
    verified: int
    closed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "total": self.total,
            "open": self.open,
            "verified": self.verified,
            "closed": self.closed,
        }


@dataclass(slots=True)
class EngagementRollup:
    """Aggregate statistics for a single engagement."""

    engagement_id: int
    name: str
    status: str
    kind: str
    target_count: int
    asset_count: int
    service_count: int
    credential_count: int
    finding_count: int
    open_finding_count: int
    verified_count: int
    duplicate_count: int
    risk_score: float
    risk_band: str
    coverage_score: float
    severity: list[SeverityCount] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)
    confidence_counts: dict[str, int] = field(default_factory=dict)
    top_findings: list[dict[str, Any]] = field(default_factory=list)
    age_buckets: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "engagement_id": self.engagement_id,
            "name": self.name,
            "status": self.status,
            "kind": self.kind,
            "target_count": self.target_count,
            "asset_count": self.asset_count,
            "service_count": self.service_count,
            "credential_count": self.credential_count,
            "finding_count": self.finding_count,
            "open_finding_count": self.open_finding_count,
            "verified_count": self.verified_count,
            "duplicate_count": self.duplicate_count,
            "risk_score": round(self.risk_score, 2),
            "risk_band": self.risk_band,
            "coverage_score": round(self.coverage_score, 4),
            "severity": [item.as_dict() for item in self.severity],
            "status_counts": dict(self.status_counts),
            "confidence_counts": dict(self.confidence_counts),
            "top_findings": list(self.top_findings),
            "age_buckets": dict(self.age_buckets),
        }


@dataclass(slots=True)
class PortfolioRollup:
    """Portfolio-level dashboard data."""

    engagement_count: int
    active_count: int
    finding_count: int
    open_finding_count: int
    critical_count: int
    risk_score: float
    risk_band: str
    severity: list[SeverityCount]
    engagements: list[EngagementRollup]

    def as_dict(self) -> dict[str, Any]:
        return {
            "engagement_count": self.engagement_count,
            "active_count": self.active_count,
            "finding_count": self.finding_count,
            "open_finding_count": self.open_finding_count,
            "critical_count": self.critical_count,
            "risk_score": round(self.risk_score, 2),
            "risk_band": self.risk_band,
            "severity": [item.as_dict() for item in self.severity],
            "engagements": [item.as_dict() for item in self.engagements],
        }


def risk_band(score: float) -> str:
    """Map a numeric risk score to a display band."""
    if score >= 60.0:
        return "critical"
    if score >= 35.0:
        return "high"
    if score >= 15.0:
        return "medium"
    if score > 0.0:
        return "low"
    return "none"


def finding_risk(finding: Finding) -> float:
    """Compute a confidence-weighted risk contribution for one finding."""
    if finding.status in {FindingStatus.DUPLICATE, FindingStatus.CLOSED}:
        return 0.0
    base = max(SEVERITY_WEIGHTS[finding.severity], finding.cvss_score * 1.5)
    return base * CONFIDENCE_MULTIPLIERS[finding.confidence]


def risk_score(findings: Iterable[Finding], *, cap: float = 100.0) -> float:
    """Aggregate finding risk with diminishing returns."""
    values = sorted((finding_risk(item) for item in findings), reverse=True)
    total = 0.0
    for index, value in enumerate(values):
        total += value / (1.0 + index * 0.25)
    return clamp(total, 0.0, cap)


def severity_counts(findings: Iterable[Finding]) -> list[SeverityCount]:
    """Count findings by severity and lifecycle state."""
    buckets: dict[Severity, SeverityCount] = {
        severity: SeverityCount(severity.value, 0, 0, 0, 0) for severity in SEVERITY_ORDER
    }
    for finding in findings:
        count = buckets[finding.severity]
        count.total += 1
        if finding.status is FindingStatus.OPEN:
            count.open += 1
        elif finding.status is FindingStatus.VERIFIED:
            count.verified += 1
        elif finding.status in {FindingStatus.CLOSED, FindingStatus.REMEDIATED}:
            count.closed += 1
    return [buckets[severity] for severity in SEVERITY_ORDER]


def status_counts(findings: Iterable[Finding]) -> dict[str, int]:
    """Count findings by status."""
    result = {status.value: 0 for status in FindingStatus}
    for finding in findings:
        result[finding.status.value] += 1
    return result


def confidence_counts(findings: Iterable[Finding]) -> dict[str, int]:
    """Count findings by confidence band."""
    result = {confidence.value: 0 for confidence in Confidence}
    for finding in findings:
        result[finding.confidence.value] += 1
    return result


def age_bucket(created_at: str, *, today: date | None = None) -> str:
    """Bucket finding age for aging widgets."""
    reference = today or datetime.now(timezone.utc).date()
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    except ValueError:
        return "older"
    age = (reference - created).days
    if age <= 0:
        return "today"
    if age <= 7:
        return "week"
    if age <= 30:
        return "month"
    return "older"


def age_buckets(findings: Iterable[Finding], *, today: date | None = None) -> dict[str, int]:
    """Count findings by age bucket."""
    result = dict.fromkeys(AGE_BUCKETS, 0)
    for finding in findings:
        result[age_bucket(finding.created_at, today=today)] += 1
    return result


def sort_findings(findings: Sequence[Finding], *, limit: int = 5) -> list[Finding]:
    """Sort findings by score, severity, recency, and id."""
    ordered = sorted(
        findings,
        key=lambda item: (
            -item.effective_score,
            -severity_index(item.severity),
            item.created_at,
            item.id,
        ),
    )
    return ordered[:limit]


def top_findings(findings: Iterable[Finding], *, limit: int = 5) -> list[dict[str, Any]]:
    """Return compact JSON rows for a top-findings widget."""
    return [
        {
            "id": item.id,
            "title": item.title,
            "severity": item.severity.value,
            "confidence": item.confidence.value,
            "status": item.status.value,
            "target_id": item.target_id,
            "score": item.effective_score,
            "risk": round(finding_risk(item), 2),
        }
        for item in sort_findings(list(findings), limit=limit)
    ]


def engagement_rollup(
    engagement: Engagement,
    *,
    targets: Iterable[Target] = (),
    assets: Iterable[Any] = (),
    services: Iterable[Any] = (),
    credentials: Iterable[Any] = (),
    findings: Iterable[Finding] = (),
    coverage_score: float = 0.0,
    today: date | None = None,
) -> EngagementRollup:
    """Build one engagement rollup from already-filtered collections."""
    finding_list = list(findings)
    open_findings = [
        finding
        for finding in finding_list
        if finding.status
        in {
            FindingStatus.OPEN,
            FindingStatus.VERIFIED,
            FindingStatus.ACCEPTED_RISK,
        }
    ]
    score = risk_score(finding_list)
    return EngagementRollup(
        engagement_id=engagement.id,
        name=engagement.display_name,
        status=engagement.status.value,
        kind=engagement.kind.value,
        target_count=len(list(targets)),
        asset_count=len(list(assets)),
        service_count=len(list(services)),
        credential_count=len(list(credentials)),
        finding_count=len(finding_list),
        open_finding_count=len(open_findings),
        verified_count=sum(1 for item in finding_list if item.status is FindingStatus.VERIFIED),
        duplicate_count=sum(1 for item in finding_list if item.status is FindingStatus.DUPLICATE),
        risk_score=score,
        risk_band=risk_band(score),
        coverage_score=coverage_score,
        severity=severity_counts(finding_list),
        status_counts=status_counts(finding_list),
        confidence_counts=confidence_counts(finding_list),
        top_findings=top_findings(finding_list),
        age_buckets=age_buckets(finding_list, today=today),
    )


def portfolio_rollup(
    engagements: Iterable[Engagement],
    rollups: Iterable[EngagementRollup],
    *,
    today: date | None = None,
) -> PortfolioRollup:
    """Aggregate engagement rollups into a portfolio dashboard."""
    engagement_list = list(engagements)
    rollup_list = sorted(rollups, key=lambda item: (-item.risk_score, item.engagement_id))
    all_findings: list[SeverityCount] = []
    for severity in SEVERITY_ORDER:
        total = sum(item.severity[severity_index(severity)].total for item in rollup_list)
        opened = sum(item.severity[severity_index(severity)].open for item in rollup_list)
        verified = sum(item.severity[severity_index(severity)].verified for item in rollup_list)
        closed = sum(item.severity[severity_index(severity)].closed for item in rollup_list)
        all_findings.append(SeverityCount(severity.value, total, opened, verified, closed))
    total_risk = sum(item.risk_score for item in rollup_list)
    return PortfolioRollup(
        engagement_count=len(engagement_list),
        active_count=sum(1 for item in engagement_list if item.status.value == "active"),
        finding_count=sum(item.finding_count for item in rollup_list),
        open_finding_count=sum(item.open_finding_count for item in rollup_list),
        critical_count=all_findings[severity_index(Severity.CRITICAL)].total,
        risk_score=total_risk,
        risk_band=risk_band(total_risk),
        severity=all_findings,
        engagements=rollup_list,
    )


def widget_cards(rollup: EngagementRollup) -> list[dict[str, Any]]:
    """Return stat cards for an engagement dashboard widget."""
    return [
        {"label": "Targets", "value": rollup.target_count, "tone": "neutral"},
        {"label": "Findings", "value": rollup.finding_count, "tone": "neutral"},
        {"label": "Open", "value": rollup.open_finding_count, "tone": "warning"},
        {
            "label": "Critical",
            "value": rollup.severity[severity_index(Severity.CRITICAL)].total,
            "tone": "danger",
        },
        {"label": "Risk", "value": format_number(rollup.risk_score), "tone": "accent"},
    ]


def severity_matrix(findings: Iterable[Finding]) -> dict[str, dict[str, int]]:
    """Return severity-by-confidence counts for a heat map."""
    result = {
        severity.value: {confidence.value: 0 for confidence in Confidence}
        for severity in SEVERITY_ORDER
    }
    for finding in findings:
        result[finding.severity.value][finding.confidence.value] += 1
    return result


def merge_status_counts(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    """Add two status-count maps."""
    result = dict(left)
    for key, value in right.items():
        result[key] = result.get(key, 0) + value
    return result
