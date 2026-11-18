"""Validation rules for engagement-core entities.

Validators return structured reports instead of raising so the service layer can
collect every problem in one response. All functions are pure and safe to reuse
from API handlers and frontend ports.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from redscribe.v2.engagements.models import (
    SEVERITY_ORDER,
    Confidence,
    Criticality,
    EngagementKind,
    EngagementStatus,
    FindingStatus,
    ScopeAction,
    ScopeRuleKind,
    Severity,
    TargetKind,
)
from redscribe.v2.engagements.util import dedupe, slugify, tokens

MAX_NAME_LENGTH = 160
MAX_KEY_LENGTH = 64
MAX_TEXT_LENGTH = 20000
MAX_SHORT_TEXT_LENGTH = 2000
MAX_TAGS = 24
MAX_TAG_LENGTH = 48
MAX_REFERENCES = 32

_CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,7}$", re.IGNORECASE)
_CWE_PATTERN = re.compile(r"^CWE-?\d{1,5}$", re.IGNORECASE)
_VECTOR_PATTERN = re.compile(r"^CVSS:3\.[01](?:/[A-Z]+:[A-Z0-9/]+)+$", re.IGNORECASE)
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_PROTOCOL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]{0,15}$")

KNOWN_NOISE = {
    "a",
    "an",
    "and",
    "the",
    "in",
    "on",
    "at",
    "via",
    "for",
    "of",
    "to",
    "is",
    "be",
    "with",
    "issue",
    "found",
    "possible",
    "potential",
}


@dataclass(slots=True)
class ValidationIssue:
    """One validation problem attached to a request field."""

    field: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message, "severity": self.severity}


@dataclass(slots=True)
class ValidationReport:
    """Accumulated validation issues with convenience accessors."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def error(self, name: str, message: str) -> None:
        self.issues.append(ValidationIssue(name, message, "error"))

    def warn(self, name: str, message: str) -> None:
        self.issues.append(ValidationIssue(name, message, "warning"))

    def extend(self, other: ValidationReport) -> None:
        self.issues.extend(other.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def fields(self) -> list[str]:
        return list(dict.fromkeys(issue.field for issue in self.errors))

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
        }


def require_text(
    value: object,
    name: str,
    report: ValidationReport,
    *,
    max_length: int = MAX_NAME_LENGTH,
    allow_empty: bool = False,
) -> str:
    """Validate a required text field and return the trimmed value."""
    if not isinstance(value, str):
        report.error(name, "must be a string")
        return ""
    result = value.strip()
    if not result and not allow_empty:
        report.error(name, "is required")
    if len(result) > max_length:
        report.error(name, f"must be at most {max_length} characters")
    return result


def optional_text(
    value: object,
    name: str,
    report: ValidationReport,
    *,
    max_length: int = MAX_SHORT_TEXT_LENGTH,
) -> str:
    """Validate an optional text field and return the trimmed value."""
    if value is None:
        return ""
    if not isinstance(value, str):
        report.error(name, "must be a string")
        return ""
    result = value.strip()
    if len(result) > max_length:
        report.error(name, f"must be at most {max_length} characters")
    return result


def require_choice(
    value: object, name: str, allowed: Iterable[str], report: ValidationReport
) -> str:
    """Validate that a value belongs to the allowed set."""
    choices = list(allowed)
    if not isinstance(value, str):
        report.error(name, "must be a string")
        return ""
    if value not in choices:
        report.error(name, f"must be one of: {', '.join(choices)}")
        return ""
    return value


def require_id(value: object, name: str, report: ValidationReport) -> int:
    """Validate a positive integer identifier."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        report.error(name, "must be a positive integer")
        return 0
    return value


def optional_id(value: object, name: str, report: ValidationReport) -> int:
    """Validate an optional positive integer identifier."""
    if value is None or value == "":
        return 0
    return require_id(value, name, report)


def validate_tags(value: object, report: ValidationReport, *, name: str = "tags") -> list[str]:
    """Normalize and validate a list of tags."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw = [part.strip() for part in value if isinstance(part, str)]
    else:
        report.error(name, "must be a list of strings")
        return []
    for tag in raw:
        if tag and len(tag) > MAX_TAG_LENGTH:
            report.error(name, f"tags must be at most {MAX_TAG_LENGTH} characters")
    unique = dedupe(tag for tag in raw if tag)
    if len(unique) > MAX_TAGS:
        report.error(name, f"at most {MAX_TAGS} tags are allowed")
    return unique[:MAX_TAGS]


