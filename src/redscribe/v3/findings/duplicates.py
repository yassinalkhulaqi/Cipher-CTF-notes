"""Duplicate suggestions built on the existing V2 duplicate detector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v2.engagements.duplicates import (
    DuplicateMatch,
    cluster_duplicates,
    find_duplicates,
    fingerprint,
)
from redscribe.v2.engagements.models import (
    Confidence,
)
from redscribe.v2.engagements.models import (
    Finding as V2Finding,
)
from redscribe.v2.engagements.models import (
    FindingStatus as V2FindingStatus,
)
from redscribe.v2.engagements.models import (
    Severity as V2Severity,
)
from redscribe.v3.entities.types import EntityRef
from redscribe.v3.findings.cvss_v4 import SeverityBand
from redscribe.v3.findings.models import Finding, FindingState

DEFAULT_THRESHOLD = 0.62
SCREENING_THRESHOLD = 0.45
CROSS_TARGET_THRESHOLD = 0.78
DIVERGENT_MAPPING_THRESHOLD = 0.8
MIN_TITLE_TOKENS = 2

_SEVERITY_MAP: dict[SeverityBand, V2Severity] = {
    SeverityBand.NONE: V2Severity.INFO,
    SeverityBand.LOW: V2Severity.LOW,
    SeverityBand.MEDIUM: V2Severity.MEDIUM,
    SeverityBand.HIGH: V2Severity.HIGH,
    SeverityBand.CRITICAL: V2Severity.CRITICAL,
}
_STATE_MAP: dict[FindingState, V2FindingStatus] = {
    FindingState.DRAFT: V2FindingStatus.DRAFT,
    FindingState.CONFIRMED: V2FindingStatus.OPEN,
    FindingState.REMEDIATED: V2FindingStatus.REMEDIATED,
    FindingState.RETESTED: V2FindingStatus.VERIFIED,
    FindingState.CLOSED: V2FindingStatus.CLOSED,
}


class DuplicateError(ValueError):
    """Raised when duplicate detection inputs are invalid."""


@dataclass(frozen=True, slots=True)
class DuplicateSuggestion:
    """A candidate duplicate expressed in V3 entity references."""

    source_ref: str
    candidate_ref: EntityRef
    score: float
    reasons: tuple[str, ...]
    fingerprint: str
    threshold: float

    @property
    def confirmed(self) -> bool:
        """Whether the score clears the configured threshold."""
        return self.score >= self.threshold

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source_ref": self.source_ref,
            "candidate_ref": self.candidate_ref.as_dict(),
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "fingerprint": self.fingerprint,
            "threshold": self.threshold,
            "confirmed": self.confirmed,
        }


def _identifier(value: str, registry: dict[str, int]) -> int:
    """Map a stable string reference to a small integer id."""
    if value not in registry:
        registry[value] = len(registry) + 1
    return registry[value]


def to_v2_finding(
    finding: Finding,
    registry: dict[str, int],
    *,
    engagement_id: int = 1,
) -> V2Finding:
    """Adapt an immutable V3 finding to the V2 duplicate detector's shape."""
    reproduction = "\n".join(
        part for part in (finding.summary, finding.metadata.get("reproduction_steps", "")) if part
    )
    evidence = "\n".join(block.excerpt for block in finding.proof_blocks if block.excerpt)
    target_id = _identifier(str(finding.target_ref), registry) if finding.target_ref else 0
    return V2Finding(
        id=_identifier(finding.ref_string, registry),
        engagement_id=engagement_id,
        target_id=target_id,
        title=finding.title,
        summary=finding.summary,
        severity=_SEVERITY_MAP[finding.severity],
        confidence=Confidence.CONFIRMED
        if finding.state in (FindingState.RETESTED, FindingState.CLOSED)
        else Confidence.MEDIUM,
        cvss_vector=finding.vector,
        cvss_score=finding.score,
        cwe=finding.mappings.primary_cwe,
        cwes=list(finding.mappings.cwes),
        cves=list(finding.mappings.cves),
        status=_STATE_MAP[finding.state],
        impact=evidence or finding.mappings.notes,
        remediation=" ".join(task.title for task in finding.remediation),
        reproduction_steps=reproduction,
        references=[],
        tags=list(finding.tags),
        duplicate_of=_identifier(str(finding.duplicate_of), registry)
        if finding.duplicate_of
        else 0,
    )


