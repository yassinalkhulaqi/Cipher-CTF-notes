"""Shared data models for the accessibility, i18n, and theme features."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Issue severity used across audits and validations."""

    INFO = "info"
    MINOR = "minor"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"


class WcagLevel(str, Enum):
    """WCAG conformance targets."""

    A = "A"
    AA = "AA"
    AAA = "AAA"


class Direction(str, Enum):
    """Text direction for a locale or element."""

    LTR = "ltr"
    RTL = "rtl"
    AUTO = "auto"


class FocusMode(str, Enum):
    """Focus behavior for a shortcut."""

    GLOBAL = "global"
    EDITOR = "editor"
    SIDEBAR = "sidebar"
    DIALOG = "dialog"
    READING = "reading"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.MINOR: 1,
    Severity.MODERATE: 2,
    Severity.SERIOUS: 3,
    Severity.CRITICAL: 4,
}

WCAG_RANK: dict[WcagLevel, int] = {
    WcagLevel.A: 1,
    WcagLevel.AA: 2,
    WcagLevel.AAA: 3,
}


def severity_rank(value: str | Severity) -> int:
    """Return the comparative rank of a severity string."""
    try:
        return SEVERITY_RANK[Severity(value)]
    except ValueError:
        return 0


def wcag_rank(value: str | WcagLevel) -> int:
    """Return the comparative rank of a WCAG level."""
    try:
        return WCAG_RANK[coerce_wcag_level(value)]
    except ValueError:
        return 0


def coerce_wcag_level(value: str | WcagLevel) -> WcagLevel:
    """Normalize a string or enum value into a :class:`WcagLevel`."""
    if isinstance(value, WcagLevel):
        return value
    return WcagLevel(str(value).upper())


def _string_list(values: tuple[str, ...] | list[str]) -> list[str]:
    return [str(value) for value in values]


@dataclass(frozen=True, slots=True)
class ElementNode:
    """A simplified DOM element used by static accessibility checks."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    text: str = ""
    children: tuple[ElementNode, ...] = ()
    visible: bool = True
    path: str = ""

    @property
    def normalized_tag(self) -> str:
        return self.tag.lower().strip()

    @property
    def role(self) -> str:
        return self.attrs.get("role", "").lower().strip()

    @property
    def element_id(self) -> str:
        return self.attrs.get("id", "")

    def attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def has_attr(self, name: str) -> bool:
        return name in self.attrs and self.attrs[name] != ""

    def descendants(self) -> list[ElementNode]:
        result: list[ElementNode] = []
        for child in self.children:
            result.append(child)
            result.extend(child.descendants())
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "attrs": dict(self.attrs),
            "text": self.text,
            "children": [child.as_dict() for child in self.children],
            "visible": self.visible,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class AuditIssue:
    """One accessibility finding with a stable rule identifier."""

    rule: str
    severity: Severity
    message: str
    target: str = ""
    wcag: str = ""
    remediation: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "target": self.target,
            "wcag": self.wcag,
            "remediation": self.remediation,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Aggregated accessibility audit result."""

    issues: tuple[AuditIssue, ...] = ()
    checked_elements: int = 0
    passed_rules: tuple[str, ...] = ()
    score: float = 100.0
    level: WcagLevel = WcagLevel.AA
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        threshold = severity_rank(Severity.MODERATE)
        return all(severity_rank(issue.severity) < threshold for issue in self.issues)

    def issues_for(self, severity: str | Severity) -> tuple[AuditIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == Severity(severity))

    def as_dict(self) -> dict[str, Any]:
        return {
            "issues": [issue.as_dict() for issue in self.issues],
            "checked_elements": self.checked_elements,
            "passed_rules": _string_list(self.passed_rules),
            "score": round(self.score, 1),
            "level": self.level.value,
            "passed": self.passed,
            "summary": dict(self.summary),
        }


