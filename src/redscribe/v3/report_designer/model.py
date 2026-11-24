"""Layout document model for the visual report designer.

A report design is an immutable tree. Sections carry findings, findings carry
evidence, and every first-class item is addressed with a V3 :class:`EntityRef`
so the designer never defines its own foreign-key vocabulary. The same tree
feeds the pagination engine and every renderer, which is what makes the
print preview and the exported files structurally identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Literal

from redscribe.v3.entities.types import EntityKind, EntityRef
from redscribe.v3.report_designer.identifiers import anchor_for, digest, slugify

SeverityName = Literal["info", "low", "medium", "high", "critical"]
FindingStatus = Literal["open", "confirmed", "mitigated", "accepted", "closed"]
EvidenceKind = Literal["note", "command", "artifact", "observation", "reference"]
RedactionScope = Literal["all", "body", "title", "evidence"]

SEVERITY_ORDER: tuple[SeverityName, ...] = ("info", "low", "medium", "high", "critical")
SEVERITY_RANKS: dict[str, int] = {name: index for index, name in enumerate(SEVERITY_ORDER)}
SEVERITY_LABELS: dict[str, str] = {
    "info": "Informational",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}
SEVERITY_ALIASES: dict[str, str] = {
    "information": "info",
    "informational": "info",
    "none": "info",
    "minor": "low",
    "moderate": "medium",
    "major": "high",
    "severe": "critical",
}
FINDING_STATUSES: tuple[FindingStatus, ...] = (
    "open",
    "confirmed",
    "mitigated",
    "accepted",
    "closed",
)
EVIDENCE_KINDS: tuple[EvidenceKind, ...] = (
    "note",
    "command",
    "artifact",
    "observation",
    "reference",
)
REDACTION_SCOPES: tuple[RedactionScope, ...] = ("all", "body", "title", "evidence")


class Severity(str, Enum):
    """Ordered severity scale shared by selection, sorting, and rendering."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def parse(cls, value: str | Severity) -> Severity:
        """Parse a severity, accepting common aliases and ignoring case."""
        if isinstance(value, Severity):
            return value
        normalized = value.strip().casefold()
        normalized = SEVERITY_ALIASES.get(normalized, normalized)
        if normalized not in SEVERITY_RANKS:
            raise ValueError(f"Unknown severity: {value}")
        return cls(normalized)

    @property
    def rank(self) -> int:
        """Numeric ordering value, higher means more severe."""
        return SEVERITY_RANKS[self.value]

    @property
    def label(self) -> str:
        """Human-readable label."""
        return SEVERITY_LABELS[self.value]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"value": self.value, "rank": self.rank, "label": self.label}


class SectionKind(str, Enum):
    """Structural role of a section in the page layout."""

    COVER = "cover"
    TOC = "toc"
    EXECUTIVE_SUMMARY = "executive_summary"
    TEXT = "text"
    FINDINGS = "findings"
    EVIDENCE = "evidence"
    RECOMMENDATIONS = "recommendations"
    APPENDIX = "appendix"
    DIVIDER = "divider"

    @classmethod
    def parse(cls, value: str | SectionKind) -> SectionKind:
        """Parse a section kind from its wire value."""
        if isinstance(value, SectionKind):
            return value
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unknown section kind: {value}")

    @property
    def is_special(self) -> bool:
        """Whether the section is generated front or back matter."""
        return self in (SectionKind.COVER, SectionKind.TOC, SectionKind.APPENDIX)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """A citable unit of source material attached to a finding."""

    ref: EntityRef
    title: str
    content: str = ""
    excerpt: str = ""
    kind: EvidenceKind = "note"
    locator: str = ""
    sensitive: bool = False

    def __post_init__(self) -> None:
        if self.ref.kind is not EntityKind.EVIDENCE:
            raise ValueError("Evidence items must reference an evidence entity")
        if not self.title.strip():
            raise ValueError("Evidence title cannot be blank")
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(f"Unknown evidence kind: {self.kind}")

    @property
    def citation(self) -> str:
        """Short citation label for renderers."""
        return f"{self.title} ({self.locator})" if self.locator else self.title

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": str(self.ref),
            "label": self.ref.label,
            "title": self.title,
            "content": self.content,
            "excerpt": self.excerpt,
            "kind": self.kind,
            "locator": self.locator,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True, slots=True)
