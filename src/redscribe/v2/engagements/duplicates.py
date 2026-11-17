"""Finding fingerprinting and duplicate detection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.engagements.models import Finding, FindingStatus, Severity
from redscribe.v2.engagements.util import clamp, digest, tokens
from redscribe.v2.engagements.validation import normalize_text_for_match

STOP_TOKENS = {
    "admin",
    "default",
    "generic",
    "multiple",
    "remote",
    "local",
    "unauthenticated",
    "authenticated",
}

FIELD_WEIGHTS = {"title": 0.45, "target": 0.2, "summary": 0.2, "evidence": 0.15}


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    """A candidate duplicate with a normalized similarity score."""

    source_id: int
    candidate_id: int
    score: float
    reasons: tuple[str, ...]
    fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "candidate_id": self.candidate_id,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "fingerprint": self.fingerprint,
        }


def normalize_title(title: str) -> str:
    """Normalize a finding title for comparison."""
    meaningful = normalize_text_for_match(title)
    return " ".join(sorted(meaningful))


def finding_tokens(finding: Finding) -> dict[str, tuple[str, ...]]:
    """Extract weighted token sets from a finding."""
    return {
        "title": normalize_text_for_match(finding.title),
        "target": tokens(finding.reproduction_steps)[:8],
        "summary": normalize_text_for_match(finding.summary),
        "evidence": normalize_text_for_match(finding.impact)[:16],
    }


def fingerprint(finding: Finding) -> str:
    """Return a stable fingerprint that ignores cosmetic wording."""
    title = normalize_title(finding.title)
    target = " ".join(
        sorted(token for token in tokens(finding.reproduction_steps) if token not in STOP_TOKENS)
    )
    parts = [title, target, finding.cwe.lower()]
    return digest("|".join(parts))


def jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    """Compute Jaccard similarity for two token sequences."""
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def containment(left: Sequence[str], right: Sequence[str]) -> float:
    """Compute asymmetric containment of one token set in another."""
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / min(len(left_set), len(right_set))


def duplicate_score(left: Finding, right: Finding) -> float:
    """Return a 0..1 duplicate likelihood for two findings."""
    left_tokens = finding_tokens(left)
    right_tokens = finding_tokens(right)
    score = 0.0
    for field_name, weight in FIELD_WEIGHTS.items():
        similarity = jaccard(left_tokens[field_name], right_tokens[field_name])
        score += weight * similarity
    title_containment = containment(left_tokens["title"], right_tokens["title"])
    score += 0.1 * title_containment
    if left.cwe and left.cwe == right.cwe:
        score += 0.1
    if left.cves and set(left.cves) & set(right.cves):
        score += 0.1
    if left.target_id and left.target_id == right.target_id:
        score += 0.05
    if left.severity is not right.severity:
        score -= 0.05
    return clamp(score)


def duplicate_reasons(left: Finding, right: Finding) -> tuple[str, ...]:
    """Explain why two findings were considered similar."""
    reasons: list[str] = []
    if normalize_title(left.title) == normalize_title(right.title):
        reasons.append("same normalized title")
    if left.cwe and left.cwe == right.cwe:
        reasons.append("same CWE")
    if set(left.cves) & set(right.cves):
        reasons.append("shared CVE")
    if left.target_id and left.target_id == right.target_id:
        reasons.append("same target")
    if jaccard(finding_tokens(left)["summary"], finding_tokens(right)["summary"]) >= 0.6:
        reasons.append("similar summary")
    if not reasons:
        reasons.append("token similarity")
    return tuple(reasons)


def find_duplicates(
    source: Finding,
    candidates: Iterable[Finding],
    *,
    threshold: float = 0.62,
    exclude_statuses: frozenset[str] = frozenset({"duplicate", "closed"}),
) -> list[DuplicateMatch]:
    """Rank candidates that look like duplicates of ``source``."""
    matches: list[DuplicateMatch] = []
    source_fp = fingerprint(source)
    for candidate in candidates:
        if candidate.id == source.id:
            continue
        if candidate.engagement_id != source.engagement_id:
            continue
        if candidate.status.value in exclude_statuses:
            continue
        score = duplicate_score(source, candidate)
        if score < threshold:
            continue
        matches.append(
            DuplicateMatch(
                source_id=source.id,
                candidate_id=candidate.id,
                score=score,
                reasons=duplicate_reasons(source, candidate),
                fingerprint=source_fp,
            )
        )
    matches.sort(key=lambda item: (-item.score, item.candidate_id))
    return matches


def best_duplicate(
    source: Finding, candidates: Iterable[Finding], *, threshold: float = 0.62
) -> DuplicateMatch | None:
    """Return the single strongest duplicate candidate, if any."""
    matches = find_duplicates(source, candidates, threshold=threshold)
    return matches[0] if matches else None


def cluster_duplicates(
    findings: Iterable[Finding],
    *,
    threshold: float = 0.62,
) -> list[list[Finding]]:
    """Group findings into similarity clusters using single-link clustering."""
    items = sorted(findings, key=lambda item: item.id)
    parent = {item.id: item.id for item in items}

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    by_id = {item.id: item for item in items}
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if left.engagement_id != right.engagement_id:
                continue
            if duplicate_score(left, right) >= threshold:
                union(left.id, right.id)
    groups: dict[int, list[Finding]] = {}
    for item in items:
        groups.setdefault(find(item.id), []).append(by_id[item.id])
    return sorted(groups.values(), key=lambda group: group[0].id)


def duplicate_summary(findings: Iterable[Finding], *, threshold: float = 0.62) -> dict[str, Any]:
    """Return duplicate-cluster metrics for dashboard widgets."""
    clusters = cluster_duplicates(findings, threshold=threshold)
    duplicate_groups = [cluster for cluster in clusters if len(cluster) > 1]
    return {
        "total": sum(len(cluster) for cluster in clusters),
        "clusters": len(clusters),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_findings": sum(len(cluster) - 1 for cluster in duplicate_groups),
        "groups": [
            {
                "ids": [item.id for item in cluster],
                "titles": [item.title for item in cluster],
                "severity": max(
                    (item.severity for item in cluster),
                    key=lambda value: list(Severity).index(value),
                ).value,
            }
            for cluster in duplicate_groups
        ],
    }


def canonical_candidate(cluster: Sequence[Finding]) -> Finding:
    """Choose the most complete finding in a duplicate cluster."""

    def completeness(item: Finding) -> tuple[int, int, int]:
        return (
            item.status is not FindingStatus.DRAFT,
            len(item.reproduction_steps) + len(item.impact) + len(item.remediation),
            len(item.references),
        )

    return max(cluster, key=completeness)


def reassign_duplicates(
    findings: Iterable[Finding],
    canonical_id: int,
    duplicate_ids: Iterable[int],
) -> dict[int, int]:
    """Build an id-to-canonical mapping, guarding against self-links."""
    mapping: dict[int, int] = {}
    for duplicate_id in duplicate_ids:
        if duplicate_id != canonical_id:
            mapping[duplicate_id] = canonical_id
    return mapping


def from_dicts(values: Iterable[Mapping[str, Any]]) -> list[Finding]:
    """Convert serialized findings into domain objects for detection."""
    return [Finding.from_dict(value) for value in values]