def validate_references(value: object, report: ValidationReport) -> list[str]:
    """Validate a list of reference URLs or document identifiers."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        report.error("references", "must be a list of strings")
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            report.error("references", "entries must be non-empty strings")
            continue
        cleaned = item.strip()
        if len(cleaned) > 500:
            report.error("references", "entries must be at most 500 characters")
            continue
        result.append(cleaned)
    if len(result) > MAX_REFERENCES:
        report.error("references", f"at most {MAX_REFERENCES} references are allowed")
    return result[:MAX_REFERENCES]


def validate_identifier(value: object, name: str, report: ValidationReport) -> str:
    """Validate a short key that is safe to use in paths and filenames."""
    raw = require_text(value, name, report, max_length=MAX_KEY_LENGTH)
    if not raw:
        return ""
    normalized = slugify(raw)
    if normalized != raw.casefold():
        report.error(name, "use lowercase letters, digits, and hyphens only")
    if not normalized[0].isalnum():
        report.error(name, "must start with a letter or digit")
    return raw


def validate_iso_date(value: object, name: str, report: ValidationReport) -> str:
    """Validate a YYYY-MM-DD date string."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        report.error(name, "must be a date string")
        return ""
    try:
        date.fromisoformat(value)
    except ValueError:
        report.error(name, "must use YYYY-MM-DD format")
        return ""
    return value


def detect_target_kind(value: str) -> TargetKind:
    """Guess a target kind from its textual value."""
    candidate = value.strip()
    if "/" in candidate and ("://" in candidate or candidate.startswith("/")):
        return TargetKind.URL
    try:
        ipaddress.ip_address(candidate)
        return TargetKind.IP_ADDRESS
    except ValueError:
        pass
    try:
        ipaddress.ip_network(candidate, strict=False)
        return TargetKind.CIDR
    except ValueError:
        pass
    if "." in candidate and _HOST_PATTERN.fullmatch(candidate):
        return TargetKind.DOMAIN
    return TargetKind.HOST


def validate_target_value(value: object, report: ValidationReport) -> str:
    """Validate a target host, IP, CIDR, URL, or application label."""
    raw = require_text(value, "value", report, max_length=MAX_NAME_LENGTH)
    if not raw:
        return ""
    kind = detect_target_kind(raw)
    if kind is TargetKind.URL and "://" not in raw and not raw.startswith("/"):
        report.error("value", "URL targets must include a scheme")
    if kind is TargetKind.DOMAIN and ".." in raw:
        report.error("value", "domain labels cannot be empty")
    if kind is TargetKind.IP_ADDRESS:
        try:
            ipaddress.ip_address(raw)
        except ValueError:
            report.error("value", "must be a valid IP address")
    if kind is TargetKind.CIDR:
        try:
            ipaddress.ip_network(raw, strict=False)
        except ValueError:
            report.error("value", "must be a valid CIDR network")
    return raw


def validate_port(value: object, report: ValidationReport) -> int:
    """Validate a TCP/UDP port number."""
    if value is None or value == "":
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        report.error("port", "must be an integer between 1 and 65535")
        return 0
    if value < 1 or value > 65535:
        report.error("port", "must be between 1 and 65535")
        return 0
    return value


def validate_protocol(value: object, report: ValidationReport) -> str:
    """Validate a service protocol token."""
    raw = require_text(value, "protocol", report, max_length=32, allow_empty=True)
    if raw and not _PROTOCOL_PATTERN.fullmatch(raw.casefold()):
        report.error("protocol", "must be a lowercase protocol token")
        return ""
    return raw.casefold() or "tcp"


def normalize_cwe(value: object, report: ValidationReport, *, name: str = "cwe") -> str:
    """Normalize a CWE identifier to ``CWE-nnn`` form."""
    if value is None:
        return ""
    raw = require_text(value, name, report, max_length=32, allow_empty=True)
    if not raw:
        return ""
    if not _CWE_PATTERN.fullmatch(raw.replace(" ", "")):
        report.error(name, "must look like CWE-79")
        return ""
    digits = re.sub(r"\D", "", raw)
    return f"CWE-{int(digits)}"


