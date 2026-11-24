"""Tests for event-to-activity projections and date grouping."""

from __future__ import annotations

from redscribe.v3.activity.models import DENSITY_COMPACT, DENSITY_DETAILED
from redscribe.v3.activity.projections import (
    ActivityProjector,
    event_summary,
    event_title,
    payload_tags,
)
from redscribe.v3.activity.timezone import day_key, week_key
from redscribe.v3.events.types import EventRecord


def test_event_title_and_summary_helpers(records: tuple[EventRecord, ...]) -> None:
    assert event_title("finding.created") == "Finding Created"
    assert event_title("evidence.added") == "Evidence Added"
    assert event_title("report_generated") == "Report Generated"
    assert event_summary({"title": " A  finding "}) == "A finding"
    assert event_summary({"message": "hello"}) == "hello"
    assert event_summary({"count": 4}) == ""
    assert payload_tags({"tags": [" Web ", "#RECON", "web"]}) == ("web", "recon")
    assert payload_tags({"tags": "web"}) == ()


def test_projection_builds_linkable_redacted_entries(
    records: tuple[EventRecord, ...],
) -> None:
    projector = ActivityProjector(timezone="UTC")
    entries = projector.entries(records)
    assert len(entries) == 8
    first = entries[0]
    assert first.sequence == 1
    assert first.title == "Finding Created"
    assert first.summary == "SQL injection"
    assert first.actor == "alice"
    assert first.severity == "info"
    assert first.subject_ref == "finding:f-1"
    assert first.jump is not None
    assert first.jump.kind == "finding"
    assert first.jump.route == "/resolve/finding/f-1"
    assert first.payload["token"] == "[redacted]"
    assert first.redactions == ("token",)
    assert first.tags == ("web", "sqli")
    assert first.has_redactions is True
    assert first.is_linkable is True


def test_projection_without_subject_is_not_linkable() -> None:
    from tests.v3_activity.conftest import make_record

    projector = ActivityProjector(timezone="UTC")
    entry = projector.entry(make_record(1, "system.start", subject=""))
    assert entry.jump is None
    assert entry.is_linkable is False
    assert entry.subject_ref == ""


def test_projection_timezone_keys_and_iso(records: tuple[EventRecord, ...]) -> None:
    projector = ActivityProjector(timezone="UTC")
    entries = projector.entries(records)
    assert entries[0].date_key == "2023-11-14"
    assert entries[0].week_key == "2023-W46"
    assert entries[0].iso_timestamp.endswith("Z")
    assert day_key(records[0].timestamp, projector._zone) == entries[0].date_key
    assert week_key(records[0].timestamp, projector._zone) == entries[0].week_key
    assert projector.local_iso(records[0].timestamp).startswith("2023-11-14")


def test_grouping_orders_buckets_newest_first(records: tuple[EventRecord, ...]) -> None:
    projector = ActivityProjector(timezone="UTC")
    entries = projector.entries(records)
    groups = projector.group(entries)
    assert len(groups) == 5
    assert groups[0].key > groups[-1].key
    assert groups[0].count == 1
    assert [entry.sequence for entry in groups[0].entries] == [8]
    weekly = projector.group(entries, period="weekly")
    assert len(weekly) == 1
    assert weekly[0].key == "2023-W46"
    assert weekly[0].count == 8


def test_facets_and_stream_result(records: tuple[EventRecord, ...]) -> None:
    projector = ActivityProjector(timezone="UTC", density=DENSITY_DETAILED)
    entries = projector.entries(records)
    facets = projector.facets(entries)
    assert facets.kinds["finding.created"] == 1
    assert facets.actors["bob"] == 2
    assert facets.severities["critical"] == 1
    assert facets.subjects["finding:f-1"] == 3
    result = projector.stream(entries, total=len(entries), query="finding")
    payload = result.as_dict()
    assert payload["total"] == 8
    assert payload["query"] == "finding"
    assert payload["density"] == DENSITY_DETAILED
    assert payload["facets"]["kinds"]["finding.updated"] == 1
    compact = entries[0].as_dict(density=DENSITY_COMPACT)
    assert "payload" not in compact
    assert "request_id" not in compact
