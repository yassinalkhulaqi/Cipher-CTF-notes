"""Tests for event filtering, combination, and deterministic replay."""

from __future__ import annotations

from redscribe.v3.entities.types import EntityId, EntityKind
from redscribe.v3.events.filters import (
    EventFilter,
    any_of,
    combine,
    count_by_kind,
    latest_per_subject,
    payload_values,
)
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.events.replay import (
    EventReplay,
    append_reducer,
    count_reducer,
)
from redscribe.v3.events.types import DomainEvent, EventRecord, EventSeverity


def _records() -> tuple[EventRecord, ...]:
    subject = EntityId(EntityKind.FINDING, "f-1")
    return (
        EventRecord(
            sequence=1,
            event=DomainEvent(
                kind="finding.created",
                subject=subject,
                actor="alice",
                severity=EventSeverity.INFO,
                payload={"title": "SQLi", "token": "secret"},
            ),
            timestamp=10.0,
        ),
        EventRecord(
            sequence=2,
            event=DomainEvent(
                kind="finding.updated",
                subject=subject,
                actor="bob",
                severity=EventSeverity.WARNING,
                payload={"title": "SQLi confirmed", "stage": "retest"},
            ),
            timestamp=20.0,
        ),
        EventRecord(
            sequence=3,
            event=DomainEvent(
                kind="note.created",
                actor="alice",
                severity=EventSeverity.TRACE,
                payload={"title": "Recon notes"},
            ),
            timestamp=30.0,
        ),
    )


def test_filter_by_kind_actor_and_subject() -> None:
    records = _records()
    assert len(EventFilter(kinds=("finding.created",)).apply(records)) == 1
    assert len(EventFilter(actors=("alice",)).apply(records)) == 2
    assert len(EventFilter(subjects=("finding:f-1",)).apply(records)) == 2
    assert len(EventFilter(exclude_kinds=("note.created",)).apply(records)) == 2


def test_filter_by_severity_and_time() -> None:
    records = _records()
    assert len(EventFilter(minimum_severity=EventSeverity.WARNING).apply(records)) == 1
    assert len(EventFilter(after=10.0).apply(records)) == 2
    assert len(EventFilter(before=30.0).apply(records)) == 2
    assert len(EventFilter(after=10.0, before=30.0).apply(records)) == 1


def test_filter_by_text_and_correlation() -> None:
    records = _records()
    assert len(EventFilter(text="SQLI").apply(records)) == 2
    assert len(EventFilter(text="recon").apply(records)) == 1
    records[0].event.payload["correlation_id"] = "c-1"
    assert len(EventFilter(correlation_id="c-1").apply(records)) == 0


def test_filter_parse() -> None:
    parsed = EventFilter.parse("kind:created actor:alice severity:warning free text")
    assert parsed.kinds == ("created",)
    assert parsed.actors == ("alice",)
    assert parsed.minimum_severity is EventSeverity.WARNING
    assert parsed.text == "free text"
    assert EventFilter.parse("text:hello").text == "hello"


def test_filter_combination() -> None:
    records = _records()
    both = combine(EventFilter(kinds=("finding.created",)), EventFilter(actors=("alice",)))
    assert sum(1 for record in records if both(record)) == 1
    either = any_of(EventFilter(kinds=("note.created",)), EventFilter(actors=("bob",)))
    assert sum(1 for record in records if either(record)) == 2


def test_filter_aggregates() -> None:
    records = _records()
    assert count_by_kind(records) == {"finding.created": 1, "finding.updated": 1, "note.created": 1}
    latest = latest_per_subject(records)
    assert latest["finding:f-1"].sequence == 2
    assert payload_values(records, "title") == ("SQLi", "SQLi confirmed", "Recon notes")
    assert payload_values(records, "missing") == ()


def test_replay_fold() -> None:
    replay = EventReplay(_records())
    result = replay.fold(count_reducer, {})
    assert result.state == {"finding.created": 1, "finding.updated": 1, "note.created": 1}
    assert result.consumed == 3
    assert result.skipped == 0
    assert result.last_sequence == 3
    assert result.as_dict()["consumed"] == 3


def test_replay_filtered_and_append() -> None:
    replay = EventReplay(_records())
    result = replay.fold(
        append_reducer,
        (),
        event_filter=EventFilter(kinds=("finding.created",)),
    )
    assert result.consumed == 1
    assert result.skipped == 2
    assert len(result.state) == 1


def test_replay_collect_with_redaction() -> None:
    replay = EventReplay(_records())
    payloads = replay.collect(redactor=RedactionPolicy())
    assert payloads[0]["payload"]["token"] == "[redacted]"
    filtered = replay.collect(event_filter=EventFilter(kinds=("note.created",)))
    assert len(filtered) == 1


def test_replay_project_and_subjects() -> None:
    replay = EventReplay(_records())
    projection = replay.project("title")
    assert sorted(projection) == ["Recon notes", "SQLi", "SQLi confirmed"]
    assert replay.subjects() == ("finding:f-1",)
    assert replay.count() == 3
    assert replay.count(event_filter=EventFilter(kinds=("note.created",))) == 1