class FindingItem:
    """A security observation with evidence and remediation guidance."""

    ref: EntityRef
    title: str
    summary: str = ""
    severity: SeverityName = "medium"
    status: FindingStatus = "open"
    category: str = ""
    tags: tuple[str, ...] = ()
    confidence: float = 1.0
    impact: str = ""
    recommendation: str = ""
    evidence: tuple[EvidenceItem, ...] = ()
    references: tuple[str, ...] = ()
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.ref.kind is not EntityKind.FINDING:
            raise ValueError("Finding items must reference a finding entity")
        if not self.title.strip():
            raise ValueError("Finding title cannot be blank")
        Severity.parse(self.severity)
        if self.status not in FINDING_STATUSES:
            raise ValueError(f"Unknown finding status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")

    @property
    def key(self) -> str:
        """Stable identifier used for anchors and sorting."""
        return self.identifier or slugify(self.title, fallback="finding")

    @property
    def severity_level(self) -> Severity:
        """Parsed severity value."""
        return Severity.parse(self.severity)

    @property
    def is_open(self) -> bool:
        """Whether the finding is still an active observation."""
        return self.status in ("open", "confirmed")

    @property
    def evidence_count(self) -> int:
        """Number of attached evidence items."""
        return len(self.evidence)

    def with_evidence(self, evidence: tuple[EvidenceItem, ...]) -> FindingItem:
        """Return a copy with a different evidence set."""
        return replace(self, evidence=evidence)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": str(self.ref),
            "label": self.ref.label,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "status": self.status,
            "category": self.category,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "evidence": [item.as_dict() for item in self.evidence],
            "references": list(self.references),
            "identifier": self.key,
        }


@dataclass(frozen=True, slots=True)
class LayoutSection:
    """One block in the report outline. Sections may nest and carry findings."""

    key: str
    title: str
    kind: SectionKind = SectionKind.TEXT
    level: int = 1
    order: int = 0
    visible: bool = True
    body: str = ""
    summary: str = ""
    findings: tuple[FindingItem, ...] = ()
    children: tuple[LayoutSection, ...] = ()
    page_break_before: bool = False
    include_toc: bool = True
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Section key cannot be blank")
        if not self.title.strip():
            raise ValueError("Section title cannot be blank")
        if not 1 <= self.level <= 6:
            raise ValueError("Section level must be between one and six")
        object.__setattr__(self, "kind", SectionKind.parse(self.kind))

    @property
    def anchor(self) -> str:
        """Stable anchor derived from the section key."""
        return anchor_for(self.key)

    @property
    def is_container(self) -> bool:
        """Whether the section groups other sections."""
        return bool(self.children) or self.kind in (
            SectionKind.FINDINGS,
            SectionKind.APPENDIX,
        )

    @property
    def finding_count(self) -> int:
        """Number of findings directly attached to this section."""
        return len(self.findings)

    def walk(self) -> tuple[LayoutSection, ...]:
        """Return this section and all descendants in depth-first order."""
        result: list[LayoutSection] = [self]
        for child in self.children:
            result.extend(child.walk())
        return tuple(result)

    def all_findings(self) -> tuple[FindingItem, ...]:
        """Return findings attached anywhere in this subtree."""
        return tuple(item for node in self.walk() for item in node.findings)

    def visible_walk(self) -> tuple[LayoutSection, ...]:
        """Return visible sections in this subtree only."""
        return tuple(node for node in self.walk() if node.visible)

    def with_children(self, children: tuple[LayoutSection, ...]) -> LayoutSection:
        """Return a copy with a different child list."""
        return replace(self, children=children)

    def with_findings(self, findings: tuple[FindingItem, ...]) -> LayoutSection:
        """Return a copy with a different finding list."""
        return replace(self, findings=findings)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "title": self.title,
            "kind": self.kind.value,
            "level": self.level,
            "order": self.order,
            "visible": self.visible,
            "body": self.body,
            "summary": self.summary,
            "findings": [item.as_dict() for item in self.findings],
            "children": [child.as_dict() for child in self.children],
            "page_break_before": self.page_break_before,
            "include_toc": self.include_toc,
            "metadata": dict(self.metadata),
            "anchor": self.anchor,
        }


