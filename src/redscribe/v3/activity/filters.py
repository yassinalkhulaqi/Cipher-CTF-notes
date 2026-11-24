"""A small, composable filter DSL for the activity stream.

The DSL builds on the B00 :class:`EventFilter` for record-level filtering and
adds entry-level facets (density, tags, severity sets, display chips). It never
evaluates user expressions: input is parsed into fixed, known keys.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v3.activity.models import (
    FILTER_EXCLUDE,
    FILTER_INCLUDE,
    FILTER_OPERATORS,
    ActivityEntry,
    FilterChip,
    FilterDefinition,
    FilterValidation,
)
from redscribe.v3.clock import timestamp_from_iso
from redscribe.v3.events.filters import EventFilter
from redscribe.v3.events.types import EventSeverity

FILTER_KEYS: tuple[str, ...] = (
    "kind",
    "actor",
    "subject",
    "severity",
    "text",
    "since",
    "until",
    "correlation",
    "tag",
)


def filter_definitions() -> tuple[FilterDefinition, ...]:
    """Describe every supported DSL key for filter-chip UI generation."""
    return (
        FilterDefinition("kind", "Event kind", "Match an exact event kind", FILTER_KEYS[:1]),
        FilterDefinition("actor", "Actor", "Match the user or service that acted"),
        FilterDefinition("subject", "Entity", "Match a universal entity reference"),
        FilterDefinition(
            "severity",
            "Severity",
            "Minimum or exact severity",
            tuple(severity.value for severity in EventSeverity),
        ),
        FilterDefinition("text", "Text", "Free-text search over title and payload"),
        FilterDefinition("since", "Since", "Only events after an ISO timestamp"),
        FilterDefinition("until", "Until", "Only events before an ISO timestamp"),
        FilterDefinition("correlation", "Correlation", "Match a correlation id", (), False),
        FilterDefinition("tag", "Tag", "Match a normalized payload tag"),
    )


def _parse_time(value: str) -> float:
    """Parse a numeric timestamp or ISO-8601 string."""
    try:
        return float(value)
    except ValueError:
        return timestamp_from_iso(value)


def _clean_value(value: str) -> str:
    """Strip surrounding quotes from a parsed token value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


