"""Tests for deterministic, timezone-safe digest aggregation."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone

import pytest

from redscribe.v3.activity.digest import (
    DigestBuilder,
    build_digests,
    digest_label,
    digest_summary,
    find_digest,
)
from redscribe.v3.activity.models import ActivityEntry
from redscribe.v3.activity.projections import ActivityProjector
from redscribe.v3.activity.timezone import (
    TimezoneError,
    bucket_key,
    period_bounds,
    resolve_timezone,
    window_keys,
)
from redscribe.v3.events.types import EventRecord
from tests.v3_activity.conftest import BASE_TIME, DAY


def _entries(records: tuple[EventRecord, ...]) -> tuple[ActivityEntry, ...]:
    return ActivityProjector(timezone="UTC").entries(records)


def test_daily_digest_boundaries_are_deterministic(
    records: tuple[EventRecord, ...],
) -> None:
    entries = _entries(records)
    first = build_digests(entries, period="daily", timezone="UTC", generated_at=999.0)
    second = DigestBuilder(timezone="UTC").build(entries, period="daily", generated_at=999.0)
    assert first.as_dict() == second.as_dict()
    assert first.period == "daily"
    assert first.generated_at == 999.0
    assert len(first.digests) == 5
    assert first.digests[-1].key == "2023-11-14"
    assert first.digests[0].key == "2023-11-18"
    assert first.total_events == 8
    assert sum(digest.entry_count for digest in first.digests) == 8
    assert first.digests[-1].start < first.digests[-1].end
    assert first.digests[0].iso_start.startswith("2023-11-18")


def test_digest_highlights_and_sections(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    collection = build_digests(
        entries, period="daily", timezone="UTC", generated_at=1.0, highlight_limit=2
    )
    day_one = collection.digests[-1]
    assert day_one.counts == {"finding.created": 1, "note.created": 1}
    assert day_one.actor_counts == {"alice": 1, "bob": 1}
    assert len(day_one.sections) == 2
    assert len(day_one.highlights) == 2
    assert day_one.highlights[0].severity_rank >= day_one.highlights[1].severity_rank
    rendered = day_one.as_dict()
    assert rendered["sections"][0]["entries"][0]["sequence"] in (1, 2)
    assert digest_summary(day_one)["count"] == 2


def test_weekly_digest_buckets(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    collection = build_digests(entries, period="weekly", timezone="UTC", generated_at=1.0)
    assert len(collection.digests) == 1
    weekly = collection.digests[0]
    assert weekly.key == "2023-W46"
    assert weekly.label == "Week of 2023-11-13"
    assert weekly.entry_count == 8
    assert weekly.end - weekly.start == 7 * DAY


def test_digest_at_anchor_and_lookup(records: tuple[EventRecord, ...]) -> None:
    entries = _entries(records)
    builder = DigestBuilder(timezone="UTC")
    found = builder.for_anchor(entries, period="daily", anchor=BASE_TIME + DAY, generated_at=5.0)
    assert found is not None
    assert found.key == "2023-11-15"
    missing = builder.for_anchor(
        entries, period="daily", anchor=BASE_TIME - 10 * DAY, generated_at=5.0
    )
    assert missing is None
    collection = builder.build(entries, period="daily", generated_at=5.0)
    assert find_digest(collection, "2023-11-15") is not None
    assert find_digest(collection, "1999-01-01") is None


def test_timezone_shifts_bucket_keys(records: tuple[EventRecord, ...]) -> None:
    utc = ActivityProjector(timezone="UTC")
    tokyo = ActivityProjector(timezone="Asia/Tokyo")
    assert utc.entries(records)[0].date_key == "2023-11-14"
    assert tokyo.entries(records)[0].date_key == "2023-11-15"
    assert bucket_key(BASE_TIME, "weekly", resolve_timezone("Asia/Tokyo")) == "2023-W46"


def test_dst_day_is_twenty_five_hours() -> None:
    zone = resolve_timezone("America/New_York")
    moment = datetime(2023, 11, 5, 6, 30, tzinfo=dt_timezone.utc).timestamp()
    start, end, key, label = period_bounds(moment, "daily", zone)
    assert key == "2023-11-05"
    assert label == "2023-11-05"
    assert end - start == 25 * 3600
    spring = datetime(2023, 3, 12, 7, 30, tzinfo=dt_timezone.utc).timestamp()
    start, end, _, _ = period_bounds(spring, "daily", zone)
    assert end - start == 23 * 3600


def test_timezone_validation_and_window_keys() -> None:
    assert resolve_timezone("UTC") is dt_timezone.utc
    assert resolve_timezone("") is dt_timezone.utc
    assert window_keys(BASE_TIME, BASE_TIME + 4 * DAY, "daily", resolve_timezone("UTC")) == (
        "2023-11-14",
        "2023-11-15",
        "2023-11-16",
        "2023-11-17",
        "2023-11-18",
    )
    assert window_keys(BASE_TIME, BASE_TIME + 4 * DAY, "weekly", resolve_timezone("UTC")) == (
        "2023-W46",
    )
    assert digest_label(BASE_TIME, "daily", "UTC") == "2023-11-14"
    with pytest.raises(TimezoneError, match="Unknown timezone"):
        resolve_timezone("Mars/Olympus")
