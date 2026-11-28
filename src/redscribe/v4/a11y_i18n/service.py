"""Domain services for accessibility audits, catalogs, formatting, and tours.

The services are pure and deterministic: given the same inputs they produce the
same outputs without reading the clock, the filesystem, or the network. Callers
inject identifiers and timestamps where a value must vary.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v4.a11y_i18n.types import (
    AA_CONTRAST_RATIO,
    INTERACTIVE_ROLES,
    LABELED_ROLES,
    AuditIssue,
    AuditRule,
    AuditSeverity,
    Direction,
    LocaleCatalog,
    MessageId,
    MotionPolicy,
    MotionPreference,
    PluralCategory,
    PluralForms,
    RuleId,
    TourStatus,
    TourStep,
    UiDescriptor,
    require_locale,
)

DURATION_KEYS = ("fast", "normal", "slow", "pulse")

DURATION_TABLE: dict[MotionPreference, dict[str, int]] = {
    MotionPreference.FULL: {"fast": 120, "normal": 220, "slow": 380, "pulse": 1600},
    MotionPreference.SUBTLE: {"fast": 60, "normal": 100, "slow": 160, "pulse": 0},
    MotionPreference.OFF: {"fast": 0, "normal": 0, "slow": 0, "pulse": 0},
}


class A11yServiceError(ValueError):
    """Base class for recoverable service validation failures."""


class AuditError(A11yServiceError):
    """Raised when an audit is misconfigured."""


class TranslationError(A11yServiceError):
    """Raised when a catalog or translation request is invalid."""


class FormattingError(A11yServiceError):
    """Raised when a locale value cannot be formatted."""


class MotionError(A11yServiceError):
    """Raised when a motion policy cannot be resolved."""


class TourError(A11yServiceError):
    """Raised when a tour is advanced outside its bounds."""


def default_rules() -> tuple[AuditRule, ...]:
    """Return the five built-in audit rules in stable order."""
    return (
        AuditRule(
            RuleId.MISSING_LABEL,
            "Interactive and meaningful elements expose an accessible name.",
            AuditSeverity.ERROR,
        ),
        AuditRule(
            RuleId.UNFOCUSABLE_INTERACTIVE,
            "Interactive elements participate in the keyboard tab order.",
            AuditSeverity.ERROR,
        ),
        AuditRule(
            RuleId.LOW_CONTRAST,
            "Visible text meets a 4.5:1 contrast ratio.",
            AuditSeverity.WARNING,
        ),
        AuditRule(
            RuleId.DUPLICATE_ID,
            "Element identifiers are unique within a view.",
            AuditSeverity.WARNING,
        ),
        AuditRule(
            RuleId.SKIPPED_HEADING_LEVEL,
            "Heading levels increase by at most one at a time.",
            AuditSeverity.INFO,
        ),
    )


@dataclass(frozen=True, slots=True)
class AuditReport:
    """The immutable result of running an audit."""

    issues: tuple[AuditIssue, ...]
    rules_run: tuple[RuleId, ...]
    descriptor_count: int

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is AuditSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is AuditSeverity.WARNING)

    def severity_counts(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in AuditSeverity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts

    def issues_for(self, rule: RuleId) -> tuple[AuditIssue, ...]:
        return tuple(issue for issue in self.issues if issue.rule_id is rule)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issues": [issue.to_dict() for issue in self.issues],
            "rules_run": [rule.value for rule in self.rules_run],
            "descriptor_count": self.descriptor_count,
            "passed": self.passed,
            "severity_counts": self.severity_counts(),
        }


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """A translated string plus provenance for debugging."""

    text: str
    message: MessageId
    locale: str
    resolved_locale: str
    fallback_used: bool
    missing_placeholders: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "message": self.message.value,
            "locale": self.locale,
            "resolved_locale": self.resolved_locale,
            "fallback_used": self.fallback_used,
            "missing_placeholders": list(self.missing_placeholders),
        }


@dataclass(frozen=True, slots=True)
class TourState:
    """A snapshot of the tour cursor and visit history."""

    index: int
    status: TourStatus
    visited_ids: tuple[str, ...]
    completed_ids: tuple[str, ...]
    total: int

    @property
    def can_advance(self) -> bool:
        return self.status is TourStatus.IN_PROGRESS and self.index + 1 < self.total

    @property
    def can_go_back(self) -> bool:
        return self.status is TourStatus.IN_PROGRESS and self.index > 0

    @property
    def progress(self) -> float:
        if self.total == 0:
            return 1.0
        return round((self.index + 1) / self.total, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "status": self.status.value,
            "visited_ids": list(self.visited_ids),
            "completed_ids": list(self.completed_ids),
            "total": self.total,
            "can_advance": self.can_advance,
            "can_go_back": self.can_go_back,
            "progress": self.progress,
        }


class A11yAuditor:
    """Run a configurable set of static rules over UI descriptors."""

    def __init__(self, rules: Sequence[AuditRule] | None = None) -> None:
        source = default_rules() if rules is None else tuple(rules)
        seen: set[RuleId] = set()
        for rule in source:
            if rule.id in seen:
                raise AuditError(f"duplicate rule: {rule.id.value}")
            seen.add(rule.id)
        self._rules: tuple[AuditRule, ...] = source
        self._by_id: dict[RuleId, AuditRule] = {rule.id: rule for rule in source}

    def rules(self, enabled_only: bool = False) -> tuple[AuditRule, ...]:
        if enabled_only:
            return tuple(rule for rule in self._rules if rule.enabled)
        return self._rules

    def rule(self, rule_id: RuleId) -> AuditRule:
        try:
            return self._by_id[rule_id]
        except KeyError as exc:
            raise AuditError(f"unknown rule: {rule_id.value}") from exc

    def set_enabled(self, rule_id: RuleId, enabled: bool) -> AuditRule:
        existing = self.rule(rule_id)
        updated = AuditRule(existing.id, existing.description, existing.severity, enabled)
        self._by_id[rule_id] = updated
        self._rules = tuple(self._by_id[rule] for rule in self._by_id)
        return updated

    def severity_for(self, rule_id: RuleId) -> AuditSeverity:
        return self.rule(rule_id).severity

    def audit(self, descriptors: Sequence[UiDescriptor]) -> AuditReport:
        """Run all enabled rules and return a complete report."""
        enabled = [rule for rule in self._rules if rule.enabled]
        issues: list[AuditIssue] = []
        for rule in enabled:
            issues.extend(self._run_rule(rule, descriptors))
        ordered = sorted(issues, key=lambda issue: (-issue.severity.rank, issue.fingerprint))
        return AuditReport(
            issues=tuple(ordered),
            rules_run=tuple(rule.id for rule in enabled),
            descriptor_count=len(descriptors),
        )

    def audit_issues(self, descriptors: Sequence[UiDescriptor]) -> list[AuditIssue]:
        """Return only the issues, for callers that do not need report metadata."""
        return list(self.audit(descriptors).issues)

    def _run_rule(self, rule: AuditRule, descriptors: Sequence[UiDescriptor]) -> list[AuditIssue]:
        checkers: dict[RuleId, Callable[[Sequence[UiDescriptor]], list[AuditIssue]]] = {
            RuleId.MISSING_LABEL: self.check_missing_label,
            RuleId.UNFOCUSABLE_INTERACTIVE: self.check_unfocusable_interactive,
            RuleId.LOW_CONTRAST: self.check_low_contrast,
            RuleId.DUPLICATE_ID: self.check_duplicate_id,
            RuleId.SKIPPED_HEADING_LEVEL: self.check_skipped_heading_level,
        }
        checker = checkers.get(rule.id)
        if checker is None:
            raise AuditError(f"no checker registered for rule: {rule.id.value}")
        found = checker(descriptors)
        return [
            AuditIssue(
                issue.rule_id,
                issue.target,
                issue.detail,
                issue.suggestion,
                rule.severity,
            )
            for issue in found
        ]

    def check_missing_label(self, descriptors: Sequence[UiDescriptor]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for item in descriptors:
            if item.role in LABELED_ROLES and not item.label.strip():
                issues.append(
                    AuditIssue(
                        RuleId.MISSING_LABEL,
                        item.id,
                        f"Element with role '{item.role}' has no accessible name.",
                        "Provide a visible label or an aria-label attribute.",
                    )
                )
        return issues

    def check_unfocusable_interactive(
        self, descriptors: Sequence[UiDescriptor]
    ) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for item in descriptors:
            if item.role in INTERACTIVE_ROLES and not item.focusable:
                issues.append(
                    AuditIssue(
                        RuleId.UNFOCUSABLE_INTERACTIVE,
                        item.id,
                        f"Interactive '{item.role}' is not focusable.",
                        "Make the element focusable and reachable with the Tab key.",
                    )
                )
        return issues

    def check_low_contrast(self, descriptors: Sequence[UiDescriptor]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for item in descriptors:
            if item.visible and item.contrast_ratio < AA_CONTRAST_RATIO:
                issues.append(
                    AuditIssue(
                        RuleId.LOW_CONTRAST,
                        item.id,
                        f"Contrast ratio {item.contrast_ratio:.2f}:1 is below 4.5:1.",
                        "Darken the foreground or lighten the background to reach 4.5:1.",
                    )
                )
        return issues

    def check_duplicate_id(self, descriptors: Sequence[UiDescriptor]) -> list[AuditIssue]:
        seen: dict[str, int] = {}
        for item in descriptors:
            seen[item.id] = seen.get(item.id, 0) + 1
        return [
            AuditIssue(
                RuleId.DUPLICATE_ID,
                element_id,
                f"Element id '{element_id}' appears {count} times.",
                "Assign a unique id to each element in the view.",
            )
            for element_id, count in sorted(seen.items())
            if count > 1
        ]

    def check_skipped_heading_level(self, descriptors: Sequence[UiDescriptor]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        previous: int | None = None
        for item in descriptors:
            level = item.heading_level
            if level is None:
                continue
            if previous is not None and level > previous + 1:
                issues.append(
                    AuditIssue(
                        RuleId.SKIPPED_HEADING_LEVEL,
                        item.id,
                        f"Heading jumps from h{previous} to h{level}.",
                        "Use an intermediate heading level or restructure the section.",
                    )
                )
            previous = level
        return issues


def english_catalog() -> LocaleCatalog:
    """Return the built-in English fallback catalog."""
    messages: dict[MessageId, str] = {
        MessageId.WELCOME: "Welcome to RedScribe",
        MessageId.SAVE: "Save",
        MessageId.CANCEL: "Cancel",
        MessageId.LOADING: "Loading {items} items",
        MessageId.RETRY: "Try again",
        MessageId.EMPTY_TITLE: "Nothing here yet",
        MessageId.EMPTY_BODY: "Adjust your filters or add a new item.",
        MessageId.EMPTY_ACTION: "Create item",
        MessageId.AUDIT_TITLE: "Accessibility audit",
        MessageId.AUDIT_SUMMARY: "{count} issues across {targets} elements",
        MessageId.AUDIT_CLEAN: "No accessibility issues found",
        MessageId.ITEMS_COUNT: "{count} item",
        MessageId.TOUR_NEXT: "Next step",
        MessageId.TOUR_PREVIOUS: "Previous step",
        MessageId.TOUR_SKIP: "Skip tour",
        MessageId.TOUR_COMPLETE: "Finish",
        MessageId.MOTION_FULL: "Full motion",
        MessageId.MOTION_SUBTLE: "Reduced motion",
        MessageId.MOTION_OFF: "No motion",
        MessageId.LOCALE_LABEL: "Language",
        MessageId.RTL_PREVIEW: "Right-to-left preview",
        MessageId.THEME_LABEL: "Theme",
        MessageId.DENSITY_LABEL: "Density",
        MessageId.SNAPSHOT_SAVED: "Saved preferences as {name}",
        MessageId.SNAPSHOT_MISSING: "No snapshot named {name}",
    }
    return LocaleCatalog("en", Direction.LTR, messages)


def plural_category(locale: str, count: int) -> PluralCategory:
    """Map a locale and count to a deterministic plural category."""
    if isinstance(count, bool) or not isinstance(count, int):
        raise TranslationError("count must be an integer")
    language = require_locale(locale).split("-", 1)[0]
    if language in {"ja", "zh", "ko", "th", "vi"}:
        return PluralCategory.OTHER
    if language == "ar":
        if count == 0:
            return PluralCategory.ZERO
        if count == 1:
            return PluralCategory.ONE
        if count == 2:
            return PluralCategory.TWO
        if 3 <= count <= 10:
            return PluralCategory.FEW
        return PluralCategory.MANY
    if language == "fr" and 0 <= count <= 1:
        return PluralCategory.ONE
    return PluralCategory.ONE if count == 1 else PluralCategory.OTHER


def interpolate(template: str, params: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    """Replace ``{name}`` tokens and report any placeholders left unresolved."""
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            if name not in missing:
                missing.append(name)
            return match.group(0)
        value = params[name]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise TranslationError(f"placeholder {name} must be a scalar")
        return str(value)

    return PLACEHOLDER_SUBSTITUTION.sub(substitute, template), tuple(missing)


PLACEHOLDER_SUBSTITUTION = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class I18nCatalog:
    """A registry of locale catalogs with fallback and plural translation."""

    def __init__(self, fallback: LocaleCatalog | None = None) -> None:
        base = fallback or english_catalog()
        if base.locale != "en":
            raise TranslationError("fallback catalog must use the en locale")
        self.fallback: LocaleCatalog = base
        self._catalogs: dict[str, LocaleCatalog] = {"en": base}
        self._plurals: dict[MessageId, PluralForms] = {
            MessageId.ITEMS_COUNT: PluralForms(one="{count} item", other="{count} items")
        }

    def register(self, catalog: LocaleCatalog, *, overwrite: bool = False) -> None:
        if catalog.locale in self._catalogs and not overwrite:
            raise TranslationError(f"catalog already registered: {catalog.locale}")
        self._catalogs[catalog.locale] = catalog

    def register_plural(
        self, message: MessageId, forms: PluralForms, *, overwrite: bool = False
    ) -> None:
        if message in self._plurals and not overwrite:
            raise TranslationError(f"plural already registered: {message.value}")
        self._plurals[message] = forms

    def has(self, locale: str) -> bool:
        return require_locale(locale) in self._catalogs

    def available_locales(self) -> tuple[str, ...]:
        return tuple(sorted(self._catalogs))

    def catalog_for(self, locale: str) -> LocaleCatalog:
        requested = require_locale(locale)
        if requested in self._catalogs:
            return self._catalogs[requested]
        language = requested.split("-", 1)[0]
        if language in self._catalogs:
            return self._catalogs[language]
        return self.fallback

    def direction_for(self, locale: str) -> Direction:
        return self.catalog_for(locale).direction

    def translate(
        self,
        message: MessageId | str,
        locale: str = "en",
        params: Mapping[str, object] | None = None,
    ) -> TranslationResult:
        message_id = MessageId.parse(message if isinstance(message, str) else message.value)
        requested = require_locale(locale)
        catalog = self.catalog_for(requested)
        template = catalog.get(message_id)
        message_fallback = not template
        if message_fallback:
            template = self.fallback.get(message_id)
        if not template:
            raise TranslationError(f"message missing from fallback catalog: {message_id.value}")
        text, missing = interpolate(template, params or {})
        return TranslationResult(
            text=text,
            message=message_id,
            locale=requested,
            resolved_locale="en" if message_fallback else catalog.locale,
            fallback_used=message_fallback or (catalog.locale == "en" and requested != "en"),
            missing_placeholders=missing,
        )

    def translate_plural(
        self,
        message: MessageId | str,
        count: int,
        locale: str = "en",
        params: Mapping[str, object] | None = None,
    ) -> TranslationResult:
        message_id = MessageId.parse(message if isinstance(message, str) else message.value)
        category = plural_category(locale, count)
        forms = self._plurals.get(message_id)
        if forms is None:
            raise TranslationError(f"no plural forms for: {message_id.value}")
        template = forms.form_for(category)
        merged: dict[str, object] = dict(params or {})
        merged["count"] = count
        requested = require_locale(locale)
        text, missing = interpolate(template, merged)
        return TranslationResult(
            text=text,
            message=message_id,
            locale=requested,
            resolved_locale=self.catalog_for(requested).locale,
            fallback_used=requested != "en" and not self.has(requested),
            missing_placeholders=missing,
        )

    def audit_messages(self) -> tuple[MessageId, ...]:
        """Return message ids present in every registered catalog."""
        common = set(self.fallback.messages)
        for catalog in self._catalogs.values():
            common &= set(catalog.messages)
        return tuple(sorted(common, key=lambda item: item.value))

    def missing_messages(self, locale: str) -> tuple[MessageId, ...]:
        catalog = self.catalog_for(locale)
        return tuple(
            message for message in self.fallback.messages if message not in catalog.messages
        )


@dataclass(frozen=True, slots=True)
class FormatProfile:
    """Deterministic formatting rules for one locale family."""

    locale: str
    date_order: str
    group_separator: str
    decimal_separator: str
    percent_symbol: str = "%"

    def __post_init__(self) -> None:
        if self.date_order not in {"mdy", "dmy", "ymd"}:
            raise FormattingError(f"invalid date order: {self.date_order}")
        if len(self.date_order) != 3:
            raise FormattingError("date order must have three fields")

    def to_dict(self) -> dict[str, str]:
        return {
            "locale": self.locale,
            "date_order": self.date_order,
            "group_separator": self.group_separator,
            "decimal_separator": self.decimal_separator,
            "percent_symbol": self.percent_symbol,
        }


FORMAT_PROFILES: dict[str, FormatProfile] = {
    "en": FormatProfile("en", "mdy", ",", "."),
    "en-GB": FormatProfile("en-GB", "dmy", ",", "."),
    "fr": FormatProfile("fr", "dmy", " ", ","),
    "de": FormatProfile("de", "dmy", ".", ","),
    "es": FormatProfile("es", "dmy", ".", ","),
    "ar": FormatProfile("ar", "dmy", ",", "."),
    "ja": FormatProfile("ja", "ymd", ",", "."),
    "zh": FormatProfile("zh", "ymd", ",", "."),
}


class LocaleFormatter:
    """Format numbers, dates, and percentages without locale runtime data."""

    def __init__(self, locale: str = "en") -> None:
        requested = require_locale(locale)
        profile = FORMAT_PROFILES.get(requested)
        if profile is None:
            profile = FORMAT_PROFILES.get(requested.split("-", 1)[0])
        if profile is None:
            raise FormattingError(f"no format profile for locale: {locale}")
        self.profile = profile

    def format_number(self, value: int | float, decimals: int = 0) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FormattingError("value must be a number")
        if decimals < 0 or decimals > 6:
            raise FormattingError("decimals must be between 0 and 6")
        negative = value < 0
        raw = f"{abs(value):.{decimals}f}"
        whole, sep, fraction = raw.partition(".")
        grouped = self._group(whole)
        result = grouped + (self.profile.decimal_separator + fraction if sep else "")
        return f"-{result}" if negative else result

    def format_date(self, year: int, month: int, day: int, separator: str = "/") -> str:
        if isinstance(year, bool) or isinstance(month, bool) or isinstance(day, bool):
            raise FormattingError("date fields must be integers")
        if not isinstance(year, int) or not isinstance(month, int) or not isinstance(day, int):
            raise FormattingError("date fields must be integers")
        if not 1 <= month <= 12:
            raise FormattingError("month out of range")
        if not 1 <= day <= 31:
            raise FormattingError("day out of range")
        if year < 1:
            raise FormattingError("year out of range")
        parts = {
            "y": f"{year:04d}",
            "m": f"{month:02d}",
            "d": f"{day:02d}",
        }
        return separator.join(parts[key] for key in self.profile.date_order)

    def format_percent(self, value: float, decimals: int = 1) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FormattingError("percent must be a number")
        return f"{self.format_number(value, decimals)}{self.profile.percent_symbol}"

    def format_duration(self, seconds: int) -> str:
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
            raise FormattingError("seconds must be a non-negative integer")
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes}:{remainder:02d}"

    def _group(self, whole: str) -> str:
        chunks: list[str] = []
        while len(whole) > 3:
            chunks.append(whole[-3:])
            whole = whole[:-3]
        chunks.append(whole)
        return self.profile.group_separator.join(reversed(chunks))


class MotionPolicyResolver:
    """Resolve a user preference and system flag into a concrete policy."""

    def __init__(self, table: Mapping[MotionPreference, Mapping[str, int]] | None = None) -> None:
        self.table: dict[MotionPreference, dict[str, int]] = {
            key: dict(value) for key, value in (table or DURATION_TABLE).items()
        }

    def resolve(
        self,
        preference: MotionPreference | str,
        reduce_motion: bool = False,
        reduce_transparency: bool = False,
    ) -> MotionPolicy:
        chosen = (
            preference
            if isinstance(preference, MotionPreference)
            else MotionPreference.parse(str(preference))
        )
        if reduce_motion:
            chosen = MotionPreference.OFF
        durations = self.table.get(chosen)
        if durations is None:
            raise MotionError(f"no duration table for preference: {chosen.value}")
        missing = [key for key in DURATION_KEYS if key not in durations]
        if missing:
            raise MotionError(f"duration table missing keys: {', '.join(missing)}")
        return MotionPolicy(chosen, dict(durations), reduce_transparency)

    @staticmethod
    def strictest(first: MotionPreference, second: MotionPreference) -> MotionPreference:
        return first if first.strictness >= second.strictness else second

    def css_variables(self, policy: MotionPolicy) -> dict[str, str]:
        return {f"--v4-duration-{key}": f"{value}ms" for key, value in policy.durations.items()}


def default_tour_steps() -> tuple[TourStep, ...]:
    """Return a three-step tour that exercises the panel's affordances."""
    return (
        TourStep(
            "tour-controls",
            "control-grid",
            "Choose your display",
            "Theme, density, motion, and language controls live here.",
        ),
        TourStep(
            "tour-audit",
            "audit-issues",
            "Review the audit",
            "Each issue names the element and suggests a concrete fix.",
        ),
        TourStep(
            "tour-preview",
            "rtl-preview",
            "Preview right-to-left text",
            "Switch language to Arabic to mirror the layout instantly.",
        ),
    )


