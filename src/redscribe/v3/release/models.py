"""Data contracts shared by the V3 release toolkit.

Every type in this module is immutable, JSON-serialisable, and free of I/O.
Feature branches may add fields to their own payloads, but the shapes below are
the stable currency between the golden-path runner, the smoke suite, the
hardening gates, and the generated release documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

RELEASE_VERSION = "3.0.0"
RELEASE_NAMESPACE = "release"

RELEASE_ACTIONS: tuple[str, ...] = (
    "manifest",
    "golden",
    "smoke",
    "gates",
    "gate_audit",
    "docs",
    "changelog",
    "migration_notes",
    "readiness",
    "onboarding",
    "showcase",
    "polish",
)

FRONTEND_SURFACES: tuple[str, ...] = (
    "onboarding-flow",
    "empty-first-run",
    "design-system-showcase",
    "iconography-label-audit",
    "animation-audit",
    "responsive-polish-checklist",
)


class ReleasePhase(str, Enum):
    """Ordered phases of the golden path covered by the release suite."""

    CAPTURE = "capture"
    FINDING = "finding"
    EVIDENCE = "evidence"
    REPORT = "report"
    EXPORT = "export"
    IMPORT = "import"
    MERGE = "merge"

    @classmethod
    def ordered(cls) -> tuple[ReleasePhase, ...]:
        """Return phases in execution order."""
        return (
            cls.CAPTURE,
            cls.FINDING,
            cls.EVIDENCE,
            cls.REPORT,
            cls.EXPORT,
            cls.IMPORT,
            cls.MERGE,
        )

    @property
    def position(self) -> int:
        """Zero-based position in the golden path."""
        return self.ordered().index(self)

    @property
    def label(self) -> str:
        """Human-friendly phase label."""
        return self.value.replace("_", " ").title()


class CheckSeverity(str, Enum):
    """Impact of a failed smoke check or polish item."""

    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Numeric severity for sorting."""
        return {
            CheckSeverity.BLOCKER: 4,
            CheckSeverity.MAJOR: 3,
            CheckSeverity.MINOR: 2,
            CheckSeverity.INFO: 1,
        }[self]