@dataclass(frozen=True, slots=True)
class ContrastPair:
    """A foreground/background color pair and its measured ratio."""

    name: str
    foreground: str
    background: str
    ratio: float
    font_size: float = 16.0
    bold: bool = False
    large_text: bool = False
    required: float = 4.5
    passed: bool = False
    level: WcagLevel = WcagLevel.AA

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "foreground": self.foreground,
            "background": self.background,
            "ratio": round(self.ratio, 2),
            "font_size": self.font_size,
            "bold": self.bold,
            "large_text": self.large_text,
            "required": self.required,
            "passed": self.passed,
            "level": self.level.value,
        }


@dataclass(frozen=True, slots=True)
class ContrastReport:
    """Contrast validation result for a set of color pairs."""

    pairs: tuple[ContrastPair, ...] = ()
    failures: tuple[ContrastPair, ...] = ()
    score: float = 100.0
    target: WcagLevel = WcagLevel.AA
    suggestions: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "pairs": [pair.as_dict() for pair in self.pairs],
            "failures": [pair.as_dict() for pair in self.failures],
            "score": round(self.score, 1),
            "target": self.target.value,
            "passed": self.passed,
            "suggestions": _string_list(self.suggestions),
        }


@dataclass(frozen=True, slots=True)
class FocusStep:
    """One element in a computed tab order."""

    order: int
    target: str
    tag: str
    tab_index: int
    description: str = ""
    hidden: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "target": self.target,
            "tag": self.tag,
            "tab_index": self.tab_index,
            "description": self.description,
            "hidden": self.hidden,
        }


@dataclass(frozen=True, slots=True)
class FocusReport:
    """Focus order analysis result."""

    steps: tuple[FocusStep, ...] = ()
    issues: tuple[AuditIssue, ...] = ()
    focusable_count: int = 0
    positive_tabindex_count: int = 0
    has_skip_link: bool = False
    score: float = 100.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "steps": [step.as_dict() for step in self.steps],
            "issues": [issue.as_dict() for issue in self.issues],
            "focusable_count": self.focusable_count,
            "positive_tabindex_count": self.positive_tabindex_count,
            "has_skip_link": self.has_skip_link,
            "score": round(self.score, 1),
        }


@dataclass(frozen=True, slots=True)
class AriaIssue:
    """One ARIA validation finding."""

    rule: str
    message: str
    target: str = ""
    severity: Severity = Severity.MODERATE
    remediation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "target": self.target,
            "severity": self.severity.value,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class AriaReport:
    """ARIA validation result for a tree of elements."""

    issues: tuple[AriaIssue, ...] = ()
    roles_seen: tuple[str, ...] = ()
    accessible_names: dict[str, str] = field(default_factory=dict)
    checked: int = 0

    @property
    def passed(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "issues": [issue.as_dict() for issue in self.issues],
            "roles_seen": _string_list(self.roles_seen),
            "accessible_names": dict(self.accessible_names),
            "checked": self.checked,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class Shortcut:
    """A registered keyboard shortcut."""

    action: str
    keys: tuple[str, ...]
    label: str
    scope: FocusMode = FocusMode.GLOBAL
    description: str = ""
    enabled: bool = True
    sequence: int = 0

    @property
    def binding(self) -> str:
        return "+".join(self.keys)

    def matches(self, pressed: tuple[str, ...]) -> bool:
        normalized = tuple(_normalize_key(key) for key in pressed)
        expected = tuple(_normalize_key(key) for key in self.keys)
        return normalized == expected

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "keys": _string_list(self.keys),
            "label": self.label,
            "scope": self.scope.value,
            "description": self.description,
            "enabled": self.enabled,
            "sequence": self.sequence,
            "binding": self.binding,
        }


def _normalize_key(value: str) -> str:
    aliases = {
        "control": "ctrl",
        "command": "meta",
        "cmd": "meta",
        "escape": "esc",
        "arrowup": "up",
        "arrowdown": "down",
        "arrowleft": "left",
        "arrowright": "right",
        " ": "space",
    }
    lowered = value.strip().lower()
    return aliases.get(lowered, lowered)


