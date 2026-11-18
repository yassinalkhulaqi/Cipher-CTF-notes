"""Typed models for the reporting studio domain.

A report is a deterministic tree of sections. Sections carry findings, and
findings carry evidence references back to vault notes. The models in this
module are deliberately serializable so the same object can drive the editor,
the renderers, and the reproducibility manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Literal

from redscribe.domain.models import STATUSES as NOTE_STATUSES
from redscribe.v2.reporting.identifiers import canonical_json, slugify

SeverityName = Literal["info", "low", "medium", "high", "critical"]
ReportFormat = Literal["markdown", "html", "json", "print"]
FindingStatus = Literal["open", "confirmed", "mitigated", "accepted", "closed"]
EvidenceKind = Literal["note", "command", "artifact", "observation", "reference"]


class Severity(str, Enum):
    """Ordered reporting severity levels."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return SEVERITY_RANKS[self.value]

    @property
    def label(self) -> str:
        return SEVERITY_LABELS[self.value]

    @classmethod
    def parse(cls, value: str | Severity) -> Severity:
        if isinstance(value, Severity):
            return value
        normalized = value.strip().casefold()
        aliases = SEVERITY_ALIASES.get(normalized, normalized)
        if aliases not in SEVERITY_RANKS:
            raise ValueError(f"Unknown severity: {value}")
        return cls(aliases)

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "rank": self.rank, "label": self.label}


SEVERITY_ORDER: tuple[SeverityName, ...] = (
    "info",
    "low",
    "medium",
    "high",
    "critical",
)
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
REPORT_FORMATS: tuple[ReportFormat, ...] = ("markdown", "html", "json", "print")
EVIDENCE_KINDS: tuple[EvidenceKind, ...] = (
    "note",
    "command",
    "artifact",
    "observation",
    "reference",
)


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """A citable unit of source material attached to a finding."""

    identifier: str
    title: str
    content: str
    kind: EvidenceKind = "note"
    source_id: int | None = None
    source_path: str = ""
    source_updated_at: str = ""
    locator: str = ""
    excerpt: str = ""
    sensitive: bool = False

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Evidence identifier cannot be empty")
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(f"Unknown evidence kind: {self.kind}")

    @property
    def citation(self) -> str:
        if self.locator:
            return f"{self.title} ({self.locator})"
        if self.source_path:
            return f"{self.title} — {self.source_path}"
        return self.title

    def as_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "content": self.content,
            "kind": self.kind,
            "source_id": self.source_id,
            "source_path": self.source_path,
            "source_updated_at": self.source_updated_at,
            "locator": self.locator,
            "excerpt": self.excerpt,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """A single security observation with evidence and remediation notes."""

    identifier: str
    title: str
    summary: str = ""
    severity: SeverityName = "medium"
    status: FindingStatus = "open"
    category: str = ""
    tags: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    impact: str = ""
    recommendation: str = ""
    references: tuple[str, ...] = ()
    confidence: float = 1.0
    cvss: str = ""
    cwe: str = ""
    affected: str = ""

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Finding identifier cannot be empty")
        if not self.title.strip():
            raise ValueError("Finding title cannot be empty")
        Severity.parse(self.severity)
        if self.status not in FINDING_STATUSES:
            raise ValueError(f"Unknown finding status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def severity_level(self) -> Severity:
        return Severity.parse(self.severity)

    @property
    def is_open(self) -> bool:
        return self.status in ("open", "confirmed")

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    def with_evidence(self, evidence: tuple[EvidenceRef, ...]) -> Finding:
        return replace(self, evidence=evidence)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "status": self.status,
            "category": self.category,
            "tags": list(self.tags),
            "evidence": [item.as_dict() for item in self.evidence],
            "impact": self.impact,
            "recommendation": self.recommendation,
            "references": list(self.references),
            "confidence": self.confidence,
            "cvss": self.cvss,
            "cwe": self.cwe,
            "affected": self.affected,
        }


@dataclass(frozen=True, slots=True)
class ReportSection:
    """A node in a report outline."""

    identifier: str
    title: str
    kind: str = "text"
    body: str = ""
    summary: str = ""
    findings: tuple[Finding, ...] = ()
    children: tuple[ReportSection, ...] = ()
    order: int = 0
    level: int = 1
    include_toc: bool = True
    page_break_before: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Section identifier cannot be empty")
        if not self.title.strip():
            raise ValueError("Section title cannot be empty")
        if self.level < 1 or self.level > 6:
            raise ValueError("Section level must be between 1 and 6")

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def is_container(self) -> bool:
        return bool(self.children) or self.kind in ("group", "appendix")

    def walk(self) -> tuple[ReportSection, ...]:
        """Return this section and its descendants in depth-first order."""
        result: list[ReportSection] = [self]
        for child in self.children:
            result.extend(child.walk())
        return tuple(result)

    def all_findings(self) -> tuple[Finding, ...]:
        return tuple(finding for section in self.walk() for finding in section.findings)

    def with_children(self, children: tuple[ReportSection, ...]) -> ReportSection:
        return replace(self, children=children)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "kind": self.kind,
            "body": self.body,
            "summary": self.summary,
            "findings": [finding.as_dict() for finding in self.findings],
            "children": [child.as_dict() for child in self.children],
            "order": self.order,
            "level": self.level,
            "include_toc": self.include_toc,
            "page_break_before": self.page_break_before,
            "metadata": dict(self.metadata),
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
        name = Severity.parse(severity).value
        values = self.as_dict()
        values[name] = int(values[name]) + 1
        return SeverityCounts(**values)

    def total(self) -> int:
        return sum(self.as_dict().values())

    def weighted(self) -> int:
        values = self.as_dict()
        return sum(SEVERITY_RANKS[name] * int(count) for name, count in values.items())

    def highest(self) -> SeverityName:
        values = self.as_dict()
        for name in reversed(SEVERITY_ORDER):
            if int(values[name]) > 0:
                return name
        return "info"

    def as_dict(self) -> dict[str, int]:
        return {
            "info": self.info,
            "low": self.low,
            "medium": self.medium,
            "high": self.high,
            "critical": self.critical,
        }


