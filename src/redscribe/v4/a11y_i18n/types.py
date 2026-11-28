"""Data-only contracts for the v4 accessibility and internationalization slice.

Every structure in this module is immutable, validated at construction time, and
round-trippable through plain dictionaries. Nothing here executes code, reads
files, or touches the network: services in :mod:`service` operate exclusively on
these values.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
LOCALE_PATTERN = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")

MIN_CONTRAST_RATIO = 1.0
MAX_CONTRAST_RATIO = 21.0
AA_CONTRAST_RATIO = 4.5
AA_LARGE_CONTRAST_RATIO = 3.0

INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "switch",
        "tab",
        "menuitem",
        "slider",
    }
)
LABELED_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "switch",
        "tab",
        "menuitem",
        "slider",
        "img",
        "heading",
        "dialog",
    }
)
HEADING_ROLES = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


class AuditSeverity(str, Enum):
    """Impact level attached to an audit issue."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        return {
            AuditSeverity.INFO: 0,
            AuditSeverity.WARNING: 1,
            AuditSeverity.ERROR: 2,
        }[self]

    @classmethod
    def parse(cls, value: str) -> AuditSeverity:
        normalized = value.strip().casefold()
        for severity in cls:
            if severity.value == normalized:
                return severity
        raise ValueError(f"unknown audit severity: {value}")


class RuleId(str, Enum):
    """Stable identifiers for the five built-in audit rules."""

    MISSING_LABEL = "missing-label"
    UNFOCUSABLE_INTERACTIVE = "unfocusable-interactive"
    LOW_CONTRAST = "low-contrast"
    DUPLICATE_ID = "duplicate-id"
    SKIPPED_HEADING_LEVEL = "skipped-heading-level"

    @classmethod
    def parse(cls, value: str) -> RuleId:
        normalized = value.strip().casefold()
        for rule in cls:
            if rule.value == normalized:
                return rule
        raise ValueError(f"unknown audit rule: {value}")


class MessageId(str, Enum):
    """Catalog keys for every user-visible string owned by this slice."""

    WELCOME = "welcome"
    SAVE = "save"
    CANCEL = "cancel"
    LOADING = "loading"
    RETRY = "retry"
    EMPTY_TITLE = "empty.title"
    EMPTY_BODY = "empty.body"
    EMPTY_ACTION = "empty.action"
    AUDIT_TITLE = "audit.title"
    AUDIT_SUMMARY = "audit.summary"
    AUDIT_CLEAN = "audit.clean"
    ITEMS_COUNT = "items.count"
    TOUR_NEXT = "tour.next"
    TOUR_PREVIOUS = "tour.previous"
    TOUR_SKIP = "tour.skip"
    TOUR_COMPLETE = "tour.complete"
    MOTION_FULL = "motion.full"
    MOTION_SUBTLE = "motion.subtle"
    MOTION_OFF = "motion.off"
    LOCALE_LABEL = "locale.label"
    RTL_PREVIEW = "locale.rtl_preview"
    THEME_LABEL = "theme.label"
    DENSITY_LABEL = "density.label"
    SNAPSHOT_SAVED = "snapshot.saved"
    SNAPSHOT_MISSING = "snapshot.missing"

    @classmethod
    def parse(cls, value: str) -> MessageId:
        normalized = value.strip().casefold()
        for message in cls:
            if message.value == normalized:
                return message
        raise ValueError(f"unknown message id: {value}")


class MotionPreference(str, Enum):
    """User motion preference, from most to least animation."""

    FULL = "full"
    SUBTLE = "subtle"
    OFF = "off"

    @classmethod
    def parse(cls, value: str) -> MotionPreference:
        normalized = value.strip().casefold()
        for preference in cls:
            if preference.value == normalized:
                return preference
        raise ValueError(f"unknown motion preference: {value}")

    @property
    def strictness(self) -> int:
        return {
            MotionPreference.FULL: 0,
            MotionPreference.SUBTLE: 1,
            MotionPreference.OFF: 2,
        }[self]


class Direction(str, Enum):
    """Text direction for a locale catalog."""

    LTR = "ltr"
    RTL = "rtl"

    @classmethod
    def parse(cls, value: str) -> Direction:
        normalized = value.strip().casefold()
        for direction in cls:
            if direction.value == normalized:
                return direction
        raise ValueError(f"unknown text direction: {value}")


class TourStatus(str, Enum):
    """Lifecycle of an onboarding tour."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PluralCategory(str, Enum):
    """Unicode-style plural categories used by catalogs."""

    ZERO = "zero"
    ONE = "one"
    TWO = "two"
    FEW = "few"
    MANY = "many"
    OTHER = "other"


def require_text(
    value: object,
    field_name: str,
    *,
    allow_empty: bool = False,
    max_length: int = 2000,
) -> str:
    """Validate and normalize a text field."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    if len(text) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")
    return text


