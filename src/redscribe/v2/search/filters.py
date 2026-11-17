"""Structured filters shared by the query parser and ranking engine."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from redscribe.v2.search.models import FacetCount, FilterClause, IndexedDocument, SearchField

FILTER_FIELDS: frozenset[str] = frozenset(
    {
        "tag",
        "tags",
        "status",
        "kind",
        "target",
        "path",
        "title",
        "flag",
        "difficulty",
        "pinned",
        "id",
        "node_id",
        "created",
        "updated",
        "group",
        *(field.value for field in SearchField),
    }
)

FILTER_OPERATORS: frozenset[str] = frozenset({":", "=", "!=", "~", ">", ">=", "<", "<="})

_FILTER_RE = re.compile(
    r"^(?P<negated>-)?(?P<field>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<operator>!=|>=|<=|:|=|~|>|<)(?P<value>.+)$"
)
_TOKEN_RE = re.compile(r'"[^"]*"|\S+')


def parse_filter_token(token: str) -> FilterClause:
    """Parse one ``field:value`` style token into a filter clause."""
    match = _FILTER_RE.fullmatch(token.strip())
    if match is None:
        raise ValueError(f"Invalid filter: {token}")
    value = match.group("value").strip().strip('"')
    clause = FilterClause(
        field=match.group("field").casefold(),
        operator=match.group("operator"),
        value=value,
        negated=bool(match.group("negated")),
    )
    validate_filter_clause(clause)
    return clause


def validate_filter_clause(clause: FilterClause) -> None:
    """Raise a descriptive error when a filter cannot be evaluated."""
    if clause.field not in FILTER_FIELDS:
        raise ValueError(f"Unsupported filter field: {clause.field}")
    if clause.operator not in FILTER_OPERATORS:
        raise ValueError(f"Unsupported filter operator: {clause.operator}")
    if not clause.value:
        raise ValueError(f"Filter value for {clause.field} cannot be empty")


def format_filter(clause: FilterClause) -> str:
    """Serialize a filter clause back into query syntax."""
    value = clause.value
    if any(character.isspace() for character in value):
        value = f'"{value}"'
    return f"{'-' if clause.negated else ''}{clause.field}{clause.operator}{value}"


def extract_filters(text: str) -> tuple[str, tuple[FilterClause, ...]]:
    """Remove filter tokens from a query string and return them separately."""
    remaining: list[str] = []
    clauses: list[FilterClause] = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        try:
            clauses.append(parse_filter_token(token))
        except ValueError:
            remaining.append(token)
    return " ".join(remaining).strip(), tuple(clauses)


def filters_to_query(clauses: Iterable[FilterClause]) -> str:
    """Join filter clauses into a reusable query fragment."""
    return " ".join(format_filter(clause) for clause in clauses)


def filters_from_dict(values: Iterable[Mapping[str, Any]]) -> tuple[FilterClause, ...]:
    """Parse serialized filter objects from an API payload."""
    clauses = tuple(FilterClause.from_dict(value) for value in values)
    for clause in clauses:
        validate_filter_clause(clause)
    return clauses


def _scalar_values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _as_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_datetime(value: Any) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _match_one(value: Any, clause: FilterClause) -> bool:
    actual = _as_text(value)
    expected = clause.value
    if clause.operator in {":", "~"}:
        if "*" in expected or "?" in expected:
            return fnmatch.fnmatchcase(actual.casefold(), expected.casefold())
        return expected.casefold() in actual.casefold()
    if clause.operator in {"=", "!="}:
        return actual.casefold() == expected.casefold()
    left_number = _as_number(value)
    right_number = _as_number(expected)
    if left_number is not None and right_number is not None:
        left: Any = left_number
        right: Any = right_number
    else:
        left_datetime = _as_datetime(value)
        right_datetime = _as_datetime(expected)
        if left_datetime is not None and right_datetime is not None:
            left = left_datetime
            right = right_datetime
        else:
            left = actual.casefold()
            right = expected.casefold()
    if clause.operator == ">":
        return bool(left > right)
    if clause.operator == ">=":
        return bool(left >= right)
    if clause.operator == "<":
        return bool(left < right)
    return bool(left <= right)


def document_value(document: IndexedDocument, field: str) -> Any:
    """Resolve a filter field against a document's fields and metadata."""
    if field in {"tag", "tags"}:
        metadata_tags = _scalar_values(document.metadata.get("tags", ())) or []
        inline_tags = document.field_text("tags").split(",")
        return [value.strip() for value in [*metadata_tags, *inline_tags] if str(value).strip()]
    if field == "title":
        return document.title
    if field in {"id", "node_id"}:
        return document.doc_id
    if field in document.metadata:
        return document.metadata[field]
    field_text = document.field_text(field)
    return field_text if field_text else None


def clause_matches(document: IndexedDocument, clause: FilterClause) -> bool:
    """Evaluate one filter clause against one document."""
    values = _scalar_values(document_value(document, clause.field))
    matched = any(_match_one(value, clause) for value in values)
    if clause.operator == "!=":
        matched = not matched
    return not matched if clause.negated else matched


def apply_filters(
    documents: Iterable[IndexedDocument],
    clauses: Sequence[FilterClause],
) -> list[IndexedDocument]:
    """Return documents satisfying every filter clause."""
    result = list(documents)
    for clause in clauses:
        result = [document for document in result if clause_matches(document, clause)]
    return result


def facet_values(
    documents: Iterable[IndexedDocument],
    field: str,
    *,
    limit: int = 20,
) -> tuple[FacetCount, ...]:
    """Count distinct filter values, ordered by frequency then value."""
    counts: dict[str, int] = {}
    for document in documents:
        distinct: set[str] = set()
        for value in _scalar_values(document_value(document, field)):
            text = _as_text(value).strip()
            if text:
                distinct.add(text)
        for text in distinct:
            counts[text] = counts.get(text, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    return tuple(FacetCount(value, count) for value, count in ordered[: max(0, limit)])


def filter_summary(clauses: Sequence[FilterClause]) -> str:
    """Return a compact human-readable description of active filters."""
    if not clauses:
        return "No filters"
    return ", ".join(f"{clause.field} {clause.operator} {clause.value}" for clause in clauses)