@dataclass(frozen=True, slots=True)
class InclusionRule:
    """Declarative rule used to include or exclude candidate findings."""

    name: str
    action: Literal["include", "exclude"]
    tags: tuple[str, ...] = ()
    severities: tuple[SeverityName, ...] = ()
    statuses: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    minimum_confidence: float = 0.0
    path_prefix: str = ""
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.action not in ("include", "exclude"):
            raise ValueError(f"Unknown rule action: {self.action}")
        for severity in self.severities:
            Severity.parse(severity)
        for status in self.statuses:
            if status not in (*FINDING_STATUSES, *NOTE_STATUSES):
                raise ValueError(f"Unknown status: {status}")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")

    @property
    def is_exclusion(self) -> bool:
        return self.action == "exclude"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "action": self.action,
            "tags": list(self.tags),
            "severities": list(self.severities),
            "statuses": list(self.statuses),
            "categories": list(self.categories),
            "minimum_confidence": self.minimum_confidence,
            "path_prefix": self.path_prefix,
            "identifier": self.identifier,
        }


@dataclass(frozen=True, slots=True)
class RedactionRule:
    """One replacement rule applied before a report is rendered."""

    name: str
    pattern: str
    replacement: str = "[REDACTED]"
    enabled: bool = True
    priority: int = 0
    flags: tuple[str, ...] = ("ignorecase",)
    scope: Literal["all", "body", "evidence", "title"] = "all"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Redaction rule needs a name")
        if not self.pattern.strip():
            raise ValueError("Redaction rule needs a pattern")
        if self.scope not in ("all", "body", "evidence", "title"):
            raise ValueError(f"Unknown redaction scope: {self.scope}")

    def disabled(self) -> bool:
        return not self.enabled

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pattern": self.pattern,
            "replacement": self.replacement,
            "enabled": self.enabled,
            "priority": self.priority,
            "flags": list(self.flags),
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Text after redaction plus an audit of applied rules."""

    text: str
    applied: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "applied": list(self.applied),
            "counts": dict(self.counts),
        }


@dataclass(frozen=True, slots=True)
class ReportConfig:
    """All user-controlled inputs required to build one report."""

    title: str
    template: str = "engagement"
    client: str = ""
    author: str = ""
    classification: str = "internal"
    scope: tuple[str, ...] = ()
    generated_at: str = ""
    introduction: str = ""
    conclusion: str = ""
    sections: tuple[ReportSection, ...] = ()
    findings: tuple[Finding, ...] = ()
    rules: tuple[InclusionRule, ...] = ()
    redactions: tuple[RedactionRule, ...] = ()
    tags: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    minimum_severity: SeverityName = "info"
    include_empty_sections: bool = False
    include_evidence: bool = True
    include_appendices: bool = True
    page_size: str = "a4"
    orientation: str = "portrait"
    print_profile: str = "standard"
    print_cover: bool = True
    print_toc: bool = True
    redact_sensitive: bool = True
    notes: str = ""

    def fingerprint(self) -> str:
        """Return a stable digest of every build-affecting field."""
        return canonical_json(self.as_dict())

    def finding_count(self) -> int:
        return len(self.findings) + sum(section.finding_count for section in self.sections)

    def confidence_invalid(self) -> bool:
        return any(
            finding.confidence < 0.0 or finding.confidence > 1.0 for finding in self.all_findings()
        )

    def all_findings(self) -> tuple[Finding, ...]:
        values = list(self.findings)
        for section in self.sections:
            values.extend(section.all_findings())
        return tuple(values)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "template": self.template,
            "client": self.client,
            "author": self.author,
            "classification": self.classification,
            "scope": list(self.scope),
            "generated_at": self.generated_at,
            "introduction": self.introduction,
            "conclusion": self.conclusion,
            "sections": [section.as_dict() for section in self.sections],
            "findings": [finding.as_dict() for finding in self.findings],
            "rules": [rule.as_dict() for rule in self.rules],
            "redactions": [rule.as_dict() for rule in self.redactions],
            "tags": list(self.tags),
            "statuses": list(self.statuses),
            "minimum_severity": self.minimum_severity,
            "include_empty_sections": self.include_empty_sections,
            "include_evidence": self.include_evidence,
            "include_appendices": self.include_appendices,
            "page_size": self.page_size,
            "orientation": self.orientation,
            "print_profile": self.print_profile,
            "print_cover": self.print_cover,
            "print_toc": self.print_toc,
            "redact_sensitive": self.redact_sensitive,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ReportTemplate:
    """A reusable outline and set of default configuration values."""

    key: str
    name: str
    description: str
    sections: tuple[ReportSection, ...]
    default_title: str = "Security Assessment"
    classification: str = "internal"
    tags: tuple[str, ...] = ()
    print_profile: str = "standard"
    glyph: str = "◆"

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Template key cannot be empty")
        if not self.sections:
            raise ValueError(f"Template '{self.key}' needs at least one section")

    def section_keys(self) -> tuple[str, ...]:
        return tuple(section.identifier for root in self.sections for section in root.walk())

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "sections": [section.as_dict() for section in self.sections],
            "default_title": self.default_title,
            "classification": self.classification,
            "tags": list(self.tags),
            "print_profile": self.print_profile,
            "glyph": self.glyph,
        }


@dataclass(frozen=True, slots=True)
class ReportDocument:
    """A fully built, deterministic report ready for rendering."""

    config: ReportConfig
    sections: tuple[ReportSection, ...]
    findings: tuple[Finding, ...]
    severity: SeverityCounts
    title: str
    template: str
    generated_at: str
    source_digest: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def identifier(self) -> str:
        return slugify(self.title) or "report"

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def all_sections(self) -> tuple[ReportSection, ...]:
        return tuple(section for root in self.sections for section in root.walk())

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.as_dict(),
            "sections": [section.as_dict() for section in self.sections],
            "findings": [finding.as_dict() for finding in self.findings],
            "finding_count": self.finding_count,
            "severity": self.severity.as_dict(),
            "title": self.title,
            "template": self.template,
            "generated_at": self.generated_at,
            "source_digest": self.source_digest,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class RenderedReport:
    """Rendered output plus its format and reproducibility metadata."""

    format: ReportFormat
    content: str
    filename: str
    mime: str
    manifest: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "content": self.content,
            "filename": self.filename,
            "mime": self.mime,
            "manifest": dict(self.manifest),
        }


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A validation problem attached to a report path."""

    code: str
    message: str
    path: str = ""
    severity: Literal["error", "warning"] = "error"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class SourceNote:
    """A vault note snapshot used as report source material."""

    identifier: int
    title: str
    path: str
    content: str
    tags: tuple[str, ...] = ()
    status: str = "todo"
    severity: SeverityName = "info"
    category: str = ""
    target: str = ""
    flag: str = ""
    updated_at: str = ""
    sensitive: bool = False

    @property
    def evidence(self) -> EvidenceRef:
        return EvidenceRef(
            identifier=f"note-{self.identifier}",
            title=self.title,
            content=self.content,
            kind="note",
            source_id=self.identifier,
            source_path=self.path,
            source_updated_at=self.updated_at,
            sensitive=self.sensitive,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "path": self.path,
            "content": self.content,
            "tags": list(self.tags),
            "status": self.status,
            "severity": self.severity,
            "category": self.category,
            "target": self.target,
            "flag": self.flag,
            "updated_at": self.updated_at,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True, slots=True)
