"""Validation and conversion of API payloads into designer domain objects.

The namespace layer never constructs domain objects directly; all untrusted
input passes through these helpers so errors are stable V3 envelopes with
field-level detail rather than raw exceptions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, cast

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.entities.types import EntityKind, EntityRef
from redscribe.v3.report_designer.engine import DesignSpec, design_key
from redscribe.v3.report_designer.model import (
    EVIDENCE_KINDS,
    FINDING_STATUSES,
    REDACTION_SCOPES,
    EvidenceItem,
    FindingItem,
    LayoutSection,
    RedactionRule,
    SectionKind,
    SelectionRule,
    Severity,
    SeverityName,
)

T = TypeVar("T")


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    """Return a mapping or raise a typed V3 error."""
    if not isinstance(value, Mapping):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must be an object", field=field)
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    """Return a sequence or raise a typed V3 error."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must be an array", field=field)
    return value


def req_string(data: Mapping[str, Any], field: str, *, max_length: int = 500) -> str:
    """Require a non-empty string field."""
    if field not in data:
        raise V3Error.missing(field)
    value = data[field]
    if not isinstance(value, str):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must be a string", field=field)
    if not value.strip():
        raise V3Error(V3ErrorCode.INVALID_REQUEST, f"'{field}' cannot be blank", field=field)
    if len(value) > max_length:
        raise V3Error(V3ErrorCode.FIELD_TOO_LONG, f"'{field}' is too long", field=field)
    return value.strip()


def opt_string(
    data: Mapping[str, Any], field: str, default: str = "", *, max_length: int = 20000
) -> str:
    """Read an optional string field."""
    if field not in data or data[field] is None:
        return default
    value = data[field]
    if not isinstance(value, str):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must be a string", field=field)
    if len(value) > max_length:
        raise V3Error(V3ErrorCode.FIELD_TOO_LONG, f"'{field}' is too long", field=field)
    return value.strip()


def string_list(data: Mapping[str, Any], field: str) -> tuple[str, ...]:
    """Read an optional array of strings."""
    if field not in data or data[field] is None:
        return ()
    values = _sequence(data[field], field)
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must contain strings", field=field)
        result.append(item.strip())
    return tuple(value for value in result if value)


def bool_value(data: Mapping[str, Any], field: str, default: bool) -> bool:
    """Read an optional boolean field."""
    if field not in data:
        return default
    value = data[field]
    if not isinstance(value, bool):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must be a boolean", field=field)
    return value


def number_value(data: Mapping[str, Any], field: str, default: float) -> float:
    """Read an optional numeric field."""
    if field not in data:
        return default
    value = data[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{field}' must be a number", field=field)
    return float(value)


def choice_value(
    data: Mapping[str, Any],
    field: str,
    choices: Sequence[str],
    default: str,
) -> str:
    """Read a field constrained to a set of choices."""
    value = opt_string(data, field, default, max_length=120)
    if value not in choices:
        raise V3Error(V3ErrorCode.INVALID_CHOICE, f"Invalid {field}: {value}", field=field)
    return value


def parse_evidence(data: Any) -> EvidenceItem:
    """Parse one evidence object."""
    raw = _mapping(data, "evidence")
    value = req_string(raw, "value", max_length=200)
    try:
        ref = EntityRef.of(EntityKind.EVIDENCE, value, opt_string(raw, "label", max_length=300))
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="evidence") from exc
    try:
        return EvidenceItem(
            ref=ref,
            title=req_string(raw, "title", max_length=300),
            content=opt_string(raw, "content"),
            excerpt=opt_string(raw, "excerpt"),
            kind=choice_value(raw, "kind", EVIDENCE_KINDS, "note"),  # type: ignore[arg-type]
            locator=opt_string(raw, "locator", max_length=300),
            sensitive=bool_value(raw, "sensitive", False),
        )
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="evidence") from exc


def parse_finding(data: Any) -> FindingItem:
    """Parse one finding object."""
    raw = _mapping(data, "finding")
    value = req_string(raw, "value", max_length=200)
    try:
        ref = EntityRef.of(EntityKind.FINDING, value, opt_string(raw, "label", max_length=300))
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="finding") from exc
    severity = choice_value(raw, "severity", tuple(severity_values()), "medium")
    status = choice_value(raw, "status", FINDING_STATUSES, "open")
    try:
        return FindingItem(
            ref=ref,
            title=req_string(raw, "title", max_length=300),
            summary=opt_string(raw, "summary", max_length=4000),
            severity=severity,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            category=opt_string(raw, "category", max_length=200),
            tags=string_list(raw, "tags"),
            confidence=number_value(raw, "confidence", 1.0),
            impact=opt_string(raw, "impact", max_length=8000),
            recommendation=opt_string(raw, "recommendation", max_length=8000),
            evidence=tuple(
                parse_evidence(item) for item in _sequence(raw.get("evidence", ()), "evidence")
            ),
            references=string_list(raw, "references"),
            identifier=opt_string(raw, "identifier", max_length=200),
        )
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="finding") from exc


