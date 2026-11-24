"""Tests for the activity service facade and replay idempotency."""

from __future__ import annotations

import pytest

from redscribe.v3.activity.filters import ActivityFilter
from redscribe.v3.activity.service import ActivityService, ActivityServiceError
from redscribe.v3.clock import FixedClock
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.types import EventRecord, EventSeverity
from tests.v3_activity.conftest import BASE_TIME, DAY, make_record


def test_service_ingestion_is_replay_idempotent(
    clock: FixedClock, records: tuple[EventRecord, ...]
) -> None:
    service = ActivityService(clock=clock, timezone="UTC")
    assert service.ingest_all(records) == 8
    assert service.ingest_all(tuple(reversed(records))) == 0
    assert service.ingest(records[0]).sequence == 1
    assert len(service.entries()) == 8
    assert [entry.sequence for entry in service.entries()] == list(range(1, 9))
    assert service.entry(99) is None
    assert service.jump_to(1) is not None
    assert service.jump_to(99) is None


def test_bus_subscription_projects_new_events(
    clock: FixedClock, records: tuple[EventRecord, ...]
) -> None:
    bus = EventBus(clock=clock)
    service = ActivityService(bus=bus, clock=clock, timezone="UTC")
    service.install_subscriber()
    for record in records:
        bus.publish(record.event, request_id=record.request_id)
    assert service.sync_from_bus() == 0
    assert len(service.entries()) == 8
    bus.publish(make_record(9, "finding.created", timestamp=BASE_TIME + 6 * DAY).event)
    assert len(service.entries()) == 9
    assert service.bus is bus


def test_stream_ordering_pagination_and_density(
    service: ActivityService,
) -> None:
    result = service.stream()
    assert result.total == 8
    assert result.page is not None
    assert result.page.total == 8
    assert [entry.sequence for entry in result.entries] == [8, 7, 6, 5, 4, 3, 2, 1]
    assert len(result.groups) == 5
    assert result.facets.kinds["finding.created"] == 1
    first_page = service.stream(size=3)
    assert [entry.sequence for entry in first_page.entries] == [8, 7, 6]
    assert first_page.page is not None
    assert first_page.page.has_next is True
    second_page = service.stream(offset=3, size=3)
    assert [entry.sequence for entry in second_page.entries] == [5, 4, 3]
    compact = service.stream(size=1, density="compact")
    assert "payload" not in compact.as_dict()["entries"][0]
    assert compact.density == "compact"


def test_stream_filter_and_warnings(service: ActivityService) -> None:
    filtered = service.stream(
        ActivityFilter(kinds=("finding.created",)), query="kind:finding.created"
    )
    assert filtered.total == 1
    assert filtered.entries[0].sequence == 1
    assert filtered.query == "kind:finding.created"
    warned = service.stream(warnings=("stale",))
    assert warned.warnings == ("stale",)


def test_digest_retrospective_and_since(service: ActivityService) -> None:
    daily = service.digest("daily", generated_at=42.0)
    assert daily.generated_at == 42.0
    assert len(daily.digests) == 5
    weekly = service.digest(period="weekly", generated_at=42.0)
    assert len(weekly.digests) == 1
    anchor = service.digest_at(BASE_TIME + DAY, period="daily", generated_at=42.0)
    assert anchor is not None
    assert anchor.key == "2023-11-15"
    summary = service.retrospective(start=BASE_TIME, end=BASE_TIME + 5 * DAY, top_limit=3)
    assert summary.total_events == 8
    assert summary.active_days == 5
    since = service.since("alice")
    assert since.count == 8
    marker = service.mark_visit("alice", note="caught up")
    assert marker.identity == "alice"
    assert marker.sequence == 8
    assert service.since("alice").count == 0


def test_metadata_validation_redaction_and_stats(service: ActivityService) -> None:
    metadata = service.filters()
    assert len(metadata["keys"]) >= 8
    assert metadata["operators"] == ["include", "exclude"]
    assert service.validate("kind:finding.created").valid is True
    assert service.validate("unknown:x").valid is False
    cleaned = service.redact({"token": "abc", "title": "ok"})
    assert cleaned == {"token": "[redacted]", "title": "ok"}
    assert service.redaction_report({"secret": "v"})["applied"] is True
    assert service.last_redaction_report()["applied"] is True
    stats = service.stats()
    assert stats["entries"] == 8
    assert stats["timezone"] == "UTC"
    assert stats["kinds"]["finding.updated"] == 1
    assert stats["redactions"]["redacted_keys"]
    assert service.as_dict()["entries"][0]["sequence"] == 1
    assert len(service.active_day_keys()) == 5


def test_service_validation_and_reset(service: ActivityService) -> None:
    with pytest.raises(ActivityServiceError):
        service.digest("monthly")
    with pytest.raises(ActivityServiceError):
        service.retrospective(start=10.0, end=10.0)
    service.reset()
    assert service.entries() == ()
    assert service.stats()["entries"] == 0
    assert service.since("alice").count == 0


def test_service_exposes_severity_rank_in_entries(service: ActivityService) -> None:
    entry = service.entry(6)
    assert entry is not None
    assert entry.severity == EventSeverity.CRITICAL.value
    assert entry.severity_rank == 4
