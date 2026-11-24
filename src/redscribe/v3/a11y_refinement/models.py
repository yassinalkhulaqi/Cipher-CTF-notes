"""Typed contracts for the V3 accessibility and i18n refinement layer.

B12 does not redefine the V2 accessibility models. It composes them with the
V3 API envelope and adds the data needed for WCAG 2.2 audits, contrast
automation, locale formatting, RTL layout metadata, keyboard maps, and
preference synchronization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v2.a11y.models import PreferenceSnapshot, WcagLevel


class RuleScope(str, Enum):
    """The part of a surface a WCAG rule applies to."""

    DOCUMENT = "document"
    FOCUS = "focus"
    POINTER = "pointer"
    CONTENT = "content"
    FORM = "form"
    LOCALIZATION = "localization"


class TargetSizeStatus(str, Enum):
    """Result of measuring an interactive target."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class SyncStrategy(str, Enum):
    """Conflict policy used when two preference records differ."""

    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    MERGE = "merge"
    REJECT = "reject"


class MotionMode(str, Enum):
    """Unified theme/motion control values."""

    FULL = "full"
    REDUCED = "reduced"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class WcagRule:
    """One deterministic WCAG 2.2 rule supported by the refinement layer."""

    rule_id: str
    criterion: str
    title: str
    level: WcagLevel
    scope: RuleScope
    description: str
    remediation: str
    automated: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe rule description."""
        return {
            "id": self.rule_id,
            "criterion": self.criterion,
            "title": self.title,
            "level": self.level.value,
            "scope": self.scope.value,
            "description": self.description,
            "remediation": self.remediation,
            "automated": self.automated,
        }


@dataclass(frozen=True, slots=True)
class SurfaceSpec:
    """A declarative description of one V3 UI surface."""

    name: str
    label: str
    level: WcagLevel = WcagLevel.AA
    locale: str = "en"
    focus_obscured: str = "none"
    focus_indicator_width: int = 2
    focus_indicator_contrast: float = 3.0
    target_size: int = 32
    drag_only: bool = False
    has_help: bool = True
    repeated_entry: bool = False
    auth_captcha: str = "none"
    non_text_contrast: float = 3.0
    hover_content: bool = False
    keyboard_reachable: bool = True
    screen_reader_labels: bool = True
    tiles: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe surface description."""
        return {
            "name": self.name,
            "label": self.label,
            "level": self.level.value,
            "locale": self.locale,
            "focus_obscured": self.focus_obscured,
            "focus_indicator_width": self.focus_indicator_width,
            "focus_indicator_contrast": self.focus_indicator_contrast,
            "target_size": self.target_size,
            "drag_only": self.drag_only,
            "has_help": self.has_help,
            "repeated_entry": self.repeated_entry,
            "auth_captcha": self.auth_captcha,
            "non_text_contrast": self.non_text_contrast,
            "hover_content": self.hover_content,
            "keyboard_reachable": self.keyboard_reachable,
            "screen_reader_labels": self.screen_reader_labels,
            "tiles": list(self.tiles),
        }


