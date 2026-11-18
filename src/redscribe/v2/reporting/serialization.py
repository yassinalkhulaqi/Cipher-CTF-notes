"""Parsing and serialization for report configuration payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.reporting.models import (
    EVIDENCE_KINDS,
    FINDING_STATUSES,
    REPORT_FORMATS,
    SEVERITY_ORDER,
    EvidenceRef,
    Finding,
    InclusionRule,
    RedactionRule,
    ReportConfig,
    ReportSection,
)
from redscribe.v2.reporting.templates import get_template


def _string(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    raise ValueError(f"Expected string, got {type(value).__name__}")


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence):
        return tuple(_string(item) for item in value if _string(item).strip())
    raise ValueError("Expected a string or list of strings")


def _boolean(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    raise ValueError("Expected boolean")


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def parse_evidence(value: Any) -> EvidenceRef:
    """Parse one evidence reference payload."""
    data = _mapping(value, label="evidence")
    identifier = _string(data.get("identifier"), default="")
    title = _string(data.get("title"), default="") or identifier
    kind = _string(data.get("kind"), default="note")
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"Unknown evidence kind: {kind}")
    source_id = data.get("source_id")
    if source_id is not None and (isinstance(source_id, bool) or not isinstance(source_id, int)):
        raise ValueError("source_id must be an integer")
    confidence = data.get("sensitive", False)
    return EvidenceRef(
        identifier=identifier,
        title=title,
        content=_string(data.get("content")),
        kind=kind,
        source_id=source_id,
        source_path=_string(data.get("source_path")),
        source_updated_at=_string(data.get("source_updated_at")),
        locator=_string(data.get("locator")),
        excerpt=_string(data.get("excerpt")),
        sensitive=_boolean(confidence),
    )


def parse_finding(value: Any) -> Finding:
    """Parse one finding payload."""
    data = _mapping(value, label="finding")
    status = _string(data.get("status"), default="open")
    if status not in FINDING_STATUSES:
        raise ValueError(f"Unknown finding status: {status}")
    severity = _string(data.get("severity"), default="medium")
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"Unknown severity: {severity}")
    confidence = data.get("confidence", 1.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number")
    return Finding(
        identifier=_string(data.get("identifier")) or "finding",
        title=_string(data.get("title")),
        summary=_string(data.get("summary")),
        severity=severity,
        status=status,
        category=_string(data.get("category")),
        tags=_strings(data.get("tags")),
        evidence=tuple(parse_evidence(item) for item in data.get("evidence", ())),
        impact=_string(data.get("impact")),
        recommendation=_string(data.get("recommendation")),
        references=_strings(data.get("references")),
        confidence=float(confidence),
        cvss=_string(data.get("cvss")),
        cwe=_string(data.get("cwe")),
        affected=_string(data.get("affected")),
    )


def parse_section(value: Any) -> ReportSection:
    """Parse a section tree payload."""
    data = _mapping(value, label="section")
    metadata_value = data.get("metadata", {})
    if not isinstance(metadata_value, Mapping):
        raise ValueError("section metadata must be an object")
    metadata = {_string(key): _string(item) for key, item in metadata_value.items()}
    level_value = data.get("level", 1)
    if isinstance(level_value, bool) or not isinstance(level_value, int):
        raise ValueError("section level must be an integer")
    order_value = data.get("order", 0)
    if isinstance(order_value, bool) or not isinstance(order_value, int):
        raise ValueError("section order must be an integer")
    return ReportSection(
        identifier=_string(data.get("identifier")) or "section",
        title=_string(data.get("title")) or "Section",
        kind=_string(data.get("kind"), default="text"),
        body=_string(data.get("body")),
        summary=_string(data.get("summary")),
        findings=tuple(parse_finding(item) for item in data.get("findings", ())),
        children=tuple(parse_section(item) for item in data.get("children", ())),
        order=order_value,
        level=level_value,
        include_toc=_boolean(data.get("include_toc"), default=True),
        page_break_before=_boolean(data.get("page_break_before")),
        metadata=metadata,
    )


def parse_rule(value: Any) -> InclusionRule:
    """Parse one inclusion rule payload."""
    data = _mapping(value, label="rule")
    action = _string(data.get("action"), default="include")
    if action not in ("include", "exclude"):
        raise ValueError(f"Unknown rule action: {action}")
    minimum = data.get("minimum_confidence", 0.0)
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
        raise ValueError("minimum_confidence must be a number")
    return InclusionRule(
        name=_string(data.get("name")) or "rule",
        action=action,  # type: ignore[arg-type]
        tags=_strings(data.get("tags")),
        severities=tuple(_strings(data.get("severities"))),  # type: ignore[arg-type]
        statuses=tuple(_strings(data.get("statuses"))),
        categories=_strings(data.get("categories")),
        minimum_confidence=float(minimum),
        path_prefix=_string(data.get("path_prefix")),
        identifier=_string(data.get("identifier")),
    )


def parse_redaction(value: Any) -> RedactionRule:
    """Parse one redaction rule payload."""
    data = _mapping(value, label="redaction")
    scope = _string(data.get("scope"), default="all")
    priority = data.get("priority", 0)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ValueError("priority must be an integer")
    return RedactionRule(
        name=_string(data.get("name")) or "rule",
        pattern=_string(data.get("pattern")),
        replacement=_string(data.get("replacement"), default="[REDACTED]"),
        enabled=_boolean(data.get("enabled"), default=True),
        priority=priority,
        flags=_strings(data.get("flags")) or ("ignorecase",),
        scope=scope,  # type: ignore[arg-type]
    )


def parse_config(
    value: Mapping[str, Any], *, default_title: str = "Security Report"
) -> ReportConfig:
    """Parse a report configuration payload."""
    template = _string(value.get("template"), default="engagement") or "engagement"
    template_info = get_template(template)
    statuses = tuple(_strings(value.get("statuses")))
    severity = _string(value.get("minimum_severity"), default="info") or "info"
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"Unknown severity: {severity}")
    return ReportConfig(
        title=_string(value.get("title")) or default_title or template_info.default_title,
        template=template,
        client=_string(value.get("client")),
        author=_string(value.get("author")),
        classification=_string(value.get("classification"), default=template_info.classification),
        scope=_strings(value.get("scope")),
        generated_at=_string(value.get("generated_at")),
        introduction=_string(value.get("introduction")),
        conclusion=_string(value.get("conclusion")),
        sections=tuple(parse_section(item) for item in value.get("sections", ()))
        or template_info.sections,
        findings=tuple(parse_finding(item) for item in value.get("findings", ())),
        rules=tuple(parse_rule(item) for item in value.get("rules", ())),
        redactions=tuple(parse_redaction(item) for item in value.get("redactions", ())),
        tags=_strings(value.get("tags")),
        statuses=statuses,
        minimum_severity=severity,
        include_empty_sections=_boolean(value.get("include_empty_sections")),
        include_evidence=_boolean(value.get("include_evidence"), default=True),
        include_appendices=_boolean(value.get("include_appendices"), default=True),
        page_size=_string(value.get("page_size"), default="a4") or "a4",
        orientation=_string(value.get("orientation"), default="portrait") or "portrait",
        print_profile=_string(value.get("print_profile"), default=template_info.print_profile)
        or template_info.print_profile,
        print_cover=_boolean(value.get("print_cover"), default=True),
        print_toc=_boolean(value.get("print_toc"), default=True),
        redact_sensitive=_boolean(value.get("redact_sensitive"), default=True),
        notes=_string(value.get("notes")),
    )


def parse_format(value: Any) -> str:
    """Parse and normalize a report format value."""
    fmt = _string(value, default="markdown").strip().casefold() or "markdown"
    if fmt not in REPORT_FORMATS:
        raise ValueError(f"Unknown report format: {value}")
    return fmt


def config_from_json(raw: str) -> ReportConfig:
    """Parse a JSON string into a report configuration."""
    import json

    return parse_config(_mapping(json.loads(raw), label="config"))


def config_to_json(config: ReportConfig) -> str:
    """Serialize a report configuration to stable JSON."""
    import json

    return json.dumps(config.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def summary_of_config(config: ReportConfig) -> dict[str, object]:
    """Return a compact display summary of a configuration."""
    return {
        "title": config.title,
        "template": config.template,
        "classification": config.classification,
        "sections": sum(len(section.walk()) for section in config.sections),
        "findings": config.finding_count(),
        "rules": len(config.rules),
        "redactions": len(config.redactions),
    }
