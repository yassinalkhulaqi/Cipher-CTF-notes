"""Projection and report models for the V3 activity stream.

Every model in this module is immutable by convention and exposes ``as_dict``
so it can travel through the V3 API envelope without a serialization layer.
The models deliberately reuse B00 entity and event vocabulary instead of
defining parallel identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.api.envelope import PageMeta
from redscribe.v3.entities.types import EntityKind
from redscribe.v3.events.types import EventSeverity

DENSITY_COMPACT = "compact"
DENSITY_COMFORTABLE = "comfortable"
DENSITY_DETAILED = "detailed"
DENSITY_MODES: tuple[str, ...] = (DENSITY_COMPACT, DENSITY_COMFORTABLE, DENSITY_DETAILED)

PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
DIGEST_PERIODS: tuple[str, ...] = (PERIOD_DAILY, PERIOD_WEEKLY)

FILTER_INCLUDE = "include"
FILTER_EXCLUDE = "exclude"
FILTER_OPERATORS: tuple[str, ...] = (FILTER_INCLUDE, FILTER_EXCLUDE)

DEFAULT_TIMEZONE = "UTC"


class DensityMode(str, Enum):
    """How much detail a rendered activity entry carries."""

    COMPACT = DENSITY_COMPACT
    COMFORTABLE = DENSITY_COMFORTABLE
    DETAILED = DENSITY_DETAILED

    @classmethod
    def parse(cls, value: str) -> DensityMode:
        """Parse a density name with a stable error message."""
        normalized = value.strip().casefold()
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(f"Unknown density mode: {value}")


class DigestInterval(str, Enum):
    """Digest bucket interval."""

    DAILY = PERIOD_DAILY
    WEEKLY = PERIOD_WEEKLY

    @classmethod
    def parse(cls, value: str) -> DigestInterval:
        """Parse a digest interval with a stable error message."""
        normalized = value.strip().casefold()
        for interval in cls:
            if interval.value == normalized:
                return interval
        raise ValueError(f"Unknown digest interval: {value}")


@dataclass(frozen=True, slots=True)
class JumpTarget:
    """Universal resolver target attached to an activity entry."""

    ref: str
    kind: str
    value: str
    label: str
    route: str

    @classmethod
    def for_ref(cls, ref: str, label: str = "") -> JumpTarget:
        """Build a resolver target from a canonical ``kind:value`` reference."""
        kind_text, _, value = ref.partition(":")
        try:
            kind = EntityKind.parse(kind_text).value
        except ValueError:
            kind = kind_text or "unknown"
        display = label or value or ref
        return cls(
            ref=ref,
            kind=kind,
            value=value,
            label=display,
            route=f"/resolve/{kind}/{value}",
        )

    @property
    def is_resolvable(self) -> bool:
        """Whether the target carries enough data to open an entity."""
        return bool(self.ref and self.kind and self.value)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": self.ref,
            "kind": self.kind,
            "value": self.value,
            "label": self.label,
            "route": self.route,
            "resolvable": self.is_resolvable,
        }


@dataclass(frozen=True, slots=True)
class ActivityEntry:
    """One projected, linkable row of the activity stream."""

    sequence: int
    kind: str
    title: str
    summary: str
    actor: str
    severity: str
    timestamp: float
    iso_timestamp: str
    date_key: str
    week_key: str
    subject_ref: str
    payload: dict[str, Any] = field(default_factory=dict)
    jump: JumpTarget | None = None
    correlation_id: str = ""
    request_id: str = ""
    tags: tuple[str, ...] = ()
    redactions: tuple[str, ...] = ()

    @property
    def severity_rank(self) -> int:
        """Numeric severity used for ordering highlights."""
        try:
            return EventSeverity(self.severity).rank
        except ValueError:
            return -1

    @property
    def is_linkable(self) -> bool:
        """Whether this entry can jump to a universal entity."""
        return self.jump is not None and self.jump.is_resolvable

    @property
    def has_redactions(self) -> bool:
        """Whether any payload field was redacted."""
        return bool(self.redactions)

    def as_dict(self, *, density: str = DENSITY_COMFORTABLE) -> dict[str, Any]:
        """Return a JSON-safe representation, trimmed for compact density."""
        payload: dict[str, Any] = {
            "sequence": self.sequence,
            "kind": self.kind,
            "title": self.title,
            "actor": self.actor,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "iso_timestamp": self.iso_timestamp,
            "date_key": self.date_key,
            "subject_ref": self.subject_ref,
            "summary": self.summary,
            "jump": self.jump.as_dict() if self.jump is not None else None,
            "redactions": list(self.redactions),
        }
        if density == DENSITY_COMPACT:
            return payload
        payload["week_key"] = self.week_key
        payload["correlation_id"] = self.correlation_id
        payload["tags"] = list(self.tags)
        payload["payload"] = dict(self.payload)
        if density == DENSITY_DETAILED:
            payload["request_id"] = self.request_id
            payload["severity_rank"] = self.severity_rank
        return payload


@dataclass(frozen=True, slots=True)
class DateGroup:
    """Entries bucketed by a local calendar day or week."""

    key: str
    label: str
    entries: tuple[ActivityEntry, ...] = ()
    period: str = PERIOD_DAILY

    @property
    def count(self) -> int:
        """Number of entries in the group."""
        return len(self.entries)

    def as_dict(self, *, density: str = DENSITY_COMFORTABLE) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "label": self.label,
            "period": self.period,
            "count": self.count,
            "entries": [entry.as_dict(density=density) for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class FacetCounts:
    """Facet counts used to render activity filter chips."""

    kinds: dict[str, int] = field(default_factory=dict)
    actors: dict[str, int] = field(default_factory=dict)
    severities: dict[str, int] = field(default_factory=dict)
    subjects: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "kinds": dict(sorted(self.kinds.items())),
            "actors": dict(sorted(self.actors.items())),
            "severities": dict(sorted(self.severities.items())),
            "subjects": dict(sorted(self.subjects.items())),
        }


@dataclass(frozen=True, slots=True)
class StreamResult:
    """A filtered, paginated activity stream with grouping and facets."""

    entries: tuple[ActivityEntry, ...] = ()
    total: int = 0
    groups: tuple[DateGroup, ...] = ()
    facets: FacetCounts = field(default_factory=FacetCounts)
    page: PageMeta | None = None
    query: str = ""
    density: str = DENSITY_COMFORTABLE
    timezone: str = DEFAULT_TIMEZONE
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "entries": [entry.as_dict(density=self.density) for entry in self.entries],
            "total": self.total,
            "groups": [group.as_dict(density=self.density) for group in self.groups],
            "facets": self.facets.as_dict(),
            "page": self.page.as_dict() if self.page is not None else None,
            "query": self.query,
            "density": self.density,
            "timezone": self.timezone,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class FilterChip:
    """A user-visible filter token such as ``kind:finding.created``."""

    key: str
    value: str
    operator: str = FILTER_INCLUDE
    label: str = ""

    @property
    def token(self) -> str:
        """Compact DSL token for this chip."""
        prefix = "" if self.operator == FILTER_INCLUDE else "-"
        return f"{prefix}{self.key}:{self.value}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "value": self.value,
            "operator": self.operator,
            "label": self.label or self.value,
            "token": self.token,
        }


@dataclass(frozen=True, slots=True)
class FilterDefinition:
    """Metadata describing one supported filter DSL key."""

    key: str
    label: str
    description: str
    choices: tuple[str, ...] = ()
    multi: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "choices": list(self.choices),
            "multi": self.multi,
        }


@dataclass(frozen=True, slots=True)
class FilterValidation:
    """Result of validating a filter query string."""

    valid: bool
    errors: tuple[str, ...] = ()
    tokens: tuple[FilterChip, ...] = ()
    normalized: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "tokens": [chip.as_dict() for chip in self.tokens],
            "normalized": self.normalized,
        }


@dataclass(frozen=True, slots=True)
class DigestSection:
    """Grouped rows inside one digest."""

    title: str
    kind: str
    entries: tuple[ActivityEntry, ...] = ()

    @property
    def count(self) -> int:
        """Number of entries in the section."""
        return len(self.entries)

    def as_dict(self, *, density: str = DENSITY_COMPACT) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "title": self.title,
            "kind": self.kind,
            "count": self.count,
            "entries": [entry.as_dict(density=density) for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class Digest:
    """One deterministic daily or weekly digest."""

    period: str
    key: str
    label: str
    start: float
    end: float
    iso_start: str
    iso_end: str
    timezone: str
    entries: tuple[ActivityEntry, ...] = ()
    sections: tuple[DigestSection, ...] = ()
    highlights: tuple[ActivityEntry, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    actor_counts: dict[str, int] = field(default_factory=dict)

    @property
    def entry_count(self) -> int:
        """Total number of entries in the digest."""
        return len(self.entries)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "period": self.period,
            "key": self.key,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "iso_start": self.iso_start,
            "iso_end": self.iso_end,
            "timezone": self.timezone,
            "entry_count": self.entry_count,
            "counts": dict(sorted(self.counts.items())),
            "actor_counts": dict(sorted(self.actor_counts.items())),
            "sections": [section.as_dict() for section in self.sections],
            "highlights": [entry.as_dict(density=DENSITY_COMPACT) for entry in self.highlights],
        }


@dataclass(frozen=True, slots=True)
class DigestCollection:
    """Ordered digests for a timezone and interval."""

    period: str
    timezone: str
    generated_at: float
    digests: tuple[Digest, ...] = ()
    total_events: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "period": self.period,
            "timezone": self.timezone,
            "generated_at": self.generated_at,
            "total_events": self.total_events,
            "digests": [digest.as_dict() for digest in self.digests],
        }


@dataclass(frozen=True, slots=True)
class VisitMarker:
    """The last point a persona observed the activity stream."""

    identity: str
    timestamp: float
    sequence: int
    iso_timestamp: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "identity": self.identity,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "iso_timestamp": self.iso_timestamp,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class SinceLastVisit:
    """Everything new since a persona last visited."""

    identity: str
    marker: VisitMarker | None
    entries: tuple[ActivityEntry, ...] = ()
    count: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    first_timestamp: float | None = None
    last_timestamp: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "identity": self.identity,
            "marker": self.marker.as_dict() if self.marker is not None else None,
            "count": self.count,
            "by_kind": dict(sorted(self.by_kind.items())),
            "by_severity": dict(sorted(self.by_severity.items())),
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "entries": [entry.as_dict(density=DENSITY_COMPACT) for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class DayCount:
    """A single day's activity count used by retrospective streaks."""

    date_key: str
    count: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"date_key": self.date_key, "count": self.count}