class ReportSource:
    """A deterministic snapshot of the vault at report build time."""

    notes: tuple[SourceNote, ...] = ()
    generated_at: str = ""
    vault_name: str = ""
    schema_version: int = 0
    revision: str = ""

    def by_id(self, identifier: int) -> SourceNote | None:
        return next((note for note in self.notes if note.identifier == identifier), None)

    def by_tag(self, tag: str) -> tuple[SourceNote, ...]:
        needle = tag.casefold()
        return tuple(
            note for note in self.notes if needle in {value.casefold() for value in note.tags}
        )

    def digest(self) -> str:
        return canonical_json(
            {
                "notes": [note.as_dict() for note in self.notes],
                "schema_version": self.schema_version,
                "revision": self.revision,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "notes": [note.as_dict() for note in self.notes],
            "generated_at": self.generated_at,
            "vault_name": self.vault_name,
            "schema_version": self.schema_version,
            "revision": self.revision,
        }


def empty_counts() -> SeverityCounts:
    """Return a zeroed severity counter."""
    return SeverityCounts()


def make_finding(
    title: str,
    *,
    severity: str = "medium",
    identifier: str = "",
    **values: Any,
) -> Finding:
    """Create a finding with a stable identifier derived from its title."""
    return Finding(
        identifier=identifier or slugify(title),
        title=title,
        severity=Severity.parse(severity).value,
        **values,
    )


def make_section(title: str, **values: Any) -> ReportSection:
    """Create a section with a stable identifier derived from its title."""
    return ReportSection(identifier=slugify(title), title=title, **values)
