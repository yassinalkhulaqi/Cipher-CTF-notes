"""Bounded, redacted request/response history for the developer console."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from redscribe.v3.api_sdk.models import SdkRequest, SdkResponse
from redscribe.v3.clock import Clock as SdkClock
from redscribe.v3.clock import SystemClock as SystemSdkClock


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One sanitized history entry. Body values are never retained."""

    sequence: int
    namespace: str
    action: str
    body_keys: tuple[str, ...]
    status: int
    request_id: str
    etag: str
    error_code: str
    duration_ms: float
    timestamp: float
    cached: bool = False
    capability: str = ""

    @property
    def route(self) -> str:
        """Return the canonical route."""
        return f"/api/v3/{self.namespace}/{self.action}"

    @property
    def failed(self) -> bool:
        """Return whether the call produced an error."""
        return bool(self.error_code)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "sequence": self.sequence,
            "route": self.route,
            "body_keys": list(self.body_keys),
            "status": self.status,
            "request_id": self.request_id,
            "etag": self.etag,
            "error_code": self.error_code,
            "duration_ms": round(self.duration_ms, 3),
            "timestamp": self.timestamp,
            "cached": self.cached,
            "capability": self.capability,
        }


class CallLog:
    """Fixed-size history with deterministic filtering."""

    def __init__(self, *, limit: int = 200, clock: SdkClock | None = None) -> None:
        if limit < 1:
            raise ValueError("History limit must be positive")
        self._limit = limit
        self._clock: SdkClock = clock or SystemSdkClock()
        self._entries: list[CallRecord] = []
        self._sequence = 0

    def record(
        self,
        request: SdkRequest,
        response: SdkResponse,
        duration_ms: float,
    ) -> CallRecord:
        """Append a sanitized entry and evict the oldest when full."""
        self._sequence += 1
        entry = CallRecord(
            sequence=self._sequence,
            namespace=request.namespace,
            action=request.action,
            body_keys=tuple(sorted(str(key) for key in request.body)),
            status=response.status,
            request_id=response.request_id,
            etag=response.etag,
            error_code=response.code,
            duration_ms=max(0.0, float(duration_ms)),
            timestamp=self._clock.now_timestamp(),
            cached=response.cached,
            capability=request.capability,
        )
        self._entries.append(entry)
        if len(self._entries) > self._limit:
            del self._entries[: len(self._entries) - self._limit]
        return entry

    def entries(self) -> tuple[CallRecord, ...]:
        """Return all retained entries in call order."""
        return tuple(self._entries)

    def filter(
        self,
        *,
        namespace: str = "",
        action: str = "",
        errors_only: bool = False,
        limit: int | None = None,
    ) -> tuple[CallRecord, ...]:
        """Return entries matching the supplied criteria."""
        matches: list[CallRecord] = []
        for entry in self._entries:
            if namespace and entry.namespace != namespace:
                continue
            if action and entry.action != action:
                continue
            if errors_only and not entry.failed:
                continue
            matches.append(entry)
        if limit is not None:
            if limit < 0:
                raise ValueError("Limit cannot be negative")
            return tuple(matches[:limit])
        return tuple(matches)

    def last(self) -> CallRecord | None:
        """Return the most recent entry."""
        return self._entries[-1] if self._entries else None

    def clear(self) -> None:
        """Drop all retained entries."""
        self._entries.clear()

    def extend(self, records: Iterable[CallRecord]) -> None:
        """Append previously created entries in order."""
        for record in records:
            self._entries.append(record)
            if len(self._entries) > self._limit:
                del self._entries[: len(self._entries) - self._limit]

    def size(self) -> int:
        """Return the retained entry count."""
        return len(self._entries)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "limit": self._limit,
            "entries": [entry.as_dict() for entry in self._entries],
        }