def fingerprint_of(finding: Finding) -> str:
    """Return the V2 fingerprint for a V3 finding."""
    return fingerprint(to_v2_finding(finding, {}))


def _title_tokens(text: str) -> set[str]:
    return {token for token in text.casefold().replace("_", " ").split() if len(token) > 2}


def _passes_false_positive_controls(
    source: Finding,
    candidate: Finding,
    score: float,
    threshold: float,
) -> bool:
    """Apply V3-specific controls on top of the V2 token score."""
    if score < SCREENING_THRESHOLD:
        return False
    if source.duplicate_of is not None or candidate.duplicate_of is not None:
        return False
    if candidate.state is FindingState.CLOSED:
        return False
    if len(_title_tokens(source.title)) < MIN_TITLE_TOKENS:
        return False
    if len(_title_tokens(candidate.title)) < MIN_TITLE_TOKENS:
        return False

    shared_cwe = bool(set(source.mappings.cwes) & set(candidate.mappings.cwes))
    shared_cve = bool(set(source.mappings.cves) & set(candidate.mappings.cves))
    same_target = source.target_ref is not None and source.target_ref == candidate.target_ref
    if not same_target and not shared_cwe and not shared_cve and score < CROSS_TARGET_THRESHOLD:
        return False

    source_cwes = set(source.mappings.cwes)
    candidate_cwes = set(candidate.mappings.cwes)
    if (
        source_cwes
        and candidate_cwes
        and not source_cwes & candidate_cwes
        and score < DIVERGENT_MAPPING_THRESHOLD
    ):
        return False

    if (
        abs(source.severity.rank - candidate.severity.rank) >= 2
        and score < DIVERGENT_MAPPING_THRESHOLD
    ):
        return False

    return score >= threshold


def suggest_duplicates(
    source: Finding,
    candidates: list[Finding],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    include_reasons: bool = True,
) -> tuple[DuplicateSuggestion, ...]:
    """Rank candidate findings that may be duplicates of ``source``."""
    if not 0.0 <= threshold <= 1.0:
        raise DuplicateError("Duplicate threshold must be between 0 and 1")

    registry: dict[str, int] = {}
    source_v2 = to_v2_finding(source, registry)
    candidate_v2 = [to_v2_finding(item, registry) for item in candidates]
    matches: list[DuplicateMatch] = find_duplicates(
        source_v2, candidate_v2, threshold=SCREENING_THRESHOLD
    )
    by_id = {match.candidate_id: match for match in matches}
    source_fp = fingerprint_of(source)

    suggestions: list[DuplicateSuggestion] = []
    for candidate, converted in zip(candidates, candidate_v2, strict=True):
        match = by_id.get(converted.id)
        if match is None:
            continue
        if not _passes_false_positive_controls(source, candidate, match.score, threshold):
            continue
        reasons = match.reasons if include_reasons else ()
        suggestions.append(
            DuplicateSuggestion(
                source_ref=source.ref_string,
                candidate_ref=candidate.ref,
                score=match.score,
                reasons=reasons,
                fingerprint=source_fp,
                threshold=threshold,
            )
        )
    suggestions.sort(key=lambda item: (-item.score, str(item.candidate_ref)))
    return tuple(suggestions)


def duplicate_clusters(findings: list[Finding]) -> tuple[tuple[str, ...], ...]:
    """Group findings with the V2 single-link clustering helper."""
    registry: dict[str, int] = {}
    converted = [to_v2_finding(item, registry) for item in findings]
    clusters = cluster_duplicates(converted)
    by_id = {
        converted_item.id: source.ref_string
        for source, converted_item in zip(findings, converted, strict=True)
    }
    return tuple(
        tuple(by_id[member.id] for member in cluster) for cluster in clusters if len(cluster) > 1
    )


def duplicate_summary(
    source: Finding,
    candidates: list[Finding],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Return a compact duplicate report for the finding editor."""
    suggestions = suggest_duplicates(source, candidates, threshold=threshold)
    return {
        "source": source.ref_string,
        "fingerprint": suggestions[0].fingerprint if suggestions else fingerprint_of(source),
        "count": len(suggestions),
        "best": suggestions[0].as_dict() if suggestions else None,
        "candidates": [item.as_dict() for item in suggestions],
    }
