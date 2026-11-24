"""Tests for since-last-visit tracking and retrospective summaries."""

from __future__ import annotations

import pytest

from redscribe.v3.activity.models import ActivityEntry
from redscribe.v3.activity.projections import ActivityProjector
from redscribe.v3.activity.retrospective import (
    build_retrospective,
    retrospective_headline,
    retrospective_stats,
    streak_lengths,
)
from redscribe.v3.activity.visits import (
    VisitError,
    VisitTracker,
    normalize_identity,
    since_last_visit,
)
from redscribe.v3.clock import FixedClock
from redscribe.v3.events.types import EventRecord
from tests.v3_activity.conftest import BASE_TIME, DAY


def _entries(records: tuple[EventRecord, ...]) -> tuple[ActivityEntry, ...]:
    return ActivityProjector(timezone="UTC").entries(records)


def test_identity_normalization() -> None:
    assert normalize_identity("  alice  ") == "alice"
    assert normalize_identity("a  b") == "a b"
    with pytest.raises(VisitError):
        normalize_identity("")
    with pytest.raises(VisitError):
        normalize_identity("x" * 200)


def test_visit_tracker_lifecycle(clock: FixedClock) -> None:
    tracker = VisitTracker(clock=clock)
    assert tracker.identities() == ()
    marker = tracker.mark("Alice", note=" first look ")
    assert marker.identity == "Alice"
    assert marker.timestamp == BASE_TIME + 5 * DAY
    assert tracker.has("Alice") is True
    assert tracker.get("Alice") == marker
    assert tracker.get("alice") is None
    assert tracker.snapshot()["identities"] == ["Alice"]
    seeded = tracker.mark("bob", timestamp=123.0, sequence=4)
    tracker.forget("Alice")
    tracker.seed([marker])
    assert tracker.has("Alice")
    assert tracker.has("bob")
    assert tracker.get("bob") == seeded
    tracker.clear()
    assert tracker.identities() == ()


def test_visit_tracker_validation(clock: FixedClock) -> None:
    tracker = VisitTracker(clock=clock)
    with pytest.raises(VisitError):
        tracker.mark("")
    with pytest.raises(VisitError):
        tracker.mark("bob", sequence=-1)


def test_since_without_marker_returns_everything(
    records: tuple[EventRecord, ...],
) -> None:
    entries = _entries(records)
    result = since_last_visit(entries, None, identity="new-user")
    assert result.count == 8
    assert result.marker is None
    assert result.by_kind["finding.created"] == 1
    assert result.first_timestamp == entries[0].timestamp
    assert result.last_timestamp == entries[-1].timestamp
    assert len(result.entries) == 8


def test_since_after_marker_uses_sequence_and_timestamp(
    records: tuple[EventRecord, ...], clock: FixedClock
) -> None:
    entries = _entries(records)
    tracker = VisitTracker(clock=clock)
    marker = tracker.mark("alice", timestamp=BASE_TIME + 2 * DAY, sequence=5)
    result = tracker.since("alice", entries)
    assert result.marker == marker
    assert result.count == 3
    assert [entry.sequence for entry in result.entries] == [6, 7, 8]
    assert result.by_severity["critical"] == 1
    assert result.first_timestamp == entries[5].timestamp


def test_since_limit_and_empty_window(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    result = since_last_visit(entries, None, limit=2)
    assert result.count == 8
    assert len(result.entries) == 2
    assert [entry.sequence for entry in result.entries] == [7, 8]
    empty = since_last_visit((), None)
    assert empty.count == 0
    assert empty.first_timestamp is None
    assert empty.last_timestamp is None


def test_streak_lengths() -> None:
    assert streak_lengths([]) == (0, 0)
    assert streak_lengths(["2023-11-01"]) == (1, 1)
    assert streak_lengths(["2023-11-01", "2023-11-02", "2023-11-04"]) == (2, 1)
    assert streak_lengths(["2023-11-01", "2023-11-02", "2023-11-03"]) == (3, 3)
    assert streak_lengths(["2023-11-03", "2023-11-01", "2023-11-02"]) == (3, 3)


def test_retrospective_counts_and_rankings(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    summary = build_retrospective(
        entries,
        start=BASE_TIME,
        end=BASE_TIME + 5 * DAY,
        timezone="UTC",
        top_limit=2,
        highlight_limit=2,
    )
    assert summary.total_events == 8
    assert summary.active_days == 5
    assert summary.active_weeks == 1
    assert summary.longest_streak == 5
    assert summary.trailing_streak == 5
    assert summary.busiest_day is not None
    assert summary.busiest_day.date_key in {entry.date_key for entry in entries}
    assert summary.top_kinds[0][1] >= summary.top_kinds[1][1]
    assert len(summary.top_actors) == 2
    assert summary.severity_mix["critical"] == 1
    assert len(summary.highlights) == 2
    assert len(summary.daily_counts) == 5
    assert summary.iso_start.startswith("2023-11-14")
    payload = summary.as_dict()
    assert payload["top_kinds"][0]["count"] == summary.top_kinds[0][1]
    assert payload["daily_counts"][0]["date_key"] == "2023-11-14"


def test_retrospective_window_is_half_open(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    summary = build_retrospective(
        entries, start=BASE_TIME + DAY, end=BASE_TIME + 3 * DAY, timezone="UTC"
    )
    assert summary.total_events == 3
    assert summary.active_days == 2
    assert summary.daily_counts[0].date_key == "2023-11-15"
    with pytest.raises(ValueError):
        build_retrospective(entries, start=BASE_TIME, end=BASE_TIME, timezone="UTC")


def test_retrospective_presentation_helpers(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    summary = build_retrospective(entries, start=BASE_TIME, end=BASE_TIME + 5 * DAY, timezone="UTC")
    headline = retrospective_headline(summary)
    assert "8 events" in headline
    assert "5 active days" in headline
    stats = retrospective_stats(summary)
    assert stats["events"] == 8
    assert stats["longest_streak"] == 5
    assert stats["headline"] == headline
