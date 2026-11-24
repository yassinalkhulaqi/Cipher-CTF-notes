"""Batched event flushing for high-volume local event streams.

The batcher is storage-agnostic: it writes through any sink that implements
``write_many`` (the V3 ``OutboxWriter`` does). Size, byte, and time triggers are
all injectable, so the benchmark can measure deterministic flush behavior with
a fixed clock and no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from redscribe.v3.clock import Clock, FixedClock, SystemClock
from redscribe.v3.events.types import EventRecord
from redscribe.v3.performance.meter import Meter
from redscribe.v3.performance.models import FlushReport
from redscribe.v3.performance.workers import estimate_event_bytes


class BatchSink(Protocol):
    """Minimal sink contract satisfied by ``OutboxWriter``."""

    def write_many(self, records: tuple[EventRecord, ...]) -> int:
        """Write a batch and return the number of accepted records."""
        ...

    def checkpoint(self) -> int:
        """Return the highest persisted sequence number."""
        ...


@dataclass(frozen=True, slots=True)
class FlushPolicy:
    """Thresholds that trigger a batch flush."""

    max_size: int = 128
    max_bytes: int = 32_768
    max_lag: float = 1.0

    def __post_init__(self) -> None:
        if self.max_size < 1:
            raise ValueError("max_size must be positive")
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if self.max_lag <= 0:
            raise ValueError("max_lag must be positive")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "max_size": self.max_size,
            "max_bytes": self.max_bytes,
            "max_lag": self.max_lag,
        }


@dataclass(slots=True)
class EventBatcher:
    """Accumulate events and flush them through a durable sink."""

    sink: BatchSink
    policy: FlushPolicy = field(default_factory=FlushPolicy)
    clock: Clock = field(default_factory=SystemClock)
    meter: Meter = field(default_factory=Meter)

    _pending: list[EventRecord] = field(default_factory=list, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _received: int = field(default=0, init=False)
    _flushed: int = field(default=0, init=False)
    _batches: int = field(default=0, init=False)
    _dropped: int = field(default=0, init=False)
    _seen: set[int] = field(default_factory=set, init=False)

    @classmethod
    def with_fixed_clock(cls, sink: BatchSink, start: float = 0.0) -> EventBatcher:
        """Build a deterministic batcher for tests and benchmarks."""
        return cls(sink=sink, clock=FixedClock(start=start, step=0.0))

    @property
    def pending(self) -> tuple[EventRecord, ...]:
        """Records waiting for the next flush."""
        return tuple(self._pending)

    @property
    def checkpoint(self) -> int:
        """Highest sequence persisted by the sink."""
        return self.sink.checkpoint()

    def append(self, record: EventRecord, *, now: float | None = None) -> bool:
        """Append one record, returning whether a threshold flush occurred."""
        if record.sequence in self._seen:
            self._dropped += 1
            return False
        self._seen.add(record.sequence)
        self._received += 1
        self.meter.record("event_append")
        timestamp = self.clock.now_timestamp() if now is None else now
        triggered = bool(self._pending) and self._should_flush(timestamp)
        if triggered:
            self.flush()
        if not self._pending:
            self._opened_at = timestamp
        self._pending.append(record)
        return triggered

    def _should_flush(self, timestamp: float) -> bool:
        """Return whether any flush threshold has been crossed."""
        if len(self._pending) >= self.policy.max_size:
            return True
        if estimate_event_bytes(self._pending) >= self.policy.max_bytes:
            return True
        return timestamp - self._opened_at >= self.policy.max_lag

    def flush(self) -> int:
        """Write the pending batch, returning the number of accepted records."""
        if not self._pending:
            return 0
        batch = tuple(self._pending)
        accepted = self.sink.write_many(batch)
        self._flushed += accepted
        self._batches += 1
        self.meter.record("event_flush", len(batch))
        self._pending.clear()
        self._opened_at = self.clock.now_timestamp()
        return accepted

    def drain(self) -> FlushReport:
        """Flush everything and return a session summary."""
        self.flush()
        return self.report()

    def report(self) -> FlushReport:
        """Return the accumulated flush summary."""
        return FlushReport(
            received=self._received,
            flushed=self._flushed,
            batches=self._batches,
            checkpoint=self.checkpoint,
            dropped=self._dropped,
        )

    def reset(self) -> None:
        """Clear pending records and counters without touching the sink."""
        self._pending.clear()
        self._seen.clear()
        self._received = 0
        self._flushed = 0
        self._batches = 0
        self._dropped = 0
        self._opened_at = 0.0
