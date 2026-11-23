"""Durable outbox persistence for domain events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from redscribe.v3.events.types import EventRecord


class OutboxStore(Protocol):
    """Storage contract for an append-only event outbox."""

    def append(self, record: EventRecord) -> None:
        """Append one event record."""
        ...

    def all(self) -> tuple[EventRecord, ...]:
        """Return all records in sequence order."""
        ...

    def checkpoint(self) -> int:
        """Return the highest persisted sequence number."""
        ...


@dataclass(slots=True)
class MemoryOutbox:
    """In-memory outbox used by services and tests."""

    _records: list[EventRecord] | None = None

    def __post_init__(self) -> None:
        if self._records is None:
            self._records = []

    def append(self, record: EventRecord) -> None:
        """Append one event record."""
        assert self._records is not None
        self._records.append(record)

    def all(self) -> tuple[EventRecord, ...]:
        """Return all records."""
        assert self._records is not None
        return tuple(self._records)

    def checkpoint(self) -> int:
        """Return the highest sequence number."""
        assert self._records is not None
        return self._records[-1].sequence if self._records else 0

    def clear(self) -> None:
        """Drop all records."""
        assert self._records is not None
        self._records.clear()


class JsonFileOutbox:
    """Append-only JSON Lines outbox for local vault persistence."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    def append(self, record: EventRecord) -> None:
        """Append one record as a JSON line."""
        line = json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":"))
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def all(self) -> tuple[EventRecord, ...]:
        """Read every record, skipping corrupt trailing lines."""
        records: list[EventRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                records.append(_record_from_dict(payload))
            except (ValueError, KeyError, TypeError):
                continue
        return tuple(records)

    def checkpoint(self) -> int:
        """Return the highest sequence number in the file."""
        return max((record.sequence for record in self.all()), default=0)


class OutboxWriter:
    """Writes published events into a durable outbox."""

    def __init__(self, store: OutboxStore) -> None:
        self._store = store
        self._written: set[int] = set()

    def write(self, record: EventRecord) -> bool:
        """Write a record once, returning whether it was new."""
        if record.sequence in self._written:
            return False
        self._store.append(record)
        self._written.add(record.sequence)
        return True

    def write_many(self, records: tuple[EventRecord, ...]) -> int:
        """Write multiple records, returning the number written."""
        return sum(1 for record in records if self.write(record))

    def checkpoint(self) -> int:
        """Return the store checkpoint."""
        return self._store.checkpoint()

    def contains(self, sequence: int) -> bool:
        """Return whether a sequence was already written."""
        return sequence in self._written


def _record_from_dict(payload: dict[str, Any]) -> EventRecord:
    """Reconstruct an event record from persisted JSON."""
    from redscribe.v3.entities.types import EntityId
    from redscribe.v3.events.types import DomainEvent, EventSeverity

    subject_raw = payload.get("subject")
    subject = EntityId.parse(subject_raw) if subject_raw else None
    event = DomainEvent(
        kind=payload["kind"],
        subject=subject,
        actor=payload.get("actor", "local"),
        severity=EventSeverity(payload.get("severity", "info")),
        payload=dict(payload.get("payload", {})),
        correlation_id=payload.get("correlation_id", ""),
    )
    return EventRecord(
        sequence=payload["sequence"],
        event=event,
        timestamp=payload["timestamp"],
        request_id=payload.get("request_id", ""),
    )
