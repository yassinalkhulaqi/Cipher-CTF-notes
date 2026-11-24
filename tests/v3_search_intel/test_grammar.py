"""Grammar validation and normalization helpers."""

from __future__ import annotations

import pytest

from redscribe.v3.search_intel.grammar import (
    field_hint,
    grammar_summary,
    normalize_value,
    parse_date_boundary,
    validate_field_value,
    validate_link_kind,
)
from redscribe.v3.search_intel.types import FieldName


def test_field_names_parse_case_insensitively() -> None:
    assert FieldName.parse("KIND") is FieldName.KIND
    assert FieldName.parse(" has ") is FieldName.HAS
    assert FieldName.parse("bogus") is None


def test_normalize_value_collapses_whitespace_and_case() -> None:
    assert normalize_value("  High   PRIORITY ") == "high priority"
    assert normalize_value("") == ""


def test_validate_known_field_values() -> None:
    value, before, link, error = validate_field_value("kind", "FINDING")
    assert (value, before, link, error) == ("finding", 0.0, "", "")


def test_validate_rejects_unknown_kind() -> None:
    value, _before, _link, error = validate_field_value("kind", "widget")
    assert value == "widget"
    assert error == "invalid_field_value"


def test_validate_status_and_severity() -> None:
    assert validate_field_value("status", "active")[3] == ""
    assert validate_field_value("severity", "critical")[3] == ""
    assert validate_field_value("status", "pending")[3] == "invalid_field_value"


def test_validate_date_boundary() -> None:
    value, before, _link, error = validate_field_value("before", "2024-02-29")
    assert value == "2024-02-29"
    assert error == ""
    assert before == pytest.approx(parse_date_boundary("2024-02-29") or 0.0)
    assert parse_date_boundary("2023-02-29") is None
    assert parse_date_boundary("not-a-date") is None
    assert validate_field_value("before", "2024-13-01")[3] == "invalid_field_value"


def test_validate_empty_value() -> None:
    assert validate_field_value("tag", "   ")[3] == "empty_field_value"


def test_validate_link_kinds() -> None:
    assert validate_link_kind("Evidences") == "evidences"
    assert validate_link_kind("unknown") == ""


def test_field_hint_suggests_close_match() -> None:
    assert "kind" in field_hint("knd")
    assert "one of" in field_hint("")


def test_grammar_summary_is_machine_readable() -> None:
    summary = grammar_summary()
    assert summary["version"] == 2
    assert "kind" in summary["fields"]
    assert summary["max_length"] == 500
