from __future__ import annotations

import pytest

from redscribe.v2.engagements.models import (
    ScopeAction,
    ScopeRuleKind,
    Severity,
    TargetKind,
)
from redscribe.v2.engagements.validation import (
    ValidationReport,
    detect_target_kind,
    engagement_patch_report,
    finding_patch_report,
    normalize_cwe,
    normalize_text_for_match,
    optional_id,
    optional_text,
    require_choice,
    require_id,
    require_text,
    severity_for_score,
    validate_cves,
    validate_cvss_vector,
    validate_identifier,
    validate_iso_date,
    validate_port,
    validate_protocol,
    validate_references,
    validate_scope_expression,
    validate_tags,
    validate_target_value,
)


def test_validation_report_collects_errors_and_warnings() -> None:
    report = ValidationReport()
    assert report.ok is True
    report.error("name", "is required")
    report.warn("tags", "could be more specific")
    report.error("name", "must be unique")
    assert report.ok is False
    assert len(report.errors) == 2
    assert len(report.warnings) == 1
    assert report.fields() == ["name"]
    payload = report.as_dict()
    assert payload["ok"] is False
    assert payload["errors"][0]["severity"] == "error"
    assert payload["warnings"][0]["severity"] == "warning"


def test_validation_report_extend_merges_in_order() -> None:
    first = ValidationReport()
    second = ValidationReport()
    first.error("a", "first")
    second.error("b", "second")
    first.extend(second)
    assert [issue.field for issue in first.errors] == ["a", "b"]


def test_require_text_trims_and_reports_invalid_values() -> None:
    report = ValidationReport()
    assert require_text("  hello  ", "name", report) == "hello"
    assert require_text("   ", "name", report, allow_empty=True) == ""
    assert require_text(12, "name", report) == ""
    assert require_text("x" * 161, "name", report) == "x" * 161
    assert [issue.field for issue in report.errors] == ["name", "name"]


def test_optional_text_allows_none_and_trims() -> None:
    report = ValidationReport()
    assert optional_text(None, "notes", report) == ""
    assert optional_text("  notes  ", "notes", report) == "notes"
    assert optional_text(7, "notes", report) == ""
    assert report.ok is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("planning", "planning"),
        ("active", "active"),
        ("broken", ""),
        (None, ""),
    ],
)
def test_require_choice(value: object, expected: str) -> None:
    report = ValidationReport()
    assert require_choice(value, "status", ["planning", "active"], report) == expected
    assert report.ok is (expected != "")


def test_ids_validate_positive_integers() -> None:
    report = ValidationReport()
    assert require_id(3, "target_id", report) == 3
    assert require_id(0, "target_id", report) == 0
    assert require_id(True, "target_id", report) == 0
    assert optional_id(None, "asset_id", report) == 0
    assert optional_id("", "asset_id", report) == 0
    assert optional_id(9, "asset_id", report) == 9
    assert len(report.errors) == 2


def test_validate_tags_normalizes_dedupes_and_limits() -> None:
    report = ValidationReport()
    assert validate_tags("web, api,web", report) == ["web", "api"]
    assert validate_tags([" web ", 4, "", "api"], report) == ["web", "api"]
    assert validate_tags(None, report) == []
    assert validate_tags(42, report) == []
    assert len(validate_tags([f"tag-{n}" for n in range(30)], report)) == 24
    assert len(report.errors) == 2


def test_validate_references_enforces_strings_and_maximums() -> None:
    report = ValidationReport()
    assert validate_references([" https://a.test "], report) == ["https://a.test"]
    assert validate_references(None, report) == []
    assert validate_references("not-a-list", report) == []
    assert validate_references([1, "", "x" * 501], report) == []
    assert len(validate_references([f"ref-{n}" for n in range(40)], report)) == 32
    assert len(report.errors) == 5


def test_validate_identifier_enforces_slug_shape() -> None:
    report = ValidationReport()
    assert validate_identifier("q1-2026", "key", report) == "q1-2026"
    assert validate_identifier("Q1 2026", "key", report) == "Q1 2026"
    assert validate_identifier("-leading", "key", report) == "-leading"
    assert validate_identifier("", "key", report) == ""
    assert len(report.errors) == 3


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-02-28", "2026-02-28"),
        ("", ""),
        (None, ""),
        ("02/28/2026", ""),
        ("2026-13-01", ""),
        (20260101, ""),
    ],
)
def test_validate_iso_date(value: object, expected: str) -> None:
    report = ValidationReport()
    assert validate_iso_date(value, "start_date", report) == expected
    assert report.ok is (expected != "" or value in ("", None))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example.test", TargetKind.DOMAIN),
        ("192.168.1.10", TargetKind.IP_ADDRESS),
        ("10.0.0.0/24", TargetKind.CIDR),
        ("https://example.test/app", TargetKind.URL),
        ("/relative/path", TargetKind.URL),
        ("internal-app", TargetKind.HOST),
    ],
)
def test_detect_target_kind(value: str, expected: TargetKind) -> None:
    assert detect_target_kind(value) is expected


