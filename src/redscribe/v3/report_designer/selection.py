"""Stable finding and evidence selection for report designs.

Selection is deliberately rule-driven and order-independent: a candidate's
inclusion is a pure function of its own fields and the policy, and the final
ordering is derived from severity and stable keys rather than insertion order.
Every decision is recorded so the designer can explain why a finding is in or
out of a deliverable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.report_designer.identifiers import digest
from redscribe.v3.report_designer.model import (
    EvidenceItem,
    FindingItem,
    SelectionRule,
    Severity,
)


@dataclass(frozen=True, slots=True)
class FindingDecision:
    """The recorded outcome for one candidate finding."""

    key: str
    ref: str
    title: str
    included: bool
    rule: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "ref": self.ref,
            "title": self.title,
            "included": self.included,
            "rule": self.rule,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Selected findings plus a full audit of every decision."""

    included: tuple[FindingItem, ...]
    excluded: tuple[FindingItem, ...]
    decisions: tuple[FindingDecision, ...]

    @property
    def total(self) -> int:
        """Number of candidates considered."""
        return len(self.included) + len(self.excluded)

    @property
    def inclusion_rate(self) -> float:
        """Fraction of candidates that were included."""
        return round(len(self.included) / self.total, 4) if self.total else 0.0

    def digest(self) -> str:
        """Digest of the selected set and the decisions."""
        return digest(
            {
                "included": [item.key for item in self.included],
                "excluded": [item.key for item in self.excluded],
                "decisions": [item.as_dict() for item in self.decisions],
            }
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "included": [item.as_dict() for item in self.included],
            "excluded": [item.as_dict() for item in self.excluded],
            "decisions": [item.as_dict() for item in self.decisions],
            "total": self.total,
            "inclusion_rate": self.inclusion_rate,
        }


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    """Declarative policy controlling which findings reach a report."""

    rules: tuple[SelectionRule, ...] = ()
    minimum_severity: str = "info"
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    require_evidence: bool = False
    include_sensitive_evidence: bool = False

    def __post_init__(self) -> None:
        Severity.parse(self.minimum_severity)

    def decide(self, finding: FindingItem) -> tuple[bool, str, str]:
        """Return ``(included, rule_name, reason)`` for one finding."""
        if finding.severity_level.rank < Severity.parse(self.minimum_severity).rank:
            return (False, "severity-threshold", f"below {self.minimum_severity}")
        if self.statuses and finding.status not in self.statuses:
            return (False, "status-filter", f"status {finding.status} not allowed")
        if self.tags:
            tags = {tag.casefold() for tag in finding.tags}
            if not any(tag.casefold() in tags for tag in self.tags):
                return (False, "tag-filter", "no required tag")
        if self.require_evidence and not finding.evidence:
            return (False, "evidence-filter", "no attached evidence")
        for rule in self.rules:
            if rule.is_exclusion and rule_matches(rule, finding):
                return (False, rule.name, "excluded by rule")
        includes = [rule for rule in self.rules if not rule.is_exclusion]
        if includes:
            for rule in includes:
                if rule_matches(rule, finding):
                    return (True, rule.name, "included by rule")
            return (False, "no-include-match", "no include rule matched")
        return (True, "default", "no rule matched")

    def select(self, findings: tuple[FindingItem, ...]) -> SelectionResult:
        """Apply the policy to a set of findings."""
        included: list[FindingItem] = []
        excluded: list[FindingItem] = []
        decisions: list[FindingDecision] = []
        for finding in stable_sort_findings(findings):
            ok, rule, reason = self.decide(finding)
            if ok:
                included.append(finding)
            else:
                excluded.append(finding)
            decisions.append(
                FindingDecision(
                    key=finding.key,
                    ref=str(finding.ref),
                    title=finding.title,
                    included=ok,
                    rule=rule,
                    reason=reason,
                )
            )
        return SelectionResult(tuple(included), tuple(excluded), tuple(decisions))

    def digest(self) -> str:
        """Digest of the complete policy definition."""
        return digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "rules": [rule.as_dict() for rule in self.rules],
            "minimum_severity": self.minimum_severity,
            "statuses": list(self.statuses),
            "tags": list(self.tags),
            "require_evidence": self.require_evidence,
            "include_sensitive_evidence": self.include_sensitive_evidence,
        }


def rule_matches(rule: SelectionRule, finding: FindingItem) -> bool:
    """Return whether a selection rule matches one finding."""
    if rule.identifier and rule.identifier != finding.key and rule.identifier != str(finding.ref):
        return False
    if rule.severities and finding.severity not in rule.severities:
        return False
    if rule.statuses and finding.status not in rule.statuses:
        return False
    if rule.categories and finding.category.casefold() not in {
        value.casefold() for value in rule.categories
    }:
        return False
    if rule.tags:
        tags = {tag.casefold() for tag in finding.tags}
        if not any(tag.casefold() in tags for tag in rule.tags):
            return False
    return finding.confidence >= rule.minimum_confidence


def stable_sort_findings(findings: tuple[FindingItem, ...]) -> tuple[FindingItem, ...]:
    """Sort findings by severity, title, and stable key."""
    return tuple(
        sorted(
            findings,
            key=lambda item: (-item.severity_level.rank, item.title.casefold(), item.key),
        )
    )


def select_evidence(
    evidence: tuple[EvidenceItem, ...],
    *,
    include_sensitive: bool = False,
    limit: int = 0,
) -> tuple[EvidenceItem, ...]:
    """Filter and stably sort evidence items."""
    if limit < 0:
        raise ValueError("limit cannot be negative")
    result = tuple(
        sorted(
            (item for item in evidence if include_sensitive or not item.sensitive),
            key=lambda item: (item.title.casefold(), str(item.ref)),
        )
    )
    return result[:limit] if limit else result


def collect_evidence(findings: tuple[FindingItem, ...]) -> tuple[EvidenceItem, ...]:
    """Collect distinct evidence items from a set of findings."""
    seen: dict[str, EvidenceItem] = {}
    for finding in findings:
        for item in finding.evidence:
            seen.setdefault(str(item.ref), item)
    return tuple(seen[key] for key in sorted(seen))


def default_policy() -> SelectionPolicy:
    """Return a conservative default policy for client deliverables."""
    return SelectionPolicy(
        rules=(
            SelectionRule("drop-sensitive", "exclude", tags=("secret", "sensitive", "credential")),
            SelectionRule("drop-draft", "exclude", statuses=("draft",)),
            SelectionRule("reportable", "include"),
        ),
        minimum_severity="info",
        require_evidence=False,
        include_sensitive_evidence=False,
    )


def rule_summary(policy: SelectionPolicy) -> dict[str, Any]:
    """Summarize the rule set for display in the designer."""
    return {
        "total": len(policy.rules),
        "includes": sum(1 for rule in policy.rules if not rule.is_exclusion),
        "excludes": sum(1 for rule in policy.rules if rule.is_exclusion),
        "names": [rule.name for rule in policy.rules],
    }
