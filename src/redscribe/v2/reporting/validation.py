"""Validation of report configurations and outlines."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from redscribe.v2.reporting.identifiers import is_identifier
from redscribe.v2.reporting.models import (
    FINDING_STATUSES,
    REPORT_FORMATS,
    ReportConfig,
    ReportSection,
    Severity,
    ValidationIssue,
)


def _issue(
    code: str,
    message: str,
    path: str = "",
    severity: str = "error",
) -> ValidationIssue:
    if severity not in ("error", "warning"):
        raise ValueError(f"Unknown issue severity: {severity}")
    return ValidationIssue(code=code, message=message, path=path, severity=severity)  # type: ignore[arg-type]


def validate_config(config: ReportConfig) -> tuple[ValidationIssue, ...]:
    """Return all validation issues for one report configuration."""
    issues: list[ValidationIssue] = []
    if not config.title.strip():
        issues.append(_issue("title_required", "Report title cannot be empty", "title"))
    if len(config.title) > 200:
        issues.append(_issue("title_too_long", "Report title exceeds 200 characters", "title"))
    if not config.template.strip():
        issues.append(_issue("template_required", "A template is required", "template"))
    if config.classification not in (
        "public",
        "internal",
        "confidential",
        "restricted",
    ):
        issues.append(
            _issue(
                "classification_invalid",
                f"Unknown classification: {config.classification}",
                "classification",
            )
        )
    try:
        Severity.parse(config.minimum_severity)
    except ValueError:
        issues.append(
            _issue(
                "severity_invalid",
                f"Unknown minimum severity: {config.minimum_severity}",
                "minimum_severity",
            )
        )
    if config.page_size not in ("a4", "letter", "legal", "a5"):
        issues.append(
            _issue("page_size_invalid", f"Unknown page size: {config.page_size}", "page_size")
        )
    if config.orientation not in ("portrait", "landscape"):
        issues.append(
            _issue(
                "orientation_invalid",
                f"Unknown orientation: {config.orientation}",
                "orientation",
            )
        )
    if config.confidence_invalid():
        issues.append(
            _issue("confidence_invalid", "Confidence values must be between zero and one")
        )
    issues.extend(_validate_findings(config))
    issues.extend(_validate_sections(config))
    issues.extend(_validate_rules(config))
    issues.extend(_validate_redactions(config))
    return tuple(issues)


def _validate_findings(config: ReportConfig) -> Iterable[ValidationIssue]:
    identifiers: Counter[str] = Counter()
    for index, finding in enumerate(config.findings):
        path = f"findings[{index}]"
        identifiers[finding.identifier] += 1
        if not is_identifier(finding.identifier):
            yield _issue("finding_id_invalid", "Finding identifier is not stable", f"{path}.id")
        try:
            Severity.parse(finding.severity)
        except ValueError:
            yield _issue("finding_severity_invalid", "Unknown severity", f"{path}.severity")
        if finding.status not in FINDING_STATUSES:
            yield _issue("finding_status_invalid", "Unknown status", f"{path}.status")
        if not finding.title.strip():
            yield _issue("finding_title_required", "Finding title is required", f"{path}.title")
        if config.include_evidence and not finding.evidence:
            yield _issue(
                "finding_evidence_missing",
                f"Finding '{finding.identifier}' has no evidence",
                f"{path}.evidence",
                "warning",
            )
        if finding.confidence < 0.25:
            yield _issue(
                "finding_confidence_low",
                f"Finding '{finding.identifier}' has low confidence",
                f"{path}.confidence",
                "warning",
            )
    for identifier, count in identifiers.items():
        if count > 1:
            yield _issue(
                "finding_id_duplicate",
                f"Finding identifier '{identifier}' appears {count} times",
                "findings",
            )


def _validate_sections(config: ReportConfig) -> Iterable[ValidationIssue]:
    identifiers: Counter[str] = Counter()
    for root in config.sections:
        for section in root.walk():
            identifiers[section.identifier] += 1
            if not is_identifier(section.identifier):
                yield _issue(
                    "section_id_invalid",
                    f"Section identifier '{section.identifier}' is not stable",
                    f"sections.{section.identifier}.id",
                )
            if not section.title.strip():
                yield _issue(
                    "section_title_required",
                    "Section title is required",
                    f"sections.{section.identifier}.title",
                )
            if section.level > 2 and section.children:
                yield _issue(
                    "section_level_deep",
                    f"Section '{section.identifier}' nests too deeply",
                    f"sections.{section.identifier}.level",
                    "warning",
                )
    for identifier, count in identifiers.items():
        if count > 1:
            yield _issue(
                "section_id_duplicate",
                f"Section identifier '{identifier}' appears {count} times",
                "sections",
            )


def _validate_rules(config: ReportConfig) -> Iterable[ValidationIssue]:
    names: Counter[str] = Counter()
    for index, rule in enumerate(config.rules):
        names[rule.name] += 1
        if not rule.name.strip():
            yield _issue("rule_name_required", "Rule needs a name", f"rules[{index}].name")
        if not rule.tags and not rule.severities and not rule.categories and not rule.identifier:
            yield _issue(
                "rule_empty",
                f"Rule '{rule.name}' has no selection criteria",
                f"rules[{index}]",
                "warning",
            )
    for name, count in names.items():
        if count > 1:
            yield _issue("rule_name_duplicate", f"Rule '{name}' is duplicated", "rules")


def _validate_redactions(config: ReportConfig) -> Iterable[ValidationIssue]:
    names: Counter[str] = Counter()
    for index, rule in enumerate(config.redactions):
        names[rule.name] += 1
        if not rule.name.strip():
            yield _issue(
                "redaction_name_required",
                "Redaction rule needs a name",
                f"redactions[{index}].name",
            )
        if rule.disabled():
            continue
        try:
            import re

            re.compile(rule.pattern, _regex_flags(rule.flags))
        except re.error as exc:
            yield _issue(
                "redaction_pattern_invalid",
                f"Invalid redaction pattern: {exc}",
                f"redactions[{index}].pattern",
            )
    for name, count in names.items():
        if count > 1:
            yield _issue(
                "redaction_name_duplicate",
                f"Redaction rule '{name}' is duplicated",
                "redactions",
            )


def _regex_flags(flags: tuple[str, ...]) -> int:
    import re

    mapping = {
        "ignorecase": re.IGNORECASE,
        "multiline": re.MULTILINE,
        "dotall": re.DOTALL,
        "verbose": re.VERBOSE,
    }
    value = 0
    for flag in flags:
        if flag in mapping:
            value |= mapping[flag]
    return value


def validate_format(value: str) -> str:
    """Return a normalized report format or raise ``ValueError``."""
    normalized = value.strip().casefold()
    if normalized not in REPORT_FORMATS:
        raise ValueError(f"Unknown report format: {value}")
    return normalized


def validate_section_tree(sections: tuple[ReportSection, ...]) -> tuple[ValidationIssue, ...]:
    """Validate an outline independently of the rest of a configuration."""
    config = ReportConfig(title="validation", sections=sections, include_evidence=False)
    return tuple(issue for issue in validate_config(config) if issue.path.startswith("sections"))


def issues_as_dicts(issues: Iterable[ValidationIssue]) -> list[dict[str, object]]:
    """Return validation issues as JSON-ready objects."""
    return [issue.as_dict() for issue in issues]


def has_errors(issues: Iterable[ValidationIssue]) -> bool:
    """Return whether any blocking issue is present."""
    return any(issue.severity == "error" for issue in issues)
