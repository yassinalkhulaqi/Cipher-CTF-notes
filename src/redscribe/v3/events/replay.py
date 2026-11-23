"""Replay and projection utilities for the event stream."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from redscribe.v3.events.filters import EventFilter
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.events.types import EventRecord

State = TypeVar("State")
Reducer = Callable[[State, EventRecord], State]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Result of replaying events into an accumulated state."""

    state: Any
    consumed: int
    skipped: int
    last_sequence: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary."""
        return {
            "consumed": self.consumed,
            "skipped": self.skipped,
            "last_sequence": self.last_sequence,
        }


class EventReplay:
    """Deterministic event replay with filtering and redaction."""

    def __init__(self, records: tuple[EventRecord, ...]) -> None:
        self._records = records

    def fold(
        self,
        reducer: Reducer[State],
        initial: State,
        *,
        event_filter: EventFilter | None = None,
    ) -> ReplayResult:
        """Fold matching records into a state value."""
        state = initial
        consumed = 0
        skipped = 0
        last_sequence = 0
        predicate = event_filter.compile() if event_filter is not None else None
        for record in self._records:
            if predicate is not None and not predicate(record):
                skipped += 1
                continue
            state = reducer(state, record)
            consumed += 1
            last_sequence = record.sequence
        return ReplayResult(
            state=state, consumed=consumed, skipped=skipped, last_sequence=last_sequence
        )

    def collect(
        self,
        *,
        event_filter: EventFilter | None = None,
        redactor: RedactionPolicy | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Return redacted record dictionaries."""
        predicate = event_filter.compile() if event_filter is not None else None
        result: list[dict[str, Any]] = []
        for record in self._records:
            if predicate is not None and not predicate(record):
                continue
            payload = record.event.payload
            if redactor is not None:
                payload = redactor.apply(payload)
            result.append(record.as_dict() | {"payload": dict(payload)})
        return tuple(result)

    def project(
        self,
        key: str,
        *,
        event_filter: EventFilter | None = None,
    ) -> dict[str, list[Any]]:
        """Group payload values by a key into lists."""
        projection: dict[str, list[Any]] = {}
        predicate = event_filter.compile() if event_filter is not None else None
        for record in self._records:
            if predicate is not None and not predicate(record):
                continue
            if key not in record.event.payload:
                continue
            group = str(record.event.payload[key])
            projection.setdefault(group, []).append(record.as_dict())
        return projection

    def count(self, *, event_filter: EventFilter | None = None) -> int:
        """Count matching records."""
        predicate = event_filter.compile() if event_filter is not None else None
        return sum(1 for record in self._records if predicate is None or predicate(record))

    def subjects(self) -> tuple[str, ...]:
        """Return distinct non-empty subjects."""
        return tuple(sorted({record.subject_ref for record in self._records if record.subject_ref}))


def count_reducer(state: dict[str, int], record: EventRecord) -> dict[str, int]:
    """Reducer that counts events by kind."""
    updated = dict(state)
    updated[record.kind] = updated.get(record.kind, 0) + 1
    return updated


def append_reducer(state: tuple[EventRecord, ...], record: EventRecord) -> tuple[EventRecord, ...]:
    """Reducer that appends records to a tuple."""
    return (*state, record)