def severity_values() -> tuple[str, ...]:
    """Return valid severity values in stable order."""
    return tuple(sev.value for sev in Severity)


def parse_section(data: Any, *, depth: int = 0) -> LayoutSection:
    """Parse one layout section, recursively parsing children."""
    if depth > 12:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, "Sections nest too deeply", field="sections")
    raw = _mapping(data, "section")
    try:
        return LayoutSection(
            key=req_string(raw, "key", max_length=200),
            title=req_string(raw, "title", max_length=300),
            kind=SectionKind.parse(
                choice_value(raw, "kind", tuple(item.value for item in SectionKind), "text")
            ),
            level=int(number_value(raw, "level", 1)),
            order=int(number_value(raw, "order", 0)),
            visible=bool_value(raw, "visible", True),
            body=opt_string(raw, "body"),
            summary=opt_string(raw, "summary", max_length=4000),
            findings=tuple(
                parse_finding(item) for item in _sequence(raw.get("findings", ()), "findings")
            ),
            children=tuple(
                parse_section(item, depth=depth + 1)
                for item in _sequence(raw.get("children", ()), "children")
            ),
            page_break_before=bool_value(raw, "page_break_before", False),
            include_toc=bool_value(raw, "include_toc", True),
            metadata={
                str(key): str(value)
                for key, value in _mapping(raw.get("metadata", {}), "metadata").items()
            },
        )
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="section") from exc


def parse_selection_rule(data: Any) -> SelectionRule:
    """Parse one selection rule."""
    raw = _mapping(data, "rule")
    try:
        return SelectionRule(
            name=req_string(raw, "name", max_length=200),
            action=choice_value(raw, "action", ("include", "exclude"), "include"),  # type: ignore[arg-type]
            severities=cast(
                tuple[SeverityName, ...],
                tuple(sev for sev in string_list(raw, "severities") if sev in severity_values()),
            ),
            statuses=string_list(raw, "statuses"),
            tags=string_list(raw, "tags"),
            categories=string_list(raw, "categories"),
            minimum_confidence=number_value(raw, "minimum_confidence", 0.0),
            identifier=opt_string(raw, "identifier", max_length=200),
        )
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="rules") from exc


def parse_redaction_rule(data: Any) -> RedactionRule:
    """Parse one redaction rule."""
    raw = _mapping(data, "redaction")
    try:
        return RedactionRule(
            name=req_string(raw, "name", max_length=200),
            pattern=req_string(raw, "pattern", max_length=2000),
            replacement=opt_string(raw, "replacement", "[REDACTED]", max_length=200),
            enabled=bool_value(raw, "enabled", True),
            priority=int(number_value(raw, "priority", 0)),
            scope=choice_value(raw, "scope", REDACTION_SCOPES, "all"),  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc), field="redactions") from exc


def spec_from_dict(data: Any) -> DesignSpec:
    """Parse a full design specification from an API payload."""
    raw = _mapping(data, "body")
    title = req_string(raw, "title", max_length=300)
    try:
        return DesignSpec(
            key=opt_string(raw, "key", max_length=200) or design_key(title),
            title=title,
            subtitle=opt_string(raw, "subtitle", max_length=300),
            client=opt_string(raw, "client", max_length=300),
            author=opt_string(raw, "author", max_length=300),
            classification=opt_string(raw, "classification", "internal", max_length=100),
            generated_at=opt_string(raw, "generated_at", max_length=100),
            theme=opt_string(raw, "theme", "client", max_length=100),
            sections=tuple(
                parse_section(item) for item in _sequence(raw.get("sections", ()), "sections")
            ),
            findings=tuple(
                parse_finding(item) for item in _sequence(raw.get("findings", ()), "findings")
            ),
            rules=tuple(
                parse_selection_rule(item) for item in _sequence(raw.get("rules", ()), "rules")
            ),
            redactions=tuple(
                parse_redaction_rule(item)
                for item in _sequence(raw.get("redactions", ()), "redactions")
            ),
            minimum_severity=choice_value(raw, "minimum_severity", severity_values(), "info"),
            statuses=string_list(raw, "statuses"),
            tags=string_list(raw, "tags"),
            require_evidence=bool_value(raw, "require_evidence", False),
            include_sensitive_evidence=bool_value(raw, "include_sensitive_evidence", False),
            formats=tuple(string_list(raw, "formats")) or ("html", "markdown", "json", "print"),
            options={
                str(key): bool(value)
                for key, value in _mapping(raw.get("options", {}), "options").items()
            },
        )
    except V3Error:
        raise
    except ValueError as exc:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(exc)) from exc


def parse_format(value: Any) -> str:
    """Parse a single render format from a request body."""
    raw = _mapping(value, "body")
    return req_string(raw, "format", max_length=40)
