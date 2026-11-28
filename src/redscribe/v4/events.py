"""Typed domain events and a durable, redactable in-process bus.

Every v4 feature emits events through this module instead of ad-hoc logging.
Events are plain dataclasses; the bus is synchronous and deterministic, with an
optional durable outbox that records redacted event payloads for replay.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from redscribe.v4.contracts import EntityKind, new_entity_id


class EventKind(str, Enum):
    """Stable event names emitted across v4 features."""

    CAPTURE_CREATED = "capture.created"
    CAPTURE_TRAGED = "capture.traged"
    FINDING_CREATED = "finding.created"
    FINDING_SCORED = "finding.scored"
    FINDING_RETESTED = "finding.retested"
    EVIDENCE_ADDED = "evidence.added"
    EVIDENCE_HASHED = "evidence.hashed"
    BLOCK_EDITED = "block.edited"
    QUERY_SAVED = "query.saved"
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    REPORT_RENDERED = "report.rendered"
    GRAPH_FILTERED = "graph.filtered"
    VAULT_LOCKED = "vault.locked"
    VAULT_UNLOCKED = "vault.unlocked"
    KEY_ROTATED = "key.rotated"
    PREFERENCE_CHANGED = "preference.changed"


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a trailing Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base event carried by the bus."""

    kind: EventKind
    aggregate_id: str
    aggregate_kind: EntityKind
    occurred_at: str = field(default_factory=utc_now)
    event_id: str = field(default_factory=new_entity_id)
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.aggregate_id:
            raise ValueError("aggregate_id must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "aggregate_id": self.aggregate_id,
            "aggregate_kind": self.aggregate_kind.value,
            "occurred_at": self.occurred_at,
            "event_id": self.event_id,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainEvent:
        return cls(
            kind=EventKind(str(data.get("kind", ""))),
            aggregate_id=str(data.get("aggregate_id", "")),
            aggregate_kind=EntityKind.parse(str(data.get("aggregate_kind", ""))),
            occurred_at=str(data.get("occurred_at", utc_now())),
            event_id=str(data.get("event_id", new_entity_id())),
            payload=dict(data.get("payload", {})),
        )


Subscriber = Callable[[DomainEvent], None]
Redactor = Callable[[dict[str, Any]], dict[str, Any]]


def default_redactor(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip obvious secret-looking keys from a stored payload."""
    secret_keys = {"password", "secret", "token", "key", "credential", "authorization"}
    redacted: dict[str, Any] = {}
    for name, value in payload.items():
        if name.casefold() in secret_keys:
            redacted[name] = "[redacted]"
        elif isinstance(value, dict):
            redacted[name] = default_redactor(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            redacted[name] = value
        else:
            redacted[name] = str(value)
    return redacted


@dataclass(slots=True)
class OutboxRecord:
    """A redacted event persisted for replay."""

    event_id: str
    kind: str
    aggregate_id: str
    occurred_at: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at,
            "payload": dict(self.payload),
        }


class InMemoryOutbox:
    """A deterministic outbox with cap-based pruning."""

    def __init__(self, capacity: int = 1000, redactor: Redactor = default_redactor) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.redactor = redactor
        self._records: list[OutboxRecord] = []

    def append(self, event: DomainEvent) -> OutboxRecord:
        record = OutboxRecord(
            event_id=event.event_id,
            kind=event.kind.value,
            aggregate_id=event.aggregate_id,
            occurred_at=event.occurred_at,
            payload=self.redactor(dict(event.payload)),
        )
        self._records.append(record)
        if len(self._records) > self.capacity:
            del self._records[: len(self._records) - self.capacity]
        return record

    def records(self, kind: EventKind | None = None) -> list[OutboxRecord]:
        if kind is None:
            return list(self._records)
        return [record for record in self._records if record.kind == kind.value]

    def replay(self, kind: EventKind | None = None) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for record in self.records(kind):
            events.append(
                DomainEvent(
                    kind=EventKind(record.kind),
                    aggregate_id=record.aggregate_id,
                    aggregate_kind=EntityKind.NOTE,
                    occurred_at=record.occurred_at,
                    event_id=record.event_id,
                    payload=dict(record.payload),
                )
            )
        return events

    def clear(self) -> None:
        self._records.clear()


class EventBus:
    """A synchronous, ordered event bus with an optional durable outbox."""

    def __init__(self, outbox: InMemoryOutbox | None = None) -> None:
        self.outbox = outbox
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._published: list[DomainEvent] = []

    def subscribe(self, kind: EventKind, subscriber: Subscriber) -> None:
        self._subscribers.setdefault(kind.value, []).append(subscriber)

    def unsubscribe(self, kind: EventKind, subscriber: Subscriber) -> None:
        subscribers = self._subscribers.get(kind.value, [])
        self._subscribers[kind.value] = [item for item in subscribers if item is not subscriber]

    def publish(self, event: DomainEvent) -> None:
        self._published.append(event)
        if self.outbox is not None:
            self.outbox.append(event)
        for subscriber in list(self._subscribers.get(event.kind.value, [])):
            subscriber(event)

    def publish_many(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            self.publish(event)

    @property
    def published(self) -> list[DomainEvent]:
        return list(self._published)

    def subscriber_count(self, kind: EventKind) -> int:
        return len(self._subscribers.get(kind.value, []))

    def clear(self) -> None:
        self._subscribers.clear()
        self._published.clear()


def event_from_dataclass(
    kind: EventKind,
    aggregate_id: str,
    aggregate_kind: EntityKind,
    value: Any,
) -> DomainEvent:
    """Build an event from a dataclass payload, normalizing nested dataclasses."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("value must be a dataclass instance")
    payload = asdict(value)
    return DomainEvent(
        kind=kind,
        aggregate_id=aggregate_id,
        aggregate_kind=aggregate_kind,
        payload=payload,
    )