def require_id(value: object, field_name: str) -> str:
    """Validate a lowercase slug identifier."""
    text = require_text(value, field_name, max_length=64).casefold()
    if not ID_PATTERN.match(text):
        raise ValueError(f"{field_name} must be a lowercase slug: {value}")
    return text


def require_locale(value: object, field_name: str = "locale") -> str:
    """Validate a BCP-47-like ``language`` or ``language-Region`` tag."""
    text = require_text(value, field_name, max_length=16)
    if not LOCALE_PATTERN.match(text):
        raise ValueError(f"{field_name} must be a locale tag: {value}")
    return text


def require_ratio(value: object, field_name: str = "contrast_ratio") -> float:
    """Validate a WCAG contrast ratio in the inclusive range 1..21."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    ratio = float(value)
    if not MIN_CONTRAST_RATIO <= ratio <= MAX_CONTRAST_RATIO:
        raise ValueError(f"{field_name} out of range: {ratio}")
    return ratio


def placeholder_names(template: str) -> tuple[str, ...]:
    """Return the ordered, deduplicated placeholders in a message template."""
    names: list[str] = []
    for match in PLACEHOLDER_PATTERN.finditer(template):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return tuple(names)


@dataclass(frozen=True, slots=True)
class AuditRule:
    """A toggleable accessibility rule with a stable id."""

    id: RuleId
    description: str
    severity: AuditSeverity
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "description", require_text(self.description, "description"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id.value,
            "description": self.description,
            "severity": self.severity.value,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AuditRule:
        return cls(
            id=RuleId.parse(str(data.get("id", ""))),
            description=str(data.get("description", "")),
            severity=AuditSeverity.parse(str(data.get("severity", "info"))),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True, slots=True)
class AuditIssue:
    """A single rule violation found on a UI descriptor."""

    rule_id: RuleId
    target: str
    detail: str
    suggestion: str
    severity: AuditSeverity = AuditSeverity.WARNING

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", require_text(self.target, "target"))
        object.__setattr__(self, "detail", require_text(self.detail, "detail"))
        object.__setattr__(self, "suggestion", require_text(self.suggestion, "suggestion"))

    @property
    def fingerprint(self) -> str:
        return f"{self.rule_id.value}:{self.target}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id.value,
            "target": self.target,
            "detail": self.detail,
            "suggestion": self.suggestion,
            "severity": self.severity.value,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AuditIssue:
        return cls(
            rule_id=RuleId.parse(str(data.get("rule_id", ""))),
            target=str(data.get("target", "")),
            detail=str(data.get("detail", "")),
            suggestion=str(data.get("suggestion", "")),
            severity=AuditSeverity.parse(str(data.get("severity", "warning"))),
        )


@dataclass(frozen=True, slots=True)
class UiDescriptor:
    """A declarative description of one rendered UI element."""

    id: str
    role: str
    label: str
    focusable: bool
    visible: bool
    contrast_ratio: float
    tab_index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_id(self.id, "id"))
        object.__setattr__(self, "role", require_id(self.role, "role"))
        object.__setattr__(self, "label", require_text(self.label, "label", allow_empty=True))
        object.__setattr__(self, "contrast_ratio", require_ratio(self.contrast_ratio))
        if isinstance(self.tab_index, bool) or not isinstance(self.tab_index, int):
            raise ValueError("tab_index must be an integer")
        if self.tab_index < -1:
            raise ValueError("tab_index must be >= -1")

    @property
    def interactive(self) -> bool:
        return self.role in INTERACTIVE_ROLES

    @property
    def heading_level(self) -> int | None:
        if self.role in HEADING_ROLES:
            return int(self.role[1])
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "label": self.label,
            "focusable": self.focusable,
            "visible": self.visible,
            "contrast_ratio": self.contrast_ratio,
            "tab_index": self.tab_index,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UiDescriptor:
        return cls(
            id=str(data.get("id", "")),
            role=str(data.get("role", "")),
            label=str(data.get("label", "")),
            focusable=bool(data.get("focusable", False)),
            visible=bool(data.get("visible", True)),
            contrast_ratio=float(data.get("contrast_ratio", 1.0)),
            tab_index=int(data.get("tab_index", 0)),
        )


@dataclass(frozen=True, slots=True)
class PluralForms:
    """Translated variants keyed by plural category."""

    one: str
    other: str
    zero: str = ""
    two: str = ""
    few: str = ""
    many: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "one", require_text(self.one, "one"))
        object.__setattr__(self, "other", require_text(self.other, "other"))
        for name in ("zero", "two", "few", "many"):
            value = getattr(self, name)
            object.__setattr__(self, name, require_text(value, name, allow_empty=True))

    def form_for(self, category: PluralCategory) -> str:
        candidate = getattr(self, category.value, "")
        return candidate or self.other

    def to_dict(self) -> dict[str, str]:
        return {
            "zero": self.zero,
            "one": self.one,
            "two": self.two,
            "few": self.few,
            "many": self.many,
            "other": self.other,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PluralForms:
        return cls(
            one=str(data.get("one", "")),
            other=str(data.get("other", "")),
            zero=str(data.get("zero", "")),
            two=str(data.get("two", "")),
            few=str(data.get("few", "")),
            many=str(data.get("many", "")),
        )


@dataclass(frozen=True, slots=True)
class LocaleCatalog:
    """A translated message table for one locale."""

    locale: str
    direction: Direction
    messages: Mapping[MessageId, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "locale", require_locale(self.locale))
        cleaned: dict[MessageId, str] = {}
        for key, value in self.messages.items():
            message = MessageId.parse(key.value if isinstance(key, MessageId) else str(key))
            cleaned[message] = require_text(value, f"messages[{message.value}]", max_length=4000)
        object.__setattr__(self, "messages", cleaned)

    @property
    def language(self) -> str:
        return self.locale.split("-", 1)[0]

    def get(self, message: MessageId) -> str:
        return self.messages.get(message, "")

    def has(self, message: MessageId) -> bool:
        return message in self.messages

    def with_message(self, message: MessageId, text: str) -> LocaleCatalog:
        merged = dict(self.messages)
        merged[message] = require_text(text, "text", max_length=4000)
        return LocaleCatalog(self.locale, self.direction, merged)

    def to_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "direction": self.direction.value,
            "messages": {key.value: value for key, value in self.messages.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LocaleCatalog:
        raw = data.get("messages", {})
        messages: dict[MessageId, str] = {}
        if isinstance(raw, Mapping):
            for key, value in raw.items():
                messages[MessageId.parse(str(key))] = str(value)
        return cls(
            locale=str(data.get("locale", "")),
            direction=Direction.parse(str(data.get("direction", "ltr"))),
            messages=messages,
        )


@dataclass(frozen=True, slots=True)
class MotionPolicy:
    """Resolved animation durations for a single preference."""

    preference: MotionPreference
    durations: Mapping[str, int]
    reduce_transparency: bool = False

    def __post_init__(self) -> None:
        cleaned: dict[str, int] = {}
        for key, value in self.durations.items():
            name = require_id(key, "duration key")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"duration {name} must be a non-negative integer")
            cleaned[name] = value
        object.__setattr__(self, "durations", cleaned)

    def duration_for(self, key: str) -> int:
        return self.durations.get(key, 0)

    @property
    def animated(self) -> bool:
        return any(value > 0 for value in self.durations.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "preference": self.preference.value,
            "durations": dict(self.durations),
            "reduce_transparency": self.reduce_transparency,
            "animated": self.animated,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MotionPolicy:
        raw = data.get("durations", {})
        durations: dict[str, int] = {}
        if isinstance(raw, Mapping):
            for key, value in raw.items():
                durations[str(key)] = int(value)
        return cls(
            preference=MotionPreference.parse(str(data.get("preference", "full"))),
            durations=durations,
            reduce_transparency=bool(data.get("reduce_transparency", False)),
        )


@dataclass(frozen=True, slots=True)
class TourStep:
    """One targeted step of the onboarding tour."""

    id: str
    target: str
    title: str
    body: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_id(self.id, "id"))
        object.__setattr__(self, "target", require_id(self.target, "target"))
        object.__setattr__(self, "title", require_text(self.title, "title"))
        object.__setattr__(self, "body", require_text(self.body, "body", max_length=4000))

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "target": self.target,
            "title": self.title,
            "body": self.body,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TourStep:
        return cls(
            id=str(data.get("id", "")),
            target=str(data.get("target", "")),
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
        )


@dataclass(frozen=True, slots=True)
class EmptyStateSpec:
    """Copy for an empty-state card."""

    title: str
    body: str
    action_label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", require_text(self.title, "title"))
        object.__setattr__(self, "body", require_text(self.body, "body", max_length=4000))
        object.__setattr__(self, "action_label", require_text(self.action_label, "action_label"))

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "body": self.body,
            "action_label": self.action_label,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EmptyStateSpec:
        return cls(
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            action_label=str(data.get("action_label", "")),
        )


__all__ = [
    "AA_CONTRAST_RATIO",
    "AA_LARGE_CONTRAST_RATIO",
    "HEADING_ROLES",
    "INTERACTIVE_ROLES",
    "LABELED_ROLES",
    "AuditIssue",
    "AuditRule",
    "AuditSeverity",
    "Direction",
    "EmptyStateSpec",
    "LocaleCatalog",
    "MessageId",
    "MotionPolicy",
    "MotionPreference",
    "PluralCategory",
    "PluralForms",
    "RuleId",
    "TourStatus",
    "TourStep",
    "UiDescriptor",
    "placeholder_names",
    "require_id",
    "require_locale",
    "require_ratio",
    "require_text",
]
