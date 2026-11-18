from __future__ import annotations

import pytest

from redscribe.v2.engagements.util import (
    clamp,
    dedupe,
    digest,
    format_number,
    mapping_get,
    now_iso,
    parse_bool,
    set_clock,
    slugify,
    tokens,
    truncate,
)


@pytest.fixture(autouse=True)
def reset_clock():
    set_clock(None)
    yield
    set_clock(None)


def test_now_iso_returns_utc_timestamp_without_microseconds() -> None:
    value = now_iso()
    assert value.endswith("Z")
    assert "." not in value
    assert len(value) == 20


def test_set_clock_pins_and_releases_timestamps() -> None:
    set_clock("2026-01-02T03:04:05Z")
    assert now_iso() == "2026-01-02T03:04:05Z"
    set_clock(None)
    assert now_iso() != "2026-01-02T03:04:05Z"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Q1 2026 Audit", "q1-2026-audit"),
        ("  spaces   here ", "spaces-here"),
        ("--punctuation--", "punctuation"),
        ("###", "item"),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected
    assert slugify(value, fallback="fallback") in {expected, "fallback"}


def test_slugify_respects_custom_fallback() -> None:
    assert slugify("!!!", fallback="unnamed") == "unnamed"


def test_tokens_extract_lowercase_alphanumeric_words() -> None:
    assert tokens("SQL injection / CWE-89!") == ("sql", "injection", "cwe", "89")
    assert tokens("") == ()
    assert tokens("___") == ()


def test_dedupe_preserves_first_occurrence_and_optional_case_sensitivity() -> None:
    assert dedupe(["Web", "web", "API", "api"]) == ["Web", "API"]
    assert dedupe(["Web", "web", "API"], casefold=False) == ["Web", "web", "API"]
    assert dedupe([]) == []


def test_clamp_enforces_inclusive_bounds() -> None:
    assert clamp(-1.0) == 0.0
    assert clamp(0.5) == 0.5
    assert clamp(2.0) == 1.0
    assert clamp(15.0, 10.0, 20.0) == 15.0
    assert clamp(25.0, 10.0, 20.0) == 20.0


def test_digest_is_stable_short_and_input_sensitive() -> None:
    first = digest("title|summary")
    assert first == digest("title|summary")
    assert first != digest("summary|title")
    assert len(first) == 16
    assert all(char in "0123456789abcdef" for char in first)


def test_mapping_get_handles_missing_keys() -> None:
    data = {"present": 1, "none": None}
    assert mapping_get(data, "present", 9) == 1
    assert mapping_get(data, "none", 9) is None
    assert mapping_get(data, "missing", 9) == 9


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (1.0, 1, "1"),
        (1.25, 1, "1.2"),
        (1.234, 2, "1.23"),
        (0.0, 3, "0"),
    ],
)
def test_format_number(value: float, digits: int, expected: str) -> None:
    assert format_number(value, digits=digits) == expected


def test_truncate_preserves_short_values_and_suffixes_long_values() -> None:
    assert truncate("short", limit=10) == "short"
    assert truncate("abcdefghij", limit=5) == "ab..."
    assert truncate("abcdefghij", limit=3, suffix="...") == "abc"
    assert truncate("abcdefghij", limit=12) == "abcdefghij"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        (True, True),
        (False, False),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("1", True),
        ("false", False),
        ("NO", False),
        ("off", False),
        ("0", False),
        ("maybe", False),
    ],
)
def test_parse_bool(value: str | bool | None, expected: bool) -> None:
    assert parse_bool(value) is expected
    assert parse_bool(value, default=not expected) is (
        expected if value not in (None, "maybe") else not expected
    )
