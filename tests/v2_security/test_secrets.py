from __future__ import annotations

import pytest

from redscribe.v2.security.secrets import (
    builtin_secret_patterns,
    patterns_from_names,
    scan_mapping,
    scan_secrets,
)


def test_builtin_secret_patterns_cover_expected_detectors() -> None:
    names = {pattern.name for pattern in builtin_secret_patterns()}
    assert "aws_access_key_id" in names
    assert "github_token" in names
    assert "private_key_block" in names
    assert "jwt" in names
    assert "database_uri" in names
    assert len(names) >= 15


def test_scan_secrets_detects_common_credentials() -> None:
    text = (
        "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n"
        "token = ghp_abcdefghijklmnopqrstuvwxyz\n"
        "password: hunter22\n"
        "Authorization: Bearer abc.def.ghi12345678901234567890\n"
        "postgres://user:pass@example.com/db\n"
    )
    result = scan_secrets(text)
    names = {finding.name for finding in result.findings}
    assert "aws_access_key_id" in names
    assert "github_token" in names
    assert "password_assignment" in names
    assert "database_uri" in names
    assert result.count >= 4
    assert result.highest_severity in {"high", "critical"}
    assert result.scanned_characters == len(text)
    assert result.as_dict()["count"] == result.count


def test_scan_secrets_masks_values_and_reports_locations() -> None:
    token = "ghp_" + "a" * 24
    text = f"prefix {token} suffix"
    result = scan_secrets(text)
    finding = next(item for item in result.findings if item.name == "github_token")
    assert finding.value == token
    assert finding.masked != token
    assert finding.masked.startswith("ghp_")
    assert finding.masked.endswith(token[-4:])
    assert finding.start == text.index(token)
    assert finding.end == finding.start + len(token)
    assert finding.line == 1
    assert finding.column == len("prefix ") + 1
    assert finding.context
    assert 0.0 < finding.confidence <= 1.0


def test_scan_secrets_supports_selected_patterns_and_limits() -> None:
    text = "AKIA1234567890ABCDEF AKIAABCDEFGHIJKLMNO ghp_abcdefghijklmnopqrstuvwxyz1234"
    aws_only = scan_secrets(text, patterns=patterns_from_names(["aws_access_key_id"]))
    assert {finding.name for finding in aws_only.findings} == {"aws_access_key_id"}
    limited = scan_secrets(text, max_findings=1)
    assert limited.count == 1
    unknown = patterns_from_names(["does-not-exist"])
    assert len(unknown) == len(builtin_secret_patterns())


def test_scan_secrets_entropy_filtering_and_private_key_detection() -> None:
    private_key = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIBVwIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEA\n"
        "-----END PRIVATE KEY-----"
    )
    result = scan_secrets(private_key, include_entropy=True)
    assert any(finding.name == "private_key_block" for finding in result.findings)
    noisy = "value=" + "a" * 40
    result_noisy = scan_secrets(noisy, include_entropy=True)
    assert result_noisy.entropy_flagged >= 0
    payload = scan_secrets(noisy, include_entropy=False)
    assert payload.pattern_count == len(builtin_secret_patterns())


def test_scan_secrets_validates_inputs() -> None:
    with pytest.raises(TypeError):
        scan_secrets(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        scan_secrets("x", context_radius=-1)
    with pytest.raises(ValueError):
        scan_secrets("x", max_findings=0)


def test_scan_mapping_reports_per_field_results() -> None:
    payload = {
        "title": "safe",
        "body": "token=ghp_abcdefghijklmnopqrstuvwxyz",
        "notes": "AKIA1234567890ABCD",
        "count": 3,
    }
    result = scan_mapping(payload)
    assert result["count"] >= 2
    assert set(result["fields"]) == {"title", "body", "notes"}
    assert result["fields"]["title"]["count"] == 0
    assert result["fields"]["body"]["count"] >= 1
    selected = scan_mapping(payload, keys=["body"])
    assert set(selected["fields"]) == {"body"}
