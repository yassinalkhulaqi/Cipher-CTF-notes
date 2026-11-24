"""Typed domain events and durable event records for RedScribe V3."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.entities.types import EntityId


class EventSeverity(str, Enum):
    """Severity used for activity filtering and digest emphasis."""

    TRACE = "trace"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Numeric order for threshold comparisons."""
        return {
            EventSeverity.TRACE: 0,
            EventSeverity.INFO: 1,
            EventSeverity.NOTICE: 2,
            EventSeverity.WARNING: 3,
            EventSeverity.CRITICAL: 4,
        }[self]


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """An immutable event emitted by a V3 feature."""

    kind: str
    subject: EntityId | None = None
    actor: str = "local"
    severity: EventSeverity = EventSeverity.INFO
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.kind or len(self.kind) > 120:
            raise ValueError("Event kind must be 1-120 characters")
        if not self.actor or len(self.actor) > 120:
            raise ValueError("Event actor must be 1-120 characters")

    @property
    def subject_ref(self) -> str:
        """Canonical subject reference or an empty string."""
        return str(self.subject) if self.subject is not None else ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "kind": self.kind,
            "subject": self.subject_ref,
            "actor": self.actor,
            "severity": self.severity.value,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True)
class EventRecord:
    """A persisted event with sequence metadata."""

    sequence: int
    event: DomainEvent
    timestamp: float
    request_id: str = ""

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("Event sequence must be positive")

    @property
    def kind(self) -> str:
        """Event kind shortcut."""
        return self.event.kind

    @property
    def subject_ref(self) -> str:
        """Subject shortcut."""
        return self.event.subject_ref

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload = self.event.as_dict()
        payload.update(
            {"sequence": self.sequence, "timestamp": self.timestamp, "request_id": self.request_id}
        )
        return payload


def make_event(
    kind: str,
    subject: EntityId | None = None,
    **payload: Any,
) -> DomainEvent:
    """Build an event with keyword payload data."""
    return DomainEvent(kind=kind, subject=subject, payload=dict(payload))
