"""In-process event bus with isolated subscribers and durable recording."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.events.types import DomainEvent, EventRecord

Subscriber = Callable[[EventRecord], None]
WildcardSubscriber = Callable[[EventRecord], None]


class EventBusError(RuntimeError):
    """Raised for invalid bus configuration."""


class EventBus:
    """Synchronous event dispatcher with a durable outbox.

    Subscriber failures are captured instead of propagating, so one feature can
    never break a mutation performed by another. Captured errors are exposed for
    the B08 activity dashboard and for tests.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._wildcard: list[WildcardSubscriber] = []
        self._records: list[EventRecord] = []
        self._errors: list[dict[str, Any]] = []
        self._sequence = 0

    def subscribe(self, kind: str, callback: Subscriber) -> None:
        """Subscribe to one event kind."""
        if not kind:
            raise EventBusError("Subscription kind cannot be empty")
        self._subscribers[kind].append(callback)

    def subscribe_all(self, callback: WildcardSubscriber) -> None:
        """Subscribe to every event kind."""
        self._wildcard.append(callback)

    def unsubscribe(self, kind: str, callback: Subscriber) -> bool:
        """Remove a subscription, returning whether it existed."""
        callbacks = self._subscribers.get(kind)
        if callbacks is None or callback not in callbacks:
            return False
        callbacks.remove(callback)
        return True

    def publish(
        self,
        event: DomainEvent,
        *,
        request_id: str = "",
    ) -> EventRecord:
        """Record and dispatch an event to all matching subscribers."""
        self._sequence += 1
        record = EventRecord(
            sequence=self._sequence,
            event=event,
            timestamp=self._clock.now_timestamp(),
            request_id=request_id,
        )
        self._records.append(record)
        for callback in tuple(self._subscribers.get(event.kind, ())):
            self._safe_call(callback, record)
        for callback in tuple(self._wildcard):
            self._safe_call(callback, record)
        return record

    def _safe_call(self, callback: Callable[[EventRecord], None], record: EventRecord) -> None:
        """Invoke a subscriber and capture failures."""
        try:
            callback(record)
        except Exception as error:
            self._errors.append(
                {
                    "sequence": record.sequence,
                    "kind": record.kind,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )

    def records(self) -> tuple[EventRecord, ...]:
        """Return all recorded events in sequence order."""
        return tuple(self._records)

    def records_since(self, sequence: int) -> tuple[EventRecord, ...]:
        """Return events recorded after a sequence number."""
        return tuple(record for record in self._records if record.sequence > sequence)

    def of_kind(self, kind: str) -> tuple[EventRecord, ...]:
        """Return events of one kind."""
        return tuple(record for record in self._records if record.kind == kind)

    def errors(self) -> tuple[dict[str, Any], ...]:
        """Return captured subscriber failures."""
        return tuple(dict(error) for error in self._errors)

    def last(self) -> EventRecord | None:
        """Return the most recent event, if any."""
        return self._records[-1] if self._records else None

    def clear(self) -> None:
        """Drop recorded events and captured errors."""
        self._records.clear()
        self._errors.clear()

    def size(self) -> int:
        """Return the number of recorded events."""
        return len(self._records)

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable bus snapshot."""
        return {
            "sequence": self._sequence,
            "events": [record.as_dict() for record in self._records],
            "errors": [dict(error) for error in self._errors],
        }