@dataclass(frozen=True, slots=True)
class SeverityCounts:
    """Finding totals grouped by severity."""

    info: int = 0
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0

    def increment(self, severity: str) -> SeverityCounts:
        """Return a copy with one more finding of the given severity."""
        values = self.as_dict()
        values[Severity.parse(severity).value] += 1
        return SeverityCounts(**values)

    def total(self) -> int:
        """Total number of counted findings."""
        return sum(self.as_dict().values())

    def weighted(self) -> int:
        """Severity-weighted score useful for risk summaries."""
        return sum(SEVERITY_RANKS[name] * count for name, count in self.as_dict().items())

    def highest(self) -> SeverityName:
        """Highest severity present in the counts."""
        for name in reversed(SEVERITY_ORDER):
            if self.as_dict()[name] > 0:
                return name
        return "info"

    def as_dict(self) -> dict[str, int]:
        """Return a JSON-safe representation."""
        return {
            "info": self.info,
            "low": self.low,
            "medium": self.medium,
            "high": self.high,
            "critical": self.critical,
        }


def count_severities(findings: tuple[FindingItem, ...]) -> SeverityCounts:
    """Aggregate a set of findings into severity counts."""
    counts = SeverityCounts()
    for finding in findings:
        counts = counts.increment(finding.severity)
    return counts


@dataclass(frozen=True, slots=True)
class LayoutDocument:
    """A complete, deterministic report design tree."""

    key: str
    title: str
    subtitle: str = ""
    client: str = ""
    author: str = ""
    classification: str = "internal"
    generated_at: str = ""
    theme: str = "client"
    sections: tuple[LayoutSection, ...] = ()
    findings: tuple[FindingItem, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Document key cannot be blank")
        if not self.title.strip():
            raise ValueError("Document title cannot be blank")

    @property
    def all_sections(self) -> tuple[LayoutSection, ...]:
        """Every section in the tree, depth-first."""
        return tuple(node for root in self.sections for node in root.walk())

    @property
    def visible_sections(self) -> tuple[LayoutSection, ...]:
        """Every visible section in reading order."""
        return tuple(node for node in self.all_sections if node.visible)

    @property
    def finding_count(self) -> int:
        """Total findings attached to the document."""
        return len(self.findings) + sum(section.finding_count for section in self.all_sections)

    @property
    def severity(self) -> SeverityCounts:
        """Severity counts across every finding."""
        return count_severities(self.all_findings)

    @property
    def all_findings(self) -> tuple[FindingItem, ...]:
        """Findings at document level plus those inside sections."""
        values = list(self.findings)
        for section in self.all_sections:
            values.extend(section.findings)
        return tuple(values)

    def find_section(self, key: str) -> LayoutSection | None:
        """Look up a section by key."""
        return next((node for node in self.all_sections if node.key == key), None)

    def fingerprint(self) -> str:
        """Stable digest of every build-affecting field."""
        return digest(self.as_dict())

    def with_sections(self, sections: tuple[LayoutSection, ...]) -> LayoutDocument:
        """Return a copy with a different section tree."""
        return replace(self, sections=sections)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "title": self.title,
            "subtitle": self.subtitle,
            "client": self.client,
            "author": self.author,
            "classification": self.classification,
            "generated_at": self.generated_at,
            "theme": self.theme,
            "sections": [node.as_dict() for node in self.sections],
            "findings": [item.as_dict() for item in self.findings],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SelectionRule:
    """Declarative rule used to include or exclude candidate findings."""

    name: str
    action: Literal["include", "exclude"] = "include"
    severities: tuple[SeverityName, ...] = ()
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    minimum_confidence: float = 0.0
    identifier: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Selection rule needs a name")
        if self.action not in ("include", "exclude"):
            raise ValueError(f"Unknown rule action: {self.action}")
        for severity in self.severities:
            Severity.parse(severity)
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between zero and one")

    @property
    def is_exclusion(self) -> bool:
        """Whether the rule excludes matching findings."""
        return self.action == "exclude"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "action": self.action,
            "severities": list(self.severities),
            "statuses": list(self.statuses),
            "tags": list(self.tags),
            "categories": list(self.categories),
            "minimum_confidence": self.minimum_confidence,
            "identifier": self.identifier,
        }


@dataclass(frozen=True, slots=True)
class RedactionRule:
    """One replacement rule applied to report text before rendering."""

    name: str
    pattern: str
    replacement: str = "[REDACTED]"
    enabled: bool = True
    priority: int = 0
    scope: RedactionScope = "all"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Redaction rule needs a name")
        if not self.pattern.strip():
            raise ValueError("Redaction rule needs a pattern")
        if self.scope not in REDACTION_SCOPES:
            raise ValueError(f"Unknown redaction scope: {self.scope}")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "pattern": self.pattern,
            "replacement": self.replacement,
            "enabled": self.enabled,
            "priority": self.priority,
            "scope": self.scope,
        }


def empty_counts() -> SeverityCounts:
    """Return a zeroed severity counter."""
    return SeverityCounts()
