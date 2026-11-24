"""Test fixtures for V3 activity tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from redscribe.v3.activity.service import ActivityService
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityId
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.types import DomainEvent, EventRecord, EventSeverity

BASE_TIME = 1_700_000_000.0
DAY = 86_400.0

RecordFactory = Callable[..., EventRecord]


def make_record(
    sequence: int,
    kind: str,
    *,
    actor: str = "alice",
    subject: str = "finding:f-1",
    severity: EventSeverity = EventSeverity.INFO,
    payload: dict[str, Any] | None = None,
    timestamp: float = BASE_TIME,
    request_id: str = "",
    correlation_id: str = "",
) -> EventRecord:
    """Build a deterministic event record for tests."""
    parsed_subject = EntityId.parse(subject) if subject else None
    event = DomainEvent(
        kind=kind,
        subject=parsed_subject,
        actor=actor,
        severity=severity,
        payload=dict(payload or {}),
        correlation_id=correlation_id,
    )
    return EventRecord(sequence=sequence, event=event, timestamp=timestamp, request_id=request_id)


@pytest.fixture
def clock() -> FixedClock:
    """Deterministic clock anchored at the end of the sample window."""
    return FixedClock(start=BASE_TIME + 5 * DAY)


@pytest.fixture
def records() -> tuple[EventRecord, ...]:
    """A small, deterministic event history spanning five days."""
    return (
        make_record(
            1,
            "finding.created",
            payload={"title": "SQL injection", "tags": ["web", "sqli"], "token": "s3cr3t"},
        ),
        make_record(
            2,
            "note.created",
            actor="bob",
            subject="note:n-1",
            severity=EventSeverity.TRACE,
            timestamp=BASE_TIME + 1800,
            payload={"title": "Recon notes", "body": "contact me@example.com"},
        ),
        make_record(
            3,
            "finding.updated",
            timestamp=BASE_TIME + DAY,
            severity=EventSeverity.WARNING,
            payload={"title": "SQLi confirmed", "stage": "retest"},
        ),
        make_record(
            4,
            "evidence.added",
            actor="carol",
            subject="evidence:e-1",
            severity=EventSeverity.NOTICE,
            timestamp=BASE_TIME + DAY + 1200,
            payload={"filename": "proof.png", "api_key": "do-not-leak"},
        ),
        make_record(
            5,
            "report.generated",
            timestamp=BASE_TIME + 2 * DAY,
            subject="report:r-1",
            payload={"title": "Weekly report", "count": 4},
        ),
        make_record(
            6,
            "finding.closed",
            actor="dave",
            timestamp=BASE_TIME + 3 * DAY,
            severity=EventSeverity.CRITICAL,
            payload={"title": "SQLi remediated", "status": "closed"},
        ),
        make_record(
            7,
            "note.updated",
            actor="bob",
            subject="note:n-1",
            timestamp=BASE_TIME + 3 * DAY + 60,
            payload={"title": "Recon notes", "stage": "edited"},
        ),
        make_record(
            8,
            "playbook.started",
            timestamp=BASE_TIME + 4 * DAY,
            severity=EventSeverity.NOTICE,
            subject="run:run-1",
            payload={"title": "Web assessment", "correlation": "batch-1"},
        ),
    )


@pytest.fixture
def bus(clock: FixedClock, records: tuple[EventRecord, ...]) -> EventBus:
    """Event bus preloaded with the sample history."""
    instance = EventBus(clock=clock)
    for record in records:
        instance.publish(record.event, request_id=record.request_id)
    return instance


@pytest.fixture
def service(clock: FixedClock, records: tuple[EventRecord, ...]) -> ActivityService:
    """Activity service preloaded with the sample history."""
    instance = ActivityService(clock=clock, timezone="UTC", highlight_limit=3)
    instance.ingest_all(records)
    return instance


@pytest.fixture
def record_factory() -> RecordFactory:
    """Expose the record builder as a fixture."""
    return make_record
