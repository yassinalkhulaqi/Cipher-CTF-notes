"""Target coverage assessment and gap analysis."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.engagements.models import (
    Asset,
    Criticality,
    Finding,
    FindingStatus,
    ScopeStatus,
    Service,
    Target,
    criticality_index,
)
from redscribe.v2.engagements.util import clamp, format_number

COVERAGE_WEIGHTS = {
    "scope": 0.20,
    "assets": 0.20,
    "services": 0.20,
    "findings": 0.25,
    "evidence": 0.15,
}


class CoverageLevel(str):
    """Display bands for coverage scores."""


def coverage_level(score: float) -> str:
    """Map a coverage score to a display band."""
    if score >= 0.85:
        return "complete"
    if score >= 0.6:
        return "good"
    if score >= 0.35:
        return "partial"
    return "missing"


@dataclass(slots=True)
class TargetCoverage:
    """Coverage details for one target."""

    target_id: int
    target_name: str
    scope_status: str
    criticality: str
    score: float
    level: str
    asset_count: int
    service_count: int
    finding_count: int
    verified_count: int
    evidence_count: int
    gaps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "scope_status": self.scope_status,
            "criticality": self.criticality,
            "score": round(self.score, 4),
            "level": self.level,
            "asset_count": self.asset_count,
            "service_count": self.service_count,
            "finding_count": self.finding_count,
            "verified_count": self.verified_count,
            "evidence_count": self.evidence_count,
            "gaps": list(self.gaps),
        }


@dataclass(slots=True)
class CoverageReport:
    """Aggregated coverage data for an engagement."""

    engagement_id: int
    score: float
    level: str
    targets: list[TargetCoverage]
    uncovered: list[int]
    partial: list[int]
    priority: list[int]
    gaps: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "engagement_id": self.engagement_id,
            "score": round(self.score, 4),
            "level": self.level,
            "targets": [target.as_dict() for target in self.targets],
            "uncovered": list(self.uncovered),
            "partial": list(self.partial),
            "priority": list(self.priority),
            "gaps": list(self.gaps),
        }


def assess_target(
    target: Target,
    assets: Iterable[Asset],
    services: Iterable[Service],
    findings: Iterable[Finding],
) -> TargetCoverage:
    """Compute the coverage score and gaps for one target."""
    target_assets = [asset for asset in assets if asset.target_id == target.id]
    target_services = [
        service
        for service in services
        if service.target_id == target.id
        or service.asset_id in {asset.id for asset in target_assets}
    ]
    target_findings = [finding for finding in findings if finding.target_id == target.id]
    verified = [finding for finding in target_findings if finding.status is FindingStatus.VERIFIED]
    evidence = [
        finding
        for finding in target_findings
        if finding.reproduction_steps.strip() or finding.references
    ]

    gaps: list[str] = []
    scope_score = 1.0 if target.scope_status is ScopeStatus.IN_SCOPE else 0.25
    if target.scope_status is not ScopeStatus.IN_SCOPE:
        gaps.append("target is not confirmed in scope")
    asset_score = 1.0 if target_assets else 0.0
    if not target_assets:
        gaps.append("no assets identified")
    service_score = min(1.0, len(target_services) / 2.0)
    if not target_services:
        gaps.append("no services enumerated")
    finding_score = min(1.0, len(target_findings) / 2.0)
    if not target_findings:
        gaps.append("no findings recorded")
    evidence_score = min(1.0, len(evidence) / max(1, len(target_findings)))
    if evidence and len(evidence) < len(target_findings):
        gaps.append("some findings lack evidence")

    score = clamp(
        COVERAGE_WEIGHTS["scope"] * scope_score
        + COVERAGE_WEIGHTS["assets"] * asset_score
        + COVERAGE_WEIGHTS["services"] * service_score
        + COVERAGE_WEIGHTS["findings"] * finding_score
        + COVERAGE_WEIGHTS["evidence"] * evidence_score
    )
    if verified:
        score = clamp(score + 0.05)
    return TargetCoverage(
        target_id=target.id,
        target_name=target.display_name,
        scope_status=target.scope_status.value,
        criticality=target.criticality.value,
        score=score,
        level=coverage_level(score),
        asset_count=len(target_assets),
        service_count=len(target_services),
        finding_count=len(target_findings),
        verified_count=len(verified),
        evidence_count=len(evidence),
        gaps=gaps,
    )


def priority_ranking(
    targets: Sequence[Target], coverage: Mapping[int, TargetCoverage]
) -> list[int]:
    """Rank targets by criticality and low coverage."""

    def key(target: Target) -> tuple[int, float, int]:
        detail = coverage.get(target.id)
        return (-criticality_index(target.criticality), detail.score if detail else 0.0, target.id)

    ranked = sorted(targets, key=key)
    return [target.id for target in ranked]


def compute_coverage(
    engagement_id: int,
    targets: Iterable[Target],
    assets: Iterable[Asset],
    services: Iterable[Service],
    findings: Iterable[Finding],
) -> CoverageReport:
    """Build a coverage report for all targets in an engagement."""
    target_list = [target for target in targets if target.engagement_id == engagement_id]
    asset_list = [asset for asset in assets if asset.engagement_id == engagement_id]
    service_list = [service for service in services if service.engagement_id == engagement_id]
    finding_list = [finding for finding in findings if finding.engagement_id == engagement_id]

    details = [
        assess_target(target, asset_list, service_list, finding_list) for target in target_list
    ]
    by_id = {detail.target_id: detail for detail in details}
    total_score = sum(detail.score for detail in details) / len(details) if details else 0.0
    uncovered = [detail.target_id for detail in details if detail.level == "missing"]
    partial = [detail.target_id for detail in details if detail.level in {"missing", "partial"}]
    gaps = list(dict.fromkeys(gap for detail in details for gap in detail.gaps))
    return CoverageReport(
        engagement_id=engagement_id,
        score=total_score,
        level=coverage_level(total_score),
        targets=details,
        uncovered=uncovered,
        partial=partial,
        priority=priority_ranking(target_list, by_id),
        gaps=gaps,
    )


def coverage_percent(report: CoverageReport) -> int:
    """Return a whole-number percentage for UI display."""
    return round(report.score * 100)


def coverage_label(report: CoverageReport) -> str:
    """Return a human-readable coverage label."""
    return f"{format_number(report.score * 100)}% {report.level}"


def out_of_scope_count(targets: Iterable[Target]) -> int:
    """Count targets explicitly excluded from scope."""
    return sum(
        1
        for target in targets
        if target.scope_status in {ScopeStatus.OUT_OF_SCOPE, ScopeStatus.WAIVED}
    )


def criticality_distribution(targets: Iterable[Target]) -> dict[str, int]:
    """Count targets by criticality band."""
    result = {item.value: 0 for item in Criticality}
    for target in targets:
        result[target.criticality.value] += 1
    return result


def coverage_gap_summary(report: CoverageReport) -> list[dict[str, Any]]:
    """Return gaps with affected target counts for reporting."""
    counts: dict[str, int] = {}
    for detail in report.targets:
        for gap in detail.gaps:
            counts[gap] = counts.get(gap, 0) + 1
    return [
        {"gap": gap, "count": count}
        for gap, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