class GateStatus(str, Enum):
    """Outcome of a hardening gate."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

    @property
    def ok(self) -> bool:
        """Whether the gate permits a release."""
        return self is not GateStatus.FAIL


@dataclass(frozen=True, slots=True)
class GateDefinition:
    """Static description of one final hardening gate."""

    gate_id: str
    title: str
    severity: str = "major"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"id": self.gate_id, "title": self.title, "severity": self.severity}


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    """One observable assertion inside a golden-path scenario."""

    phase: ReleasePhase
    name: str
    detail: str
    expected: str
    actual: str
    passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "phase": self.phase.value,
            "name": self.name,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Result of one deterministic scenario run."""

    name: str
    description: str
    steps: tuple[ScenarioStep, ...]

    @property
    def passed_count(self) -> int:
        """Number of passing steps."""
        return sum(1 for step in self.steps if step.passed)

    @property
    def failed_count(self) -> int:
        """Number of failing steps."""
        return len(self.steps) - self.passed_count

    @property
    def ok(self) -> bool:
        """Whether every step passed."""
        return bool(self.steps) and self.failed_count == 0

    @property
    def phases(self) -> tuple[str, ...]:
        """Distinct phase values touched by the scenario."""
        return tuple(dict.fromkeys(step.phase.value for step in self.steps))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "description": self.description,
            "ok": self.ok,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "phases": list(self.phases),
            "steps": [step.as_dict() for step in self.steps],
        }


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    """One release smoke assertion."""

    check_id: str
    title: str
    severity: CheckSeverity
    passed: bool
    expected: str
    actual: str
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.check_id,
            "title": self.title,
            "severity": self.severity.value,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class SmokeReport:
    """Aggregate of the release smoke suite."""

    checks: tuple[SmokeCheck, ...]

    @property
    def passed_count(self) -> int:
        """Number of passing checks."""
        return sum(1 for check in self.checks if check.passed)

    @property
    def failed_count(self) -> int:
        """Number of failing checks."""
        return len(self.checks) - self.passed_count

    @property
    def ok(self) -> bool:
        """Whether the suite is clean."""
        return bool(self.checks) and self.failed_count == 0

    def failures(self) -> tuple[SmokeCheck, ...]:
        """Return failing checks in stable order."""
        return tuple(check for check in self.checks if not check.passed)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ok": self.ok,
            "total": len(self.checks),
            "passed": self.passed_count,
            "failed": self.failed_count,
            "checks": [check.as_dict() for check in self.checks],
        }

    def markdown(self) -> str:
        """Render a compact Markdown table."""
        lines = [
            "| Check | Severity | Result | Expected |",
            "| --- | --- | --- | --- |",
        ]
        for check in self.checks:
            result = "PASS" if check.passed else "FAIL"
            lines.append(
                f"| `{check.check_id}` | {check.severity.value} | {result} | {check.expected} |"
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of one final hardening gate."""

    gate_id: str
    title: str
    status: GateStatus
    detail: str
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.gate_id,
            "title": self.title,
            "status": self.status.value,
            "detail": self.detail,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class GateReport:
    """Aggregate of final release gates."""

    results: tuple[GateResult, ...]

    @property
    def ok(self) -> bool:
        """Whether no gate hard-fails."""
        return all(result.status.ok for result in self.results)

    @property
    def failures(self) -> tuple[GateResult, ...]:
        """Return hard failures in stable order."""
        return tuple(result for result in self.results if result.status is GateStatus.FAIL)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ok": self.ok,
            "passed": sum(1 for result in self.results if result.status is GateStatus.PASS),
            "warnings": sum(1 for result in self.results if result.status is GateStatus.WARN),
            "failed": len(self.failures),
            "gates": [result.as_dict() for result in self.results],
        }

    def markdown(self) -> str:
        """Render a compact Markdown table."""
        lines = ["| Gate | Status | Detail |", "| --- | --- | --- |"]
        for result in self.results:
            lines.append(f"| `{result.gate_id}` | {result.status.value} | {result.detail} |")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ChangelogEntry:
    """One release-note row grouped by category."""

    version: str
    category: str
    title: str
    detail: str
    reference: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "version": self.version,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class MigrationNote:
    """One documented upgrade step."""

    from_version: str
    to_version: str
    title: str
    action: str
    automated: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "from": self.from_version,
            "to": self.to_version,
            "title": self.title,
            "action": self.action,
            "automated": self.automated,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class DocSection:
    """One generated documentation section."""

    section_id: str
    title: str
    body: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"id": self.section_id, "title": self.title, "body": self.body}


@dataclass(frozen=True, slots=True)
class DocBundle:
    """Ordered documentation sections with a deterministic renderer."""

    title: str
    version: str
    sections: tuple[DocSection, ...]

    def render(self) -> str:
        """Render the full document."""
        parts = [f"# {self.title}", "", f"Release: `{self.version}`", ""]
        for section in self.sections:
            parts.extend([f"## {section.title}", "", section.body.strip(), ""])
        return "\n".join(parts).rstrip() + "\n"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "title": self.title,
            "version": self.version,
            "sections": [section.as_dict() for section in self.sections],
        }


@dataclass(frozen=True, slots=True)
class OnboardingSpec:
    """One step of the first-run onboarding flow."""

    step_id: str
    title: str
    description: str
    control: str
    hint: str
    required: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.step_id,
            "title": self.title,
            "description": self.description,
            "control": self.control,
            "hint": self.hint,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class EmptyStateSpec:
    """Copy and action for an empty or first-run surface."""

    surface: str
    title: str
    body: str
    action_label: str
    action_route: str
    icon: str = "file-text"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "surface": self.surface,
            "title": self.title,
            "body": self.body,
            "action_label": self.action_label,
            "action_route": self.action_route,
            "icon": self.icon,
        }


@dataclass(frozen=True, slots=True)
class PolishCheck:
    """A release-polish checklist item for one UI surface."""

    check_id: str
    area: str
    label: str
    detail: str
    severity: CheckSeverity = CheckSeverity.MINOR
    done: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.check_id,
            "area": self.area,
            "label": self.label,
            "detail": self.detail,
            "severity": self.severity.value,
            "done": self.done,
        }


@dataclass(frozen=True, slots=True)
class AnimationAudit:
    """Reduced-motion audit record for one animated surface."""

    surface: str
    property_name: str
    duration_token: str
    reduced_motion_safe: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "surface": self.surface,
            "property": self.property_name,
            "duration_token": self.duration_token,
            "reduced_motion_safe": self.reduced_motion_safe,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ShowcaseEntry:
    """Design-system v3 showcase row."""

    token: str
    label: str
    kind: str
    preview: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "token": self.token,
            "label": self.label,
            "kind": self.kind,
            "preview": self.preview,
        }


def phase_values() -> tuple[str, ...]:
    """Return phase identifiers in execution order."""
    return tuple(phase.value for phase in ReleasePhase.ordered())
