from __future__ import annotations

from datetime import datetime, timedelta, timezone

from redscribe.domain.utils import (
    collapse_whitespace,
    format_duration,
    format_number,
    humanize_delta,
    iso_z,
    parse_timestamp,
    pluralize,
    relative_time,
    safe_filename,
    slug_hash,
    slugify,
    truncate,
    unique_slug,
    utc_now,
    word_count,
)


def test_utc_now_is_parseable() -> None:
    parsed = parse_timestamp(utc_now())
    assert parsed is not None
    assert parsed.tzinfo is not None


def test_parse_timestamp_accepts_naive_values() -> None:
    parsed = parse_timestamp("2026-10-21T12:30:00")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_parse_timestamp_accepts_z_suffix() -> None:
    parsed = parse_timestamp("2026-10-21T12:30:00Z")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 12


def test_parse_timestamp_rejects_garbage() -> None:
    assert parse_timestamp("not-a-date") is None
    assert parse_timestamp("") is None
    assert parse_timestamp("   ") is None


def test_humanize_delta_long_form() -> None:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    assert humanize_delta((now - timedelta(hours=2)).isoformat(), now=now, long=True) == (
        "2 hours ago"
    )
    assert humanize_delta((now - timedelta(days=1)).isoformat(), now=now, long=True) == (
        "1 day ago"
    )
    assert humanize_delta((now - timedelta(seconds=50)).isoformat(), now=now) == "just now"


def test_humanize_delta_scales() -> None:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    assert humanize_delta((now - timedelta(seconds=10)).isoformat(), now=now) == "just now"
    assert humanize_delta((now - timedelta(minutes=3)).isoformat(), now=now) == "3m ago"
    assert humanize_delta((now - timedelta(hours=5)).isoformat(), now=now) == "5h ago"
    assert humanize_delta((now - timedelta(days=2)).isoformat(), now=now) == "2d ago"
    assert humanize_delta((now - timedelta(days=15)).isoformat(), now=now) == "2w ago"
    assert humanize_delta((now - timedelta(days=90)).isoformat(), now=now) == "3mo ago"
    assert humanize_delta((now - timedelta(days=800)).isoformat(), now=now) == "2y ago"


def test_humanize_delta_handles_invalid_and_future_values() -> None:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    assert humanize_delta("bad", now=now) == ""
    assert humanize_delta((now + timedelta(minutes=3)).isoformat(), now=now) == "just now"


def test_slugify_is_url_safe() -> None:
    assert slugify("HTB — Corporate Box") == "htb-corporate-box"
    assert slugify("Café / CTF") == "cafe-ctf"
    assert slugify("***") == "note"
    assert slugify("a" * 100, max_length=12) == "a" * 12
    assert slugify("!", fallback="folder") == "folder"


def test_safe_filename_removes_reserved_characters() -> None:
    assert safe_filename('a<b>c:d"e/f\\g|h?i*j') == "a-b-c-d-e-f-g-h-i-j"
    assert safe_filename("  .hidden.  ") == "hidden"
    assert safe_filename("", fallback="note-4") == "note-4"
    assert safe_filename("report", extension=".md") == "report.md"
    assert safe_filename("x" * 200).__len__() == 80


def test_word_count_and_truncate() -> None:
    assert word_count("One two three, four.") == 4
    assert word_count("") == 0
    assert truncate("  hello   world  ", 20) == "hello world"
    assert truncate("abcdefghij", 8) == "abcdefg…"
    assert truncate("abcdefghij", 2) == "a…"


def test_collapse_whitespace_and_pluralize() -> None:
    assert collapse_whitespace(" a \n b\tc ") == "a b c"
    assert pluralize(1, "note") == "note"
    assert pluralize(2, "note") == "notes"
    assert pluralize(0, "entry", "entries") == "entries"
    assert format_number(1234567) == "1,234,567"


def test_relative_time_reports_past_and_future() -> None:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    assert relative_time((now - timedelta(minutes=3)).isoformat(), now=now) == "3m ago"
    assert relative_time((now + timedelta(minutes=3)).isoformat(), now=now) == "in 3m"
    assert relative_time((now - timedelta(hours=2)).isoformat(), now=now, long=True) == (
        "2 hours ago"
    )
    assert relative_time((now + timedelta(hours=1)).isoformat(), now=now, long=True) == (
        "in 1 hour"
    )
    assert relative_time((now + timedelta(days=2)).isoformat(), now=now) == "in 2d"
    assert relative_time((now - timedelta(days=400)).isoformat(), now=now, long=True) == (
        "1 year ago"
    )


def test_relative_time_keeps_near_values_and_invalid_input() -> None:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    assert relative_time((now - timedelta(seconds=10)).isoformat(), now=now) == "just now"
    assert relative_time((now + timedelta(seconds=10)).isoformat(), now=now) == "just now"
    assert relative_time("bad", now=now) == ""
    assert relative_time("   ", now=now) == ""


def test_iso_z_normalizes_offsets() -> None:
    moment = datetime(2026, 10, 21, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert iso_z(moment) == "2026-10-21T10:00:00Z"
    assert iso_z(datetime(2026, 10, 21, 12, 0)) == "2026-10-21T12:00:00Z"


def test_format_duration_scales() -> None:
    assert format_duration(2.5) == "2.5ms"
    assert format_duration(25) == "25ms"
    assert format_duration(1500) == "1.50s"
    assert format_duration(90_000) == "1.5m"


def test_unique_slug_avoids_existing_values() -> None:
    assert unique_slug("New Note", []) == "new-note"
    assert unique_slug("New Note", ["new-note"]) == "new-note-2"
    assert unique_slug("New Note", ["new-note", "new-note-2"]) == "new-note-3"
    assert unique_slug("***", ["note"]) == "note-2"
    assert unique_slug("a" * 100, ["a" * 10], max_length=10) == "aaaaaaaa-2"


def test_slug_hash_is_stable_and_bounded() -> None:
    assert slug_hash("fixture") == slug_hash("fixture")
    assert slug_hash("fixture") != slug_hash("other")
    assert len(slug_hash("fixture", length=16)) == 16
    assert slug_hash("fixture", length=100) == slug_hash("fixture", length=64)
    assert slug_hash("fixture", length=0) == slug_hash("fixture", length=1)
