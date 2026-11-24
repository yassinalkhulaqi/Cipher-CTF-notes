"""Tests for the activity filter DSL."""

from __future__ import annotations

from redscribe.v3.activity.filters import (
    ActivityFilter,
    any_filter,
    combine_filters,
    filter_definitions,
    make_filter_chips,
    parse_query,
    validate_query,
)
from redscribe.v3.activity.models import FILTER_EXCLUDE, ActivityEntry
from redscribe.v3.activity.projections import ActivityProjector
from redscribe.v3.events.filters import EventFilter
from redscribe.v3.events.types import EventRecord, EventSeverity


def _entries(records: tuple[EventRecord, ...]) -> tuple[ActivityEntry, ...]:
    return ActivityProjector(timezone="UTC").entries(records)


def test_parse_simple_queries() -> None:
    parsed = ActivityFilter.parse("kind:finding.created actor:alice severity:warning")
    assert parsed.kinds == ("finding.created",)
    assert parsed.actors == ("alice",)
    assert parsed.minimum_severity == "warning"
    assert parsed.is_empty is False
    assert ActivityFilter.parse("").is_empty is True


def test_parse_exclusions_and_free_text() -> None:
    parsed = ActivityFilter.parse('-kind:note.created -actor:bob "search term"')
    assert parsed.exclude_kinds == ("note.created",)
    assert parsed.exclude_actors == ("bob",)
    assert parsed.text == "search term"
    chips = validate_query("-kind:note.created").tokens
    assert chips[0].operator == FILTER_EXCLUDE
    assert chips[0].token == "-kind:note.created"


def test_parse_time_and_correlation_filters() -> None:
    parsed = ActivityFilter.parse(
        "since:2023-11-14T00:00:00Z until:2023-11-18T00:00:00Z correlation:batch-1"
    )
    assert parsed.since is not None
    assert parsed.since > 0
    assert parsed.until is not None
    assert parsed.until > parsed.since
    assert parsed.correlation_id == "batch-1"
    assert ActivityFilter.parse("since:123.5").since == 123.5


def test_validation_reports_bad_tokens() -> None:
    valid = validate_query("kind:finding.created severity:warning")
    assert valid.valid is True
    assert valid.normalized == "kind:finding.created severity:warning"
    invalid = validate_query("bogus:value severity:nope since:not-a-time")
    assert invalid.valid is False
    assert len(invalid.errors) == 3
    assert any("Unsupported filter key" in error for error in invalid.errors)
    assert any("Unknown severity" in error for error in invalid.errors)
    assert any("Invalid timestamp" in error for error in invalid.errors)


def test_filter_matches_kinds_actors_subjects(
    records: tuple[EventRecord, ...],
) -> None:
    entries = _entries(records)
    assert len(ActivityFilter(kinds=("finding.created",)).apply(entries)) == 1
    assert len(ActivityFilter(exclude_kinds=("note.created", "note.updated")).apply(entries)) == 6
    assert len(ActivityFilter(actors=("bob",)).apply(entries)) == 2
    assert len(ActivityFilter(exclude_actors=("bob",)).apply(entries)) == 6
    assert len(ActivityFilter(subjects=("finding:f-1",)).apply(entries)) == 3


def test_filter_matches_severity_text_and_time(
    records: tuple[EventRecord, ...],
) -> None:
    entries = _entries(records)
    assert len(ActivityFilter(minimum_severity="warning").apply(entries)) == 2
    assert len(ActivityFilter(severities=("info",)).apply(entries)) == 3
    assert len(ActivityFilter(text="SQLI").apply(entries)) == 3
    assert len(ActivityFilter(text="proof").apply(entries)) == 1
    assert len(ActivityFilter(tags=("sqli",)).apply(entries)) == 1
    assert len(ActivityFilter(since=entries[0].timestamp).apply(entries)) == 7
    assert len(ActivityFilter(until=entries[0].timestamp).apply(entries)) == 0


def test_filter_lowers_to_b00_event_filter() -> None:
    event_filter = ActivityFilter(
        kinds=("finding.created",),
        exclude_kinds=("note.created",),
        actors=("alice",),
        subjects=("finding:f-1",),
        minimum_severity="warning",
        since=1.0,
        until=2.0,
        text="sql",
    ).to_event_filter()
    assert isinstance(event_filter, EventFilter)
    assert event_filter.kinds == ("finding.created",)
    assert event_filter.exclude_kinds == ("note.created",)
    assert event_filter.minimum_severity is EventSeverity.WARNING
    assert event_filter.after == 1.0
    assert event_filter.before == 2.0


def test_filter_combinators(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    both = combine_filters(
        ActivityFilter(actors=("alice",)),
        ActivityFilter(minimum_severity="warning"),
    )
    assert sum(1 for entry in entries if both(entry)) == 1
    either = any_filter(
        ActivityFilter(kinds=("note.created",)),
        ActivityFilter(actors=("carol",)),
    )
    assert sum(1 for entry in entries if either(entry)) == 2


def test_chip_round_trip_and_definitions() -> None:
    event_filter = ActivityFilter.parse("kind:finding.created actor:alice")
    chips = make_filter_chips(event_filter)
    assert {chip.key for chip in chips} == {"kind", "actor"}
    rebuilt = ActivityFilter.from_chips(chips)
    assert rebuilt.kinds == ("finding.created",)
    assert rebuilt.actors == ("alice",)
    definitions = filter_definitions()
    assert {definition.key for definition in definitions} >= {
        "kind",
        "actor",
        "severity",
        "text",
    }
    severity = next(item for item in definitions if item.key == "severity")
    assert "critical" in severity.choices
    rendered = event_filter.as_dict()
    assert rendered["kinds"] == ["finding.created"]
    assert rendered["is_empty"] is False


def test_parse_query_returns_errors(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    event_filter, _chips, errors = parse_query("kind:finding.created")
    assert errors == ()
    assert len(event_filter.apply(entries)) == 1
    _bad, _chips, errors = parse_query("unknown:value")
    assert len(errors) == 1
