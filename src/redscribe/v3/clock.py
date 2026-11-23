"""Injectable clock helpers for deterministic V3 services and tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final, Protocol, runtime_checkable

_EPOCH: Final[datetime] = datetime(2020, 1, 1, tzinfo=timezone.utc)


@runtime_checkable
class Clock(Protocol):
    """Minimal clock interface used by V3 services."""

    def now_timestamp(self) -> float:
        """Return the current Unix timestamp in seconds."""
        ...

    def now_iso(self) -> str:
        """Return the current time as an ISO-8601 UTC string."""
        ...


class SystemClock:
    """Wall-clock implementation."""

    def now_timestamp(self) -> float:
        """Return the current Unix timestamp."""
        return datetime.now(tz=timezone.utc).timestamp()

    def now_iso(self) -> str:
        """Return the current time as an ISO-8601 UTC string."""
        return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


class FixedClock:
    """Deterministic clock that optionally advances on each read."""

    def __init__(self, start: float = 0.0, *, step: float = 0.0) -> None:
        self._current = start
        self._step = step

    def now_timestamp(self) -> float:
        """Return the fixed timestamp and advance by the configured step."""
        current = self._current
        self._current += self._step
        return current

    def now_iso(self) -> str:
        """Return the fixed timestamp in ISO-8601 UTC form."""
        return (
            datetime.fromtimestamp(self.now_timestamp(), tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self._current += seconds


def epoch_start() -> float:
    """Return the project epoch used by benchmark fixtures."""
    return _EPOCH.timestamp()


def iso_from_timestamp(timestamp: float) -> str:
    """Format a Unix timestamp as an ISO-8601 UTC string."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_from_iso(value: str) -> float:
    """Parse an ISO-8601 UTC string produced by this module."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed.timestamp()