@dataclass(frozen=True, slots=True)
class ActivityFilter:
    """Declarative filter compiled into a predicate over activity entries."""

    kinds: tuple[str, ...] = ()
    exclude_kinds: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    exclude_actors: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    severities: tuple[str, ...] = ()
    minimum_severity: str = ""
    text: str = ""
    since: float | None = None
    until: float | None = None
    correlation_id: str = ""
    tags: tuple[str, ...] = ()
    free_text: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Whether this filter matches everything."""
        return not any(
            (
                self.kinds,
                self.exclude_kinds,
                self.actors,
                self.exclude_actors,
                self.subjects,
                self.severities,
                self.minimum_severity,
                self.text,
                self.since is not None,
                self.until is not None,
                self.correlation_id,
                self.tags,
                self.free_text,
            )
        )

    def compile(self) -> Callable[[ActivityEntry], bool]:
        """Compile this filter into a callable predicate."""
        kinds = frozenset(kind.casefold() for kind in self.kinds)
        excluded = frozenset(kind.casefold() for kind in self.exclude_kinds)
        actors = frozenset(actor.casefold() for actor in self.actors)
        excluded_actors = frozenset(actor.casefold() for actor in self.exclude_actors)
        subjects = frozenset(self.subjects)
        severities = frozenset(severity.casefold() for severity in self.severities)
        tags = frozenset(tag.casefold() for tag in self.tags)
        needle = " ".join((self.text, *self.free_text)).strip().casefold()
        minimum_rank = _severity_rank(self.minimum_severity)

        def predicate(entry: ActivityEntry) -> bool:
            if kinds and entry.kind.casefold() not in kinds:
                return False
            if excluded and entry.kind.casefold() in excluded:
                return False
            if actors and entry.actor.casefold() not in actors:
                return False
            if excluded_actors and entry.actor.casefold() in excluded_actors:
                return False
            if subjects and entry.subject_ref not in subjects:
                return False
            if severities and entry.severity.casefold() not in severities:
                return False
            if minimum_rank > 0 and entry.severity_rank < minimum_rank:
                return False
            if self.since is not None and entry.timestamp <= self.since:
                return False
            if self.until is not None and entry.timestamp >= self.until:
                return False
            if self.correlation_id and entry.correlation_id != self.correlation_id:
                return False
            if tags and not tags.intersection(tag.casefold() for tag in entry.tags):
                return False
            return not (needle and needle not in _searchable(entry))

        return predicate

    def matches(self, entry: ActivityEntry) -> bool:
        """Return whether one entry matches the filter."""
        return self.compile()(entry)

    def apply(self, entries: Iterable[ActivityEntry]) -> tuple[ActivityEntry, ...]:
        """Return matching entries in their original order."""
        predicate = self.compile()
        return tuple(entry for entry in entries if predicate(entry))

    def to_event_filter(self) -> EventFilter:
        """Lower this filter to the B00 record-level event filter."""
        minimum = None
        if self.minimum_severity:
            minimum = EventSeverity(self.minimum_severity.casefold())
        return EventFilter(
            kinds=self.kinds,
            subjects=self.subjects,
            actors=self.actors,
            minimum_severity=minimum,
            after=self.since,
            before=self.until,
            text=self.text,
            exclude_kinds=self.exclude_kinds,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "kinds": list(self.kinds),
            "exclude_kinds": list(self.exclude_kinds),
            "actors": list(self.actors),
            "subjects": list(self.subjects),
            "severities": list(self.severities),
            "minimum_severity": self.minimum_severity,
            "text": self.text,
            "since": self.since,
            "until": self.until,
            "correlation_id": self.correlation_id,
            "tags": list(self.tags),
            "is_empty": self.is_empty,
        }

    @classmethod
    def parse(cls, query: str) -> ActivityFilter:
        """Parse a DSL query, ignoring invalid tokens."""
        event_filter, _, _ = parse_query(query)
        return event_filter

    @classmethod
    def from_chips(cls, chips: Sequence[FilterChip]) -> ActivityFilter:
        """Build a filter from UI filter chips."""
        return _build_filter(chips)


def _severity_rank(value: str) -> int:
    """Return a severity rank, or zero for an unset/unknown value."""
    if not value:
        return 0
    try:
        return EventSeverity(value.strip().casefold()).rank
    except ValueError:
        return 0


def _searchable(entry: ActivityEntry) -> str:
    """Build a case-folded search blob for an activity entry."""
    parts: list[str] = [
        entry.kind,
        entry.title,
        entry.summary,
        entry.actor,
        entry.subject_ref,
        entry.correlation_id,
        *entry.tags,
        *(str(value) for value in entry.payload.values()),
    ]
    return " ".join(parts).casefold()


def parse_query(query: str) -> tuple[ActivityFilter, tuple[FilterChip, ...], tuple[str, ...]]:
    """Parse a filter query into a filter, chips, and validation errors."""
    if not isinstance(query, str):
        raise TypeError("Filter query must be a string")
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    chips: list[FilterChip] = []
    errors: list[str] = []
    for token in tokens:
        chip = _chip_from_token(token)
        if chip is None:
            continue
        if chip.key not in FILTER_KEYS:
            errors.append(f"Unsupported filter key: {chip.key}")
            continue
        if chip.key == "severity" and _severity_rank(chip.value) == 0:
            errors.append(f"Unknown severity: {chip.value}")
            continue
        if chip.key in {"since", "until"}:
            try:
                _parse_time(chip.value)
            except (ValueError, TypeError):
                errors.append(f"Invalid timestamp for {chip.key}: {chip.value}")
                continue
        chips.append(chip)
    return _build_filter(chips), tuple(chips), tuple(errors)


def validate_query(query: str) -> FilterValidation:
    """Validate a filter query and return a normalized chip rendering."""
    _event_filter, chips, errors = parse_query(query)
    return FilterValidation(
        valid=not errors,
        errors=errors,
        tokens=chips,
        normalized=" ".join(chip.token for chip in chips),
    )


def _chip_from_token(token: str) -> FilterChip | None:
    """Convert one whitespace-delimited token into a filter chip."""
    if not token:
        return None
    operator = FILTER_INCLUDE
    raw = token
    if raw.startswith(("-", "!")):
        operator = FILTER_EXCLUDE
        raw = raw[1:]
    if ":" not in raw:
        value = _clean_value(raw)
        return FilterChip(key="text", value=value, operator=operator) if value else None
    key, value = raw.split(":", 1)
    value = _clean_value(value)
    if not key or not value:
        return None
    return FilterChip(key=key.strip().casefold(), value=value, operator=operator)


def _build_filter(chips: Sequence[FilterChip]) -> ActivityFilter:
    """Build a filter from parsed chips."""
    kinds: list[str] = []
    exclude_kinds: list[str] = []
    actors: list[str] = []
    exclude_actors: list[str] = []
    subjects: list[str] = []
    severities: list[str] = []
    tags: list[str] = []
    free_text: list[str] = []
    text = ""
    minimum = ""
    since: float | None = None
    until: float | None = None
    correlation = ""
    for chip in chips:
        excluded = chip.operator == FILTER_EXCLUDE
        value = chip.value
        if chip.key == "kind":
            (exclude_kinds if excluded else kinds).append(value)
        elif chip.key == "actor":
            (exclude_actors if excluded else actors).append(value)
        elif chip.key == "subject":
            subjects.append(value)
        elif chip.key == "tag":
            tags.append(value.casefold().lstrip("#"))
        elif chip.key == "severity":
            if excluded:
                severities.append(value)
            else:
                minimum = value
        elif chip.key == "text":
            if excluded:
                free_text.append(value)
            else:
                text = " ".join(part for part in (text, value) if part)
        elif chip.key == "since":
            since = _parse_time(value)
        elif chip.key == "until":
            until = _parse_time(value)
        elif chip.key == "correlation":
            correlation = value
    return ActivityFilter(
        kinds=tuple(kinds),
        exclude_kinds=tuple(exclude_kinds),
        actors=tuple(actors),
        exclude_actors=tuple(exclude_actors),
        subjects=tuple(subjects),
        severities=tuple(severities),
        minimum_severity=minimum,
        text=text,
        since=since,
        until=until,
        correlation_id=correlation,
        tags=tuple(tags),
        free_text=tuple(free_text),
    )


def combine_filters(*filters: ActivityFilter) -> Callable[[ActivityEntry], bool]:
    """Combine filters with logical AND."""
    predicates = [event_filter.compile() for event_filter in filters]

    def predicate(entry: ActivityEntry) -> bool:
        return all(item(entry) for item in predicates)

    return predicate


def any_filter(*filters: ActivityFilter) -> Callable[[ActivityEntry], bool]:
    """Combine filters with logical OR."""
    predicates = [event_filter.compile() for event_filter in filters]

    def predicate(entry: ActivityEntry) -> bool:
        return any(item(entry) for item in predicates)

    return predicate


def make_filter_chips(event_filter: ActivityFilter) -> tuple[FilterChip, ...]:
    """Render a filter back into UI chips."""
    chips: list[FilterChip] = []
    for key, values in (
        ("kind", event_filter.kinds),
        ("kind", event_filter.exclude_kinds),
        ("actor", event_filter.actors),
        ("subject", event_filter.subjects),
        ("severity", event_filter.severities),
        ("tag", event_filter.tags),
    ):
        operator = (
            FILTER_EXCLUDE
            if key == "kind" and values == event_filter.exclude_kinds
            else FILTER_INCLUDE
        )
        if key == "kind" and values == event_filter.kinds and not values:
            continue
        for value in values:
            chips.append(FilterChip(key=key, value=value, operator=operator))
    if event_filter.minimum_severity:
        chips.append(FilterChip("severity", event_filter.minimum_severity))
    if event_filter.text:
        chips.append(FilterChip("text", event_filter.text))
    return tuple(chips)


__all__ = [
    "FILTER_KEYS",
    "FILTER_OPERATORS",
    "ActivityFilter",
    "any_filter",
    "combine_filters",
    "filter_definitions",
    "make_filter_chips",
    "parse_query",
    "validate_query",
]
