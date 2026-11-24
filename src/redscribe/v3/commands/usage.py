"""Recent/frequent command usage model with time decay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.commands.types import CommandInvocation


class UsageError(ValueError):
    """Raised for malformed usage data."""


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """One recorded command invocation."""

    command_id: str
    timestamp: float
    pane_id: str = ""
    context_ref: str = ""

    def __post_init__(self) -> None:
        if not self.command_id:
            raise UsageError("Usage event needs a command id")
        if self.timestamp < 0:
            raise UsageError("Usage timestamp cannot be negative")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "command_id": self.command_id,
            "timestamp": self.timestamp,
            "pane_id": self.pane_id,
            "context_ref": self.context_ref,
        }


@dataclass(frozen=True, slots=True)
class UsageStats:
    """Aggregated usage for one command."""

    command_id: str
    count: int
    first_timestamp: float
    last_timestamp: float

    @property
    def span(self) -> float:
        """Time between the first and last use."""
        return max(0.0, self.last_timestamp - self.first_timestamp)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "command_id": self.command_id,
            "count": self.count,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
        }


class UsageModel:
    """Tracks usage as data so ranks stay deterministic for a fixed clock."""

    def __init__(self, *, half_life_seconds: float = 86400.0, clock: Clock | None = None) -> None:
        if half_life_seconds <= 0:
            raise UsageError("half_life_seconds must be positive")
        self._half_life = half_life_seconds
        self._clock: Clock = clock or SystemClock()
        self._events: dict[str, list[UsageEvent]] = {}

    def record(
        self,
        invocation: CommandInvocation,
        *,
        pane_id: str = "",
        context_ref: str = "",
        now: float | None = None,
    ) -> UsageEvent:
        """Record an invocation and return the stored event."""
        timestamp = self._clock.now_timestamp() if now is None else now
        event = UsageEvent(
            command_id=invocation.command_id,
            timestamp=timestamp,
            pane_id=pane_id,
            context_ref=context_ref or invocation.context_ref,
        )
        self._events.setdefault(event.command_id, []).append(event)
        return event

    def stats(self, command_id: str) -> UsageStats:
        """Return aggregate usage for a command, even if never used."""
        events = self._events.get(command_id, ())
        if not events:
            return UsageStats(command_id, 0, 0.0, 0.0)
        return UsageStats(
            command_id=command_id,
            count=len(events),
            first_timestamp=min(event.timestamp for event in events),
            last_timestamp=max(event.timestamp for event in events),
        )

    def recent(self, limit: int = 10) -> tuple[UsageEvent, ...]:
        """Return the most recent distinct command uses, newest first."""
        if limit < 1:
            raise UsageError("limit must be positive")
        flat = [event for events in self._events.values() for event in events]
        ordered = sorted(flat, key=lambda event: (-event.timestamp, event.command_id))
        seen: set[str] = set()
        result: list[UsageEvent] = []
        for event in ordered:
            if event.command_id in seen:
                continue
            seen.add(event.command_id)
            result.append(event)
            if len(result) == limit:
                break
        return tuple(result)

    def frequent(self, limit: int = 10) -> tuple[tuple[str, int], ...]:
        """Return commands ordered by count, then by most recent use."""
        if limit < 1:
            raise UsageError("limit must be positive")
        rows = [
            (key, len(events), max(e.timestamp for e in events))
            for key, events in self._events.items()
        ]
        rows.sort(key=lambda row: (-row[1], -row[2], row[0]))
        return tuple((key, count) for key, count, _ in rows[:limit])

    def recency_score(self, command_id: str, now: float) -> float:
        """Return exponential decay from the last use, in ``[0, 1]``."""
        stats = self.stats(command_id)
        if stats.count == 0:
            return 0.0
        age = max(0.0, now - stats.last_timestamp)
        return math.exp(-math.log(2) * age / self._half_life)

    def frequency_score(self, command_id: str) -> float:
        """Return a saturated frequency score in ``[0, 1]``."""
        count = self.stats(command_id).count
        if count == 0:
            return 0.0
        return min(1.0, math.log1p(count) / math.log1p(20))

    def score(self, command_id: str, now: float | None = None) -> float:
        """Combine recency and frequency into a ranking boost."""
        timestamp = self._clock.now_timestamp() if now is None else now
        return 0.6 * self.recency_score(command_id, timestamp) + 0.4 * self.frequency_score(
            command_id
        )

    def prune(self, before: float) -> int:
        """Drop events older than a timestamp and return how many were removed."""
        removed = 0
        for command_id, events in tuple(self._events.items()):
            kept = tuple(event for event in events if event.timestamp >= before)
            removed += len(events) - len(kept)
            if kept:
                self._events[command_id] = list(kept)
            else:
                self._events.pop(command_id, None)
        return removed

    def clear(self) -> None:
        """Forget all recorded usage."""
        self._events.clear()

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable usage snapshot."""
        events = [event for values in self._events.values() for event in values]
        events.sort(key=lambda event: (event.timestamp, event.command_id))
        return {"half_life_seconds": self._half_life, "events": [e.as_dict() for e in events]}

    def load(self, snapshot: dict[str, Any]) -> None:
        """Restore a previously captured usage snapshot."""
        raw_events = snapshot.get("events", ())
        if not isinstance(raw_events, list):
            raise UsageError("Usage snapshot events must be a list")
        restored: dict[str, list[UsageEvent]] = {}
        for raw in raw_events:
            if not isinstance(raw, dict):
                raise UsageError("Usage event must be an object")
            event = UsageEvent(
                command_id=str(raw.get("command_id", "")),
                timestamp=float(raw.get("timestamp", 0.0)),
                pane_id=str(raw.get("pane_id", "")),
                context_ref=str(raw.get("context_ref", "")),
            )
            restored.setdefault(event.command_id, []).append(event)
        self._events = restored

    def size(self) -> int:
        """Return the number of recorded events."""
        return sum(len(events) for events in self._events.values())
