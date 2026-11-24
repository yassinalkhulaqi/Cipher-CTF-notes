"""Composable filters for activity and event streams."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.events.types import EventRecord, EventSeverity

Predicate = Callable[[EventRecord], bool]


@dataclass(frozen=True, slots=True)
class EventFilter:
    """Declarative filter compiled into a predicate."""

    kinds: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()
    minimum_severity: EventSeverity | None = None
    after: float | None = None
    before: float | None = None
    correlation_id: str = ""
    text: str = ""
    exclude_kinds: tuple[str, ...] = field(default_factory=tuple)

    def compile(self) -> Predicate:
        """Compile the declarative filter into a callable predicate."""
        kinds = frozenset(self.kinds)
        excluded = frozenset(self.exclude_kinds)
        subjects = frozenset(self.subjects)
        actors = frozenset(self.actors)
        text = self.text.strip().casefold()

        def predicate(record: EventRecord) -> bool:
            if kinds and record.kind not in kinds:
                return False
            if excluded and record.kind in excluded:
                return False
            if subjects and record.subject_ref not in subjects:
                return False
            if actors and record.event.actor not in actors:
                return False
            if (
                self.minimum_severity is not None
                and record.event.severity.rank < self.minimum_severity.rank
            ):
                return False
            if self.after is not None and record.timestamp <= self.after:
                return False
            if self.before is not None and record.timestamp >= self.before:
                return False
            if self.correlation_id and record.event.correlation_id != self.correlation_id:
                return False
            return not (text and text not in _searchable_text(record))

        return predicate

    def apply(self, records: tuple[EventRecord, ...]) -> tuple[EventRecord, ...]:
        """Filter a sequence of records."""
        predicate = self.compile()
        return tuple(record for record in records if predicate(record))

    @classmethod
    def parse(cls, query: str) -> EventFilter:
        """Parse a compact filter query such as ``kind:created severity:warning``."""
        kinds: list[str] = []
        subjects: list[str] = []
        actors: list[str] = []
        severity: EventSeverity | None = None
        text_parts: list[str] = []
        for token in query.split():
            if ":" not in token:
                text_parts.append(token)
                continue
            key, value = token.split(":", 1)
            if key == "kind":
                kinds.append(value)
            elif key == "subject":
                subjects.append(value)
            elif key == "actor":
                actors.append(value)
            elif key == "severity":
                severity = EventSeverity(value.casefold())
            elif key == "text":
                text_parts.append(value)
            else:
                text_parts.append(token)
        return cls(
            kinds=tuple(kinds),
            subjects=tuple(subjects),
            actors=tuple(actors),
            minimum_severity=severity,
            text=" ".join(text_parts),
        )


def _searchable_text(record: EventRecord) -> str:
    """Build a searchable blob from an event record."""
    values: list[str] = [record.kind, record.subject_ref, record.event.actor]
    values.extend(str(value) for value in record.event.payload.values())
    return " ".join(values).casefold()


def combine(*filters: EventFilter) -> Predicate:
    """Combine filters with logical AND."""
    predicates = [event_filter.compile() for event_filter in filters]

    def predicate(record: EventRecord) -> bool:
        return all(item(record) for item in predicates)

    return predicate


def any_of(*filters: EventFilter) -> Predicate:
    """Combine filters with logical OR."""
    predicates = [event_filter.compile() for event_filter in filters]

    def predicate(record: EventRecord) -> bool:
        return any(item(record) for item in predicates)

    return predicate


def count_by_kind(records: tuple[EventRecord, ...]) -> dict[str, int]:
    """Count records grouped by event kind."""
    counts: dict[str, int] = {}
    for record in records:
        counts[record.kind] = counts.get(record.kind, 0) + 1
    return dict(sorted(counts.items()))


def latest_per_subject(records: tuple[EventRecord, ...]) -> dict[str, EventRecord]:
    """Return the latest record for each subject."""
    result: dict[str, EventRecord] = {}
    for record in records:
        if record.subject_ref:
            result[record.subject_ref] = record
    return result


def payload_values(records: tuple[EventRecord, ...], key: str) -> tuple[Any, ...]:
    """Extract one payload key from every record that has it."""
    return tuple(record.event.payload[key] for record in records if key in record.event.payload)
