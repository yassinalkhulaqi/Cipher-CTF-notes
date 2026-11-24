"""Since-last-visit tracking for the activity stream."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from redscribe.v3.activity.models import (
    ActivityEntry,
    SinceLastVisit,
    VisitMarker,
)
from redscribe.v3.clock import Clock, SystemClock, iso_from_timestamp

MAX_IDENTITY_LENGTH = 120


class VisitError(ValueError):
    """Raised for an invalid visit identity."""


def normalize_identity(identity: str) -> str:
    """Validate and normalize a visit identity."""
    if not isinstance(identity, str) or not identity.strip():
        raise VisitError("Visit identity cannot be blank")
    cleaned = " ".join(identity.split())
    if len(cleaned) > MAX_IDENTITY_LENGTH:
        raise VisitError(f"Visit identity must be at most {MAX_IDENTITY_LENGTH} characters")
    return cleaned


def since_last_visit(
    entries: Iterable[ActivityEntry],
    marker: VisitMarker | None,
    *,
    identity: str = "local",
    limit: int | None = None,
) -> SinceLastVisit:
    """Compute new entries relative to a visit marker.

    When no marker exists, every entry is treated as new (a first visit).
    """
    rows = tuple(entries)
    if marker is None:
        new = rows
    else:
        new = tuple(
            entry
            for entry in rows
            if entry.sequence > marker.sequence or entry.timestamp > marker.timestamp
        )
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for entry in new:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        by_severity[entry.severity] = by_severity.get(entry.severity, 0) + 1
    shown = new if limit is None else new[-max(0, limit) :]
    return SinceLastVisit(
        identity=identity,
        marker=marker,
        entries=shown,
        count=len(new),
        by_kind=dict(sorted(by_kind.items())),
        by_severity=dict(sorted(by_severity.items())),
        first_timestamp=min((entry.timestamp for entry in new), default=None),
        last_timestamp=max((entry.timestamp for entry in new), default=None),
    )


class VisitTracker:
    """Stores last-visit markers for stream personas."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._markers: dict[str, VisitMarker] = {}

    def mark(
        self,
        identity: str,
        *,
        timestamp: float | None = None,
        sequence: int = 0,
        note: str = "",
    ) -> VisitMarker:
        """Record the current (or supplied) visit point for an identity."""
        key = normalize_identity(identity)
        if sequence < 0:
            raise VisitError("Sequence cannot be negative")
        moment = self._clock.now_timestamp() if timestamp is None else float(timestamp)
        marker = VisitMarker(
            identity=key,
            timestamp=moment,
            sequence=sequence,
            iso_timestamp=iso_from_timestamp(moment),
            note=note.strip()[:240],
        )
        self._markers[key] = marker
        return marker

    def get(self, identity: str) -> VisitMarker | None:
        """Return a marker, if one exists."""
        return self._markers.get(normalize_identity(identity))

    def has(self, identity: str) -> bool:
        """Return whether an identity has a marker."""
        return normalize_identity(identity) in self._markers

    def since(
        self,
        identity: str,
        entries: Iterable[ActivityEntry],
        *,
        limit: int | None = None,
    ) -> SinceLastVisit:
        """Return the activity new since an identity's last visit."""
        key = normalize_identity(identity)
        return since_last_visit(entries, self._markers.get(key), identity=key, limit=limit)

    def forget(self, identity: str) -> bool:
        """Drop a marker, returning whether it existed."""
        return self._markers.pop(normalize_identity(identity), None) is not None

    def identities(self) -> tuple[str, ...]:
        """Return all tracked identities in stable order."""
        return tuple(sorted(self._markers))

    def seed(self, markers: Iterable[VisitMarker]) -> None:
        """Import pre-existing markers."""
        for marker in markers:
            self._markers[marker.identity] = marker

    def clear(self) -> None:
        """Drop all markers."""
        self._markers.clear()

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot."""
        return {
            "identities": list(self.identities()),
            "markers": {key: marker.as_dict() for key, marker in sorted(self._markers.items())},
        }