@dataclass(frozen=True, slots=True)
class RetrospectiveSummary:
    """A retrospective rollup over an explicit time window."""

    start: float
    end: float
    iso_start: str
    iso_end: str
    timezone: str
    total_events: int = 0
    active_days: int = 0
    active_weeks: int = 0
    longest_streak: int = 0
    trailing_streak: int = 0
    busiest_day: DayCount | None = None
    top_kinds: tuple[tuple[str, int], ...] = ()
    top_actors: tuple[tuple[str, int], ...] = ()
    top_subjects: tuple[tuple[str, int], ...] = ()
    severity_mix: dict[str, int] = field(default_factory=dict)
    highlights: tuple[ActivityEntry, ...] = ()
    daily_counts: tuple[DayCount, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "start": self.start,
            "end": self.end,
            "iso_start": self.iso_start,
            "iso_end": self.iso_end,
            "timezone": self.timezone,
            "total_events": self.total_events,
            "active_days": self.active_days,
            "active_weeks": self.active_weeks,
            "longest_streak": self.longest_streak,
            "trailing_streak": self.trailing_streak,
            "busiest_day": self.busiest_day.as_dict() if self.busiest_day else None,
            "top_kinds": [{"value": key, "count": count} for key, count in self.top_kinds],
            "top_actors": [{"value": key, "count": count} for key, count in self.top_actors],
            "top_subjects": [{"value": key, "count": count} for key, count in self.top_subjects],
            "severity_mix": dict(sorted(self.severity_mix.items())),
            "highlights": [entry.as_dict(density=DENSITY_COMPACT) for entry in self.highlights],
            "daily_counts": [day.as_dict() for day in self.daily_counts],
        }


@dataclass(frozen=True, slots=True)
class RedactionReport:
    """A count of redaction decisions applied to one payload."""

    redacted_keys: tuple[str, ...] = ()
    rewritten_values: int = 0
    dropped_depth: int = 0
    keys_inspected: int = 0

    @property
    def applied(self) -> bool:
        """Whether anything was changed."""
        return bool(self.redacted_keys or self.rewritten_values or self.dropped_depth)

    def merge(self, other: RedactionReport) -> RedactionReport:
        """Combine two reports into one."""
        return RedactionReport(
            redacted_keys=tuple(dict.fromkeys((*self.redacted_keys, *other.redacted_keys))),
            rewritten_values=self.rewritten_values + other.rewritten_values,
            dropped_depth=self.dropped_depth + other.dropped_depth,
            keys_inspected=self.keys_inspected + other.keys_inspected,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "applied": self.applied,
            "redacted_keys": list(self.redacted_keys),
            "rewritten_values": self.rewritten_values,
            "dropped_depth": self.dropped_depth,
            "keys_inspected": self.keys_inspected,
        }
