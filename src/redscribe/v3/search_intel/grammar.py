"""Query language v2 grammar definition and value normalization.

The grammar is intentionally small and regular so it can be implemented
identically in the Python backend and the TypeScript query builder:

.. code-block:: text

    query        := or_expr
    or_expr      := and_expr (OR and_expr)*
    and_expr     := clause (clause)*
    clause       := negation? primary
    negation     := "-" | "NOT"
    primary      := term | field_clause | has_clause | group
    term         := WORD | QUOTED
    field_clause := FIELD ":" field_value
    field_value  := WORD | QUOTED
    has_clause   := "has" ":" "link" ( "(" LINK_KIND ")" )?
    group        := "(" or_expr ")"

``AND`` is accepted as an explicit no-op separator. Implicit adjacency means
``AND``. ``OR`` and ``|`` are equivalent and bind less tightly than ``AND``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from redscribe.v3.search_intel.types import (
    FIELD_VOCABULARY,
    LINK_VALUE_KINDS,
    MAX_QUERY_LENGTH,
    QUERY_FIELDS,
    FieldName,
)

_DATE_PATTERN: re.Pattern[str] = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_OPERATOR_WORDS: frozenset[str] = frozenset({"AND", "OR", "NOT"})


def is_operator_word(value: str) -> bool:
    """Return whether a word is a grammar operator keyword."""
    return value.upper() in _OPERATOR_WORDS


def normalize_value(value: str) -> str:
    """Normalize a field or term value for comparison."""
    return " ".join(value.split()).casefold()


def validate_field_value(
    field: str,
    value: str,
) -> tuple[str, float, str, str]:
    """Validate and normalize a field value.

    Returns a tuple of ``(normalized, before_timestamp, link_kind, error_code)``.
    Exactly one of ``link_kind`` or ``before_timestamp`` is populated for the
    fields that use them. A non-empty ``error_code`` means validation failed.
    """
    normalized = normalize_value(value)
    if not normalized:
        return "", 0.0, "", "empty_field_value"
    member = FieldName.parse(field)
    if member is None:
        return normalized, 0.0, "", "unknown_field"
    vocabulary = FIELD_VOCABULARY[member.value]
    if vocabulary and normalized not in vocabulary:
        if member is FieldName.HAS:
            return normalized, 0.0, "", "invalid_field_value"
        return normalized, 0.0, "", "invalid_field_value"
    if member is FieldName.BEFORE:
        timestamp = parse_date_boundary(normalized)
        if timestamp is None:
            return normalized, 0.0, "", "invalid_field_value"
        return normalized, timestamp, "", ""
    return normalized, 0.0, "", ""


def validate_link_kind(value: str) -> str:
    """Return a normalized link kind or an empty string when invalid."""
    normalized = normalize_value(value)
    return normalized if normalized in LINK_VALUE_KINDS else ""


def parse_date_boundary(value: str) -> float | None:
    """Parse a ``YYYY-MM-DD`` date into a UTC timestamp."""
    match = _DATE_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        moment = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
    return moment.timestamp()


def field_hint(value: str) -> str:
    """Return a short suggestion for a misspelled field name."""
    normalized = normalize_value(value)
    if not normalized:
        return f"Use one of: {', '.join(QUERY_FIELDS)}"
    from difflib import get_close_matches

    matches = get_close_matches(normalized, QUERY_FIELDS, n=1, cutoff=0.6)
    if matches:
        return f"Did you mean '{matches[0]}:'?"
    return f"Use one of: {', '.join(QUERY_FIELDS)}"


def grammar_summary() -> dict[str, object]:
    """Return a machine-readable description of the v2 grammar."""
    return {
        "version": 2,
        "fields": list(QUERY_FIELDS),
        "field_values": {name: list(values) for name, values in FIELD_VOCABULARY.items()},
        "operators": ["AND", "OR", "|", "NOT", "-"],
        "grouping": ["(", ")"],
        "max_length": MAX_QUERY_LENGTH,
    }