@dataclass(frozen=True, slots=True)
class RuleFinding:
    """One finding emitted by a WCAG 2.2 rule."""

    rule_id: str
    criterion: str
    severity: str
    target: str
    message: str
    remediation: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe finding."""
        return {
            "rule": self.rule_id,
            "criterion": self.criterion,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
            "remediation": self.remediation,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class AuditRun:
    """The result of auditing one surface against a rule catalog."""

    surface: str
    level: WcagLevel
    findings: tuple[RuleFinding, ...] = ()
    passed_rules: tuple[str, ...] = ()
    checked: int = 0
    score: float = 100.0

    @property
    def passed(self) -> bool:
        """Return whether the surface has no blocking findings."""
        blocking = {"serious", "critical", "moderate"}
        return not any(item.severity in blocking for item in self.findings)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe audit run."""
        return {
            "surface": self.surface,
            "level": self.level.value,
            "findings": [item.as_dict() for item in self.findings],
            "passed_rules": list(self.passed_rules),
            "checked": self.checked,
            "score": round(self.score, 1),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ContrastTarget:
    """A foreground/background pair that must pass an automated check."""

    name: str
    foreground: str
    background: str
    font_size: float = 16.0
    bold: bool = False
    graphical: bool = False
    level: WcagLevel = WcagLevel.AA

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe target."""
        return {
            "name": self.name,
            "foreground": self.foreground,
            "background": self.background,
            "font_size": self.font_size,
            "bold": self.bold,
            "graphical": self.graphical,
            "level": self.level.value,
        }


@dataclass(frozen=True, slots=True)
class ContrastFix:
    """An automatically computed color repair for one target."""

    name: str
    before_ratio: float
    after_ratio: float
    required: float
    foreground: str
    background: str
    direction: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe fix."""
        return {
            "name": self.name,
            "before": round(self.before_ratio, 2),
            "after": round(self.after_ratio, 2),
            "required": round(self.required, 2),
            "foreground": self.foreground,
            "background": self.background,
            "direction": self.direction,
        }


@dataclass(frozen=True, slots=True)
class ContrastAutomationReport:
    """Aggregated results of an automated contrast pass."""

    pairs: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    fixes: tuple[ContrastFix, ...] = ()
    suggestions: tuple[str, ...] = ()
    level: WcagLevel = WcagLevel.AA
    score: float = 100.0

    @property
    def passed(self) -> bool:
        """Return whether every checked pair meets its threshold."""
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe report."""
        return {
            "pairs": [dict(item) for item in self.pairs],
            "failures": [dict(item) for item in self.failures],
            "fixes": [item.as_dict() for item in self.fixes],
            "suggestions": list(self.suggestions),
            "level": self.level.value,
            "score": round(self.score, 1),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class FormatRequest:
    """A locale-aware formatting request from a V3 surface."""

    locale: str
    kind: str
    value: Any
    options: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe request."""
        return {
            "locale": self.locale,
            "kind": self.kind,
            "value": self.value,
            "options": dict(self.options),
        }


@dataclass(frozen=True, slots=True)
class FormatResult:
    """A formatted value with the direction needed to display it."""

    locale: str
    kind: str
    text: str
    direction: str
    bidi_isolated: bool = False
    fallback: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe result."""
        return {
            "locale": self.locale,
            "kind": self.kind,
            "text": self.text,
            "direction": self.direction,
            "bidi_isolated": self.bidi_isolated,
            "fallback": self.fallback,
        }


@dataclass(frozen=True, slots=True)
class PaneLayout:
    """Logical-to-physical layout metadata for one pane."""

    pane: str
    direction: str
    css_class: str
    sides: dict[str, str]
    mirror_icons: tuple[str, ...]
    ordered_regions: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe layout description."""
        return {
            "pane": self.pane,
            "direction": self.direction,
            "css_class": self.css_class,
            "sides": dict(self.sides),
            "mirror_icons": list(self.mirror_icons),
            "ordered_regions": list(self.ordered_regions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class KeyboardBinding:
    """One exported keyboard binding with display metadata."""

    action: str
    keys: tuple[str, ...]
    label: str
    group: str
    scope: str
    display: str
    enabled: bool = True
    sequence: int = 0
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe binding."""
        return {
            "action": self.action,
            "keys": list(self.keys),
            "label": self.label,
            "group": self.group,
            "scope": self.scope,
            "display": self.display,
            "enabled": self.enabled,
            "sequence": self.sequence,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class KeyboardMap:
    """A complete keyboard map export for all V3 surfaces."""

    locale: str
    platform: str
    bindings: tuple[KeyboardBinding, ...]
    groups: dict[str, tuple[str, ...]]
    conflicts: tuple[dict[str, Any], ...] = ()
    coverage: dict[str, int] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """Return whether the map has bindings and no conflicts."""
        return bool(self.bindings) and not self.conflicts

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe keyboard map."""
        return {
            "locale": self.locale,
            "platform": self.platform,
            "bindings": [item.as_dict() for item in self.bindings],
            "groups": {key: list(value) for key, value in self.groups.items()},
            "conflicts": [dict(item) for item in self.conflicts],
            "coverage": dict(self.coverage),
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class PreferenceSyncRecord:
    """A versioned preference record shared across V3 features."""

    profile: str
    snapshot: PreferenceSnapshot
    revision: int = 1
    source: str = "local"
    checksum: str = ""
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe sync record."""
        return {
            "profile": self.profile,
            "revision": self.revision,
            "source": self.source,
            "checksum": self.checksum,
            "tags": list(self.tags),
            "preferences": self.snapshot.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SyncReport:
    """The outcome of synchronizing two preference records."""

    strategy: SyncStrategy
    applied: bool
    record: PreferenceSyncRecord
    changes: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe sync report."""
        return {
            "strategy": self.strategy.value,
            "applied": self.applied,
            "record": self.record.as_dict(),
            "changes": list(self.changes),
            "conflicts": list(self.conflicts),
            "warnings": list(self.warnings),
        }


__all__ = [
    "AuditRun",
    "ContrastAutomationReport",
    "ContrastFix",
    "ContrastTarget",
    "FormatRequest",
    "FormatResult",
    "KeyboardBinding",
    "KeyboardMap",
    "MotionMode",
    "PaneLayout",
    "PreferenceSyncRecord",
    "RuleFinding",
    "RuleScope",
    "SurfaceSpec",
    "SyncReport",
    "SyncStrategy",
    "TargetSizeStatus",
    "WcagRule",
]