def test_validate_target_value_accepts_supported_inputs() -> None:
    report = ValidationReport()
    assert validate_target_value("app.example.test", report) == "app.example.test"
    assert validate_target_value("10.20.30.40", report) == "10.20.30.40"
    assert validate_target_value("10.20.0.0/16", report) == "10.20.0.0/16"
    assert validate_target_value("https://example.test", report) == "https://example.test"
    assert report.ok is True


def test_validate_target_value_rejects_malformed_inputs() -> None:
    report = ValidationReport()
    assert validate_target_value("bad..domain", report) == "bad..domain"
    assert validate_target_value("999.999.999.999", report) == "999.999.999.999"
    assert validate_target_value("10.0.0.0/99", report) == "10.0.0.0/99"
    assert validate_target_value("example.test/path", report) == "example.test/path"
    assert validate_target_value("", report) == ""
    assert len(report.errors) >= 2


def test_validate_port_and_protocol() -> None:
    report = ValidationReport()
    assert validate_port(None, report) == 0
    assert validate_port(443, report) == 443
    assert validate_port(0, report) == 0
    assert validate_port(70000, report) == 0
    assert validate_port("443", report) == 0
    assert validate_protocol(None, report) == "tcp"
    assert validate_protocol("UDP", report) == "udp"
    assert validate_protocol("bad protocol", report) == ""
    assert len(report.errors) == 5


def test_cwe_and_cve_normalization() -> None:
    report = ValidationReport()
    assert normalize_cwe("cwe89", report) == "CWE-89"
    assert normalize_cwe("CWE- 79", report) == "CWE-79"
    assert normalize_cwe("nonsense", report) == ""
    assert validate_cves("cve-2024-1234, CVE-2024-1234", report) == ["CVE-2024-1234"]
    assert validate_cves(["CVE-24-1234"], report) == []
    assert len(report.errors) == 2


def test_cvss_vector_validation_and_score_mapping() -> None:
    report = ValidationReport()
    vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    assert validate_cvss_vector(vector, report) == vector
    assert validate_cvss_vector("CVSS:4.0/AV:N", report) == ""
    assert validate_cvss_vector("CVSS:3.1/AV:N/AC:L", report) == ""
    assert validate_cvss_vector(None, report) == ""
    assert severity_for_score(0.0) is Severity.INFO
    assert severity_for_score(2.5) is Severity.LOW
    assert severity_for_score(5.0) is Severity.MEDIUM
    assert severity_for_score(8.0) is Severity.HIGH
    assert severity_for_score(9.9) is Severity.CRITICAL


def test_scope_expression_validation() -> None:
    report = ValidationReport()
    assert validate_scope_expression("domain", "example.test", "include", report) == (
        ScopeRuleKind.DOMAIN,
        "example.test",
        ScopeAction.INCLUDE,
    )
    assert (
        validate_scope_expression("cidr", "10.0.0.0/8", "exclude", report)[0] is ScopeRuleKind.CIDR
    )
    assert (
        validate_scope_expression("ip_address", "10.0.0.1", "include", report)[0]
        is ScopeRuleKind.IP_ADDRESS
    )
    assert (
        validate_scope_expression("url", "example.test", "include", report)[0] is ScopeRuleKind.URL
    )
    assert validate_scope_expression("cidr", "broken", "include", report)[0] is ScopeRuleKind.CIDR
    assert validate_scope_expression("keyword", "auth", "deny", report)[2] is ScopeAction.INCLUDE
    assert len(report.errors) == 3


def test_normalize_text_for_match_removes_noise() -> None:
    result = normalize_text_for_match("There is a possible SQL injection in the login form")
    assert "sql" in result
    assert "injection" in result
    assert "login" in result
    assert "possible" not in result
    assert "the" not in result
    assert "a" not in result


def test_engagement_patch_report_full_and_partial() -> None:
    full = engagement_patch_report({}, partial=False)
    assert full.ok is False
    assert set(full.fields()) >= {"name", "key"}
    partial = engagement_patch_report({"description": "updated"}, partial=True)
    assert partial.ok is True
    invalid = engagement_patch_report(
        {
            "name": "",
            "key": "Bad Key",
            "kind": "wrong",
            "status": "wrong",
            "start_date": "bad",
            "end_date": "bad",
            "tags": [1],
        },
        partial=False,
    )
    assert len(invalid.errors) >= 6


def test_finding_patch_report_full_and_partial() -> None:
    full = finding_patch_report({"title": "Example finding"}, partial=False)
    assert full.ok is True
    partial = finding_patch_report({"summary": "new summary"}, partial=True)
    assert partial.ok is True
    invalid = finding_patch_report(
        {
            "title": "",
            "severity": "severe",
            "confidence": "maybe",
            "status": "fixed",
            "cvss_vector": "CVSS:2.0/AV:N",
            "cwe": "bad",
            "cwes": ["also bad"],
            "cves": ["CVE-no"],
            "references": [None],
            "tags": [1],
            "criticality": "urgent",
        },
        partial=False,
    )
    assert len(invalid.errors) >= 10