@dataclass(slots=True)
class TourEngine:
    """A stateful cursor over an ordered list of tour steps."""

    steps: tuple[TourStep, ...] = field(default_factory=default_tour_steps)
    index: int = 0
    status: TourStatus = TourStatus.NOT_STARTED
    visited_ids: list[str] = field(default_factory=list)
    completed_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.steps:
            raise TourError("tour requires at least one step")
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise TourError("tour step ids must be unique")
        if not 0 <= self.index < len(self.steps):
            raise TourError("tour index out of range")

    @classmethod
    def from_steps(cls, steps: Sequence[TourStep]) -> TourEngine:
        return cls(steps=tuple(steps))

    def current(self) -> TourStep:
        return self.steps[self.index]

    def start(self) -> TourState:
        self.status = TourStatus.IN_PROGRESS
        self._visit(self.current())
        return self.snapshot()

    def next(self) -> TourState:
        if self.status is TourStatus.COMPLETED or self.status is TourStatus.SKIPPED:
            raise TourError("tour is already finished")
        if self.index + 1 >= len(self.steps):
            return self.complete()
        self.status = TourStatus.IN_PROGRESS
        self.index += 1
        self._visit(self.current())
        return self.snapshot()

    def previous(self) -> TourState:
        if self.status is TourStatus.COMPLETED or self.status is TourStatus.SKIPPED:
            raise TourError("tour is already finished")
        if self.index == 0:
            return self.snapshot()
        self.index -= 1
        self._visit(self.current())
        return self.snapshot()

    def go_to(self, index: int) -> TourState:
        if not 0 <= index < len(self.steps):
            raise TourError("tour index out of range")
        self.index = index
        self.status = TourStatus.IN_PROGRESS
        self._visit(self.current())
        return self.snapshot()

    def skip(self) -> TourState:
        self.status = TourStatus.SKIPPED
        return self.snapshot()

    def complete(self) -> TourState:
        self.status = TourStatus.COMPLETED
        step = self.current()
        if step.id not in self.completed_ids:
            self.completed_ids.append(step.id)
        return self.snapshot()

    def reset(self) -> TourState:
        self.index = 0
        self.status = TourStatus.NOT_STARTED
        self.visited_ids.clear()
        self.completed_ids.clear()
        return self.snapshot()

    def snapshot(self) -> TourState:
        return TourState(
            index=self.index,
            status=self.status,
            visited_ids=tuple(self.visited_ids),
            completed_ids=tuple(self.completed_ids),
            total=len(self.steps),
        )

    def _visit(self, step: TourStep) -> None:
        if step.id not in self.visited_ids:
            self.visited_ids.append(step.id)


__all__ = [
    "DURATION_KEYS",
    "A11yAuditor",
    "A11yServiceError",
    "AuditError",
    "AuditReport",
    "FormatProfile",
    "FormattingError",
    "I18nCatalog",
    "LocaleFormatter",
    "MotionError",
    "MotionPolicyResolver",
    "TourEngine",
    "TourError",
    "TourState",
    "TranslationError",
    "TranslationResult",
    "default_rules",
    "default_tour_steps",
    "english_catalog",
    "interpolate",
    "plural_category",
]