def validate_cves(value: object, report: ValidationReport) -> list[str]:
    """Validate CVE identifiers and normalize their casing."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        raw = [part.strip() for part in value if isinstance(part, str) and part.strip()]
    else:
        report.error("cves", "must be a list of CVE identifiers")
        return []
    result: list[str] = []
    for item in raw:
        if not _CVE_PATTERN.fullmatch(item):
            report.error("cves", f"invalid CVE identifier: {item}")
            continue
        result.append(item.upper())
    return dedupe(result)


def validate_cvss_vector(value: object, report: ValidationReport) -> str:
    """Validate the shape of a CVSS v3.x base vector."""
    raw = require_text(value, "cvss_vector", report, max_length=80, allow_empty=True)
    if not raw:
        return ""
    if not _VECTOR_PATTERN.fullmatch(raw):
        report.error("cvss_vector", "must be a CVSS:3.x base vector")
        return ""
    parts = raw.split("/")[1:]
    keys = [part.split(":", 1)[0] for part in parts]
    required = {"AV", "AC", "PR", "UI", "S", "C", "I", "A"}
    if set(keys) != required or len(keys) != len(required):
        report.error("cvss_vector", "must contain exactly the eight base metrics")
        return ""
    return raw


def severity_for_score(score: float) -> Severity:
    """Map a CVSS base score to its qualitative severity band."""
    if score >= 9.0:
        return Severity.CRITICAL
    if score >= 7.0:
        return Severity.HIGH
    if score >= 4.0:
        return Severity.MEDIUM
    if score > 0.0:
        return Severity.LOW
    return Severity.INFO


def validate_scope_expression(
    kind: object,
    value: object,
    action: object,
    report: ValidationReport,
) -> tuple[ScopeRuleKind, str, ScopeAction]:
    """Validate a scope rule expression and its action."""
    rule_kind = ScopeRuleKind(
        require_choice(kind, "kind", [item.value for item in ScopeRuleKind], report)
        or ScopeRuleKind.KEYWORD.value
    )
    rule_action = ScopeAction(
        require_choice(action, "action", [item.value for item in ScopeAction], report)
        or ScopeAction.INCLUDE.value
    )
    expression = require_text(value, "value", report, max_length=MAX_NAME_LENGTH)
    if rule_kind is ScopeRuleKind.PORT:
        validate_port(expression, report)
    elif rule_kind is ScopeRuleKind.CIDR:
        try:
            ipaddress.ip_network(expression, strict=False)
        except ValueError:
            report.error("value", "must be a valid CIDR network")
    elif rule_kind is ScopeRuleKind.IP_ADDRESS:
        try:
            ipaddress.ip_address(expression)
        except ValueError:
            report.error("value", "must be a valid IP address")
    elif rule_kind is ScopeRuleKind.URL and "://" not in expression:
        report.error("value", "URL rules must include a scheme")
    return rule_kind, expression, rule_action


def normalize_text_for_match(value: str) -> tuple[str, ...]:
    """Produce meaningful normalized tokens for duplicate comparison."""
    return tuple(token for token in tokens(value) if token not in KNOWN_NOISE and len(token) > 2)


def engagement_patch_report(data: Mapping[str, Any], *, partial: bool = True) -> ValidationReport:
    """Validate common engagement fields present in a create/update payload."""
    report = ValidationReport()
    if not partial or "name" in data:
        require_text(data.get("name"), "name", report)
    if not partial or "key" in data:
        validate_identifier(data.get("key"), "key", report)
    if not partial or "kind" in data:
        require_choice(
            data.get("kind", EngagementKind.PENTEST.value),
            "kind",
            [item.value for item in EngagementKind],
            report,
        )
    if not partial or "status" in data:
        require_choice(
            data.get("status", EngagementStatus.PLANNING.value),
            "status",
            [item.value for item in EngagementStatus],
            report,
        )
    if "client" in data:
        optional_text(data.get("client"), "client", report, max_length=MAX_NAME_LENGTH)
    if "description" in data:
        optional_text(data.get("description"), "description", report, max_length=MAX_TEXT_LENGTH)
    if "start_date" in data:
        validate_iso_date(data.get("start_date"), "start_date", report)
    if "end_date" in data:
        validate_iso_date(data.get("end_date"), "end_date", report)
    if "tags" in data:
        validate_tags(data.get("tags"), report)
    return report


def finding_patch_report(data: Mapping[str, Any], *, partial: bool = True) -> ValidationReport:
    """Validate common finding fields present in a create/update payload."""
    report = ValidationReport()
    if not partial or "title" in data:
        require_text(data.get("title"), "title", report)
    for name in ("summary", "impact", "remediation", "reproduction_steps"):
        if name in data or not partial:
            optional_text(data.get(name), name, report, max_length=MAX_TEXT_LENGTH)
    if not partial or "severity" in data:
        require_choice(
            data.get("severity", Severity.MEDIUM.value),
            "severity",
            [item.value for item in SEVERITY_ORDER],
            report,
        )
    if not partial or "confidence" in data:
        require_choice(
            data.get("confidence", Confidence.MEDIUM.value),
            "confidence",
            [item.value for item in Confidence],
            report,
        )
    if not partial or "status" in data:
        require_choice(
            data.get("status", FindingStatus.DRAFT.value),
            "status",
            [item.value for item in FindingStatus],
            report,
        )
    if "cvss_vector" in data:
        validate_cvss_vector(data.get("cvss_vector"), report)
    if "cwe" in data:
        normalize_cwe(data.get("cwe"), report)
    if "cwes" in data:
        values = data.get("cwes")
        if isinstance(values, (list, tuple)):
            for index, value in enumerate(values):
                normalize_cwe(value, report, name=f"cwes[{index}]")
    if "cves" in data:
        validate_cves(data.get("cves"), report)
    if "references" in data:
        validate_references(data.get("references"), report)
    if "tags" in data:
        validate_tags(data.get("tags"), report)
    if "criticality" in data:
        require_choice(
            data.get("criticality"),
            "criticality",
            [item.value for item in Criticality],
            report,
        )
    return report
