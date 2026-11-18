from __future__ import annotations

import re

import pytest

from redscribe.v2.security.redaction import (
    RedactionRule,
    apply_redactions,
    builtin_redaction_rules,
    redact_mapping,
)
from redscribe.v2.security.scrub import ScrubPolicy, scrub_export_payload, scrub_text


def test_builtin_redaction_rules_cover_sensitive_patterns() -> None:
    names = {rule.name for rule in builtin_redaction_rules()}
    assert "private_key" in names
    assert "authorization_bearer" in names
    assert "password_assignment" in names
    assert "email" in names
    assert "ipv4" in names


def test_apply_redactions_masks_multiple_secret_types() -> None:
    text = (
        "Authorization: Bearer abcdef1234567890\n"
        "password=hunter22\n"
        "user@example.test from 10.0.0.5\n"
        "https://user:pass@example.test/path\n"
        "eyJaaaaaaaaaa.bbbbbbbbbb.cccccccccc\n"
    )
    summary = apply_redactions(text)
    assert "[REDACTED_TOKEN]" in summary.text
    assert "[REDACTED_PASSWORD]" in summary.text
    assert "[REDACTED_EMAIL]" in summary.text
    assert "[REDACTED_IPV4]" in summary.text
    assert "[REDACTED_USER]:[REDACTED_PASS]@" in summary.text
    assert "[REDACTED_JWT]" in summary.text
    assert summary.total_replacements >= 5
    assert set(summary.applied)
    assert summary.as_dict()["total_replacements"] == summary.total_replacements


def test_apply_redactions_supports_scope_and_custom_rules() -> None:
    text = "token=secretvalue email=user@example.test"
    custom = (
        RedactionRule(
            name="token",
            pattern=re.compile(r"secretvalue"),
            replacement="[TOKEN]",
            scope="body",
        ),
        RedactionRule(
            name="email",
            pattern=re.compile(r"user@example\.test"),
            replacement="[EMAIL]",
            scope="meta",
        ),
    )
    body_only = apply_redactions(text, rules=custom, scopes=("body",))
    assert "[TOKEN]" in body_only.text
    assert "user@example.test" in body_only.text
    all_scopes = apply_redactions(text, rules=custom, scopes=("all",))
    assert "[EMAIL]" in all_scopes.text
    disabled = RedactionRule(
        name="disabled",
        pattern=re.compile(r"token"),
        replacement="X",
        enabled=False,
    )
    unchanged = apply_redactions("token", rules=(disabled,))
    assert unchanged.text == "token"
    assert unchanged.total_replacements == 0


def test_apply_redactions_validates_input_type() -> None:
    with pytest.raises(TypeError):
        apply_redactions(123)  # type: ignore[arg-type]


def test_redact_mapping_handles_strings_lists_and_selected_keys() -> None:
    payload = {
        "title": "user@example.test",
        "body": ["token=abc12345", "safe"],
        "meta": {"nested": "kept"},
        "count": 1,
    }
    result = redact_mapping(payload, keys=["title", "body"])
    assert "[REDACTED_EMAIL]" in result["data"]["title"]
    assert "[REDACTED_SECRET]" in result["data"]["body"][0]
    assert result["data"]["body"][1] == "safe"
    assert result["data"]["meta"] == {"nested": "kept"}
    assert result["total_replacements"] >= 2
    assert "title" in result["fields"]


def test_scrub_text_and_export_payload_apply_policy() -> None:
    policy = ScrubPolicy(
        remove_keys=("token",),
        mask_keys=("email",),
        drop_empty=True,
        replacement="[SCRUBBED]",
    )
    cleaned_text, summary = scrub_text("password=hunter22 and user@example.test", policy=policy)
    assert "[REDACTED_PASSWORD]" in cleaned_text
    assert "[REDACTED_EMAIL]" in cleaned_text
    assert summary.total_replacements >= 2

    payload = {
        "api_token": "abcd1234",
        "owner_email": "user@example.test",
        "body": "Authorization: Bearer secretvalue",
        "items": ["password=hunter22", {"note": "10.0.0.5"}],
        "empty": "",
    }
    cleaned, report = scrub_export_payload(payload, policy=policy)
    assert cleaned["api_token"] == "[SCRUBBED]"
    assert cleaned["owner_email"] != "user@example.test"
    assert "[REDACTED_TOKEN]" in cleaned["body"]
    assert "empty" not in cleaned
    assert "api_token" in report.removed_keys
    assert any(key.endswith("owner_email") for key in report.masked_keys)
    assert report.total_redactions >= 1
    assert report.as_dict()["total_redactions"] == report.total_redactions

    no_redact = ScrubPolicy(redact_text=False)
    unchanged, no_summary = scrub_text("password=hunter22", policy=no_redact)
    assert unchanged == "password=hunter22"
    assert no_summary.total_replacements == 0