@dataclass(frozen=True, slots=True)
class ShortcutConflict:
    """Two shortcuts that cannot coexist in one context."""

    first: str
    second: str
    binding: str
    scope: FocusMode
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "first": self.first,
            "second": self.second,
            "binding": self.binding,
            "scope": self.scope.value,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ShortcutReport:
    """Validation result for a shortcut registry."""

    shortcuts: tuple[Shortcut, ...] = ()
    conflicts: tuple[ShortcutConflict, ...] = ()
    unknown_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.conflicts and not self.unknown_keys

    def as_dict(self) -> dict[str, Any]:
        return {
            "shortcuts": [shortcut.as_dict() for shortcut in self.shortcuts],
            "conflicts": [conflict.as_dict() for conflict in self.conflicts],
            "unknown_keys": {key: list(value) for key, value in self.unknown_keys.items()},
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True)
class ThemeToken:
    """One theme color token."""

    name: str
    value: str
    category: str = "surface"
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "category": self.category,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    """A named set of theme tokens."""

    name: str
    label: str
    mode: str = "dark"
    tokens: dict[str, str] = field(default_factory=dict)
    description: str = ""
    extends: str = ""
    accent_hue: int = 210

    def token(self, name: str, default: str = "") -> str:
        return self.tokens.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "mode": self.mode,
            "tokens": dict(self.tokens),
            "description": self.description,
            "extends": self.extends,
            "accent_hue": self.accent_hue,
        }


@dataclass(frozen=True, slots=True)
class ThemeValidationIssue:
    """A contrast or token problem in a theme."""

    theme: str
    token: str
    message: str
    severity: Severity = Severity.MODERATE
    ratio: float = 0.0
    required: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "token": self.token,
            "message": self.message,
            "severity": self.severity.value,
            "ratio": round(self.ratio, 2),
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class LocaleInfo:
    """Metadata for a supported locale."""

    code: str
    label: str
    native_name: str
    direction: Direction = Direction.LTR
    script: str = "Latn"
    plural_categories: tuple[str, ...] = ("one", "other")
    fallbacks: tuple[str, ...] = ("en",)
    date_format: str = "yyyy-MM-dd"
    decimal_separator: str = "."
    group_separator: str = ","

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "native_name": self.native_name,
            "direction": self.direction.value,
            "script": self.script,
            "plural_categories": _string_list(self.plural_categories),
            "fallbacks": _string_list(self.fallbacks),
            "date_format": self.date_format,
            "decimal_separator": self.decimal_separator,
            "group_separator": self.group_separator,
        }


@dataclass(frozen=True, slots=True)
class MessageEntry:
    """A translated message template."""

    key: str
    text: str
    description: str = ""
    placeholders: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "text": self.text,
            "description": self.description,
            "placeholders": _string_list(self.placeholders),
        }


@dataclass(frozen=True, slots=True)
class PreferenceSnapshot:
    """A versioned, persistable user preference record."""

    locale: str = "en"
    theme: str = "graphite"
    direction: Direction = Direction.AUTO
    font_scale: float = 1.0
    reduce_motion: bool = False
    high_contrast: bool = False
    screen_reader_hints: bool = True
    focus_ring_boost: bool = False
    shortcuts: dict[str, list[str]] = field(default_factory=dict)
    updated_at: str = ""
    revision: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "theme": self.theme,
            "direction": self.direction.value,
            "font_scale": self.font_scale,
            "reduce_motion": self.reduce_motion,
            "high_contrast": self.high_contrast,
            "screen_reader_hints": self.screen_reader_hints,
            "focus_ring_boost": self.focus_ring_boost,
            "shortcuts": {key: list(value) for key, value in self.shortcuts.items()},
            "updated_at": self.updated_at,
            "revision": self.revision,
        }
