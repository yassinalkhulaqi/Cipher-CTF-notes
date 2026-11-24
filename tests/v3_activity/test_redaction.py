"""Tests for privacy-aware activity payload redaction."""

from __future__ import annotations

import pytest

from redscribe.v3.activity.models import RedactionReport
from redscribe.v3.activity.projections import ActivityProjector
from redscribe.v3.activity.redaction import (
    ActivityRedactor,
    RedactionRule,
    redact_for_display,
    summarize_redactions,
)
from redscribe.v3.events.redaction import is_sensitive_key
from redscribe.v3.events.types import EventRecord
from tests.v3_activity.conftest import make_record


def test_sensitive_key_detection_is_reused() -> None:
    assert is_sensitive_key("api_key") is True
    assert is_sensitive_key("Auth-Token") is True
    assert is_sensitive_key("title") is False


def test_top_level_redaction_and_report() -> None:
    redactor = ActivityRedactor()
    payload = {
        "title": "SQLi finding",
        "password": "hunter2",
        "api_key": "abcd",
        "note": "mail me@example.com",
    }
    cleaned, report = redactor.redact_with_report(payload)
    assert cleaned["title"] == "SQLi finding"
    assert cleaned["password"] == "[redacted]"
    assert cleaned["api_key"] == "[redacted]"
    assert cleaned["note"] == "mail [email]"
    assert set(report.redacted_keys) == {"password", "api_key"}
    assert report.rewritten_values == 1
    assert report.keys_inspected == 4
    assert report.applied is True
    assert redactor.redact(payload) == cleaned
    assert redactor.last_report == report


def test_nested_and_list_redaction() -> None:
    redactor = ActivityRedactor()
    cleaned, report = redactor.redact_with_report(
        {
            "outer": {"secret": "nested", "stage": "done"},
            "items": [{"token": "abc"}, "Bearer eyJabc", 7],
        }
    )
    assert cleaned["outer"]["secret"] == "[redacted]"
    assert cleaned["outer"]["stage"] == "done"
    assert cleaned["items"][0]["token"] == "[redacted]"
    assert cleaned["items"][1] == "Bearer [redacted]"
    assert cleaned["items"][2] == 7
    assert "secret" in report.redacted_keys
    assert "token" in report.redacted_keys
    assert report.rewritten_values >= 1


def test_custom_rules_and_disabled_redactor() -> None:
    rule = RedactionRule(name="pin", keys=("pin", "recovery"))
    assert rule.matches("pin_code") is True
    assert rule.matches("title") is False
    assert RedactionRule("", ("pin",)).matches("pin") is False
    assert RedactionRule("x", ("pin",), enabled=False).matches("pin") is False
    redactor = ActivityRedactor(rules=(rule,))
    cleaned, report = redactor.redact_with_report({"pin_code": "1234", "title": "ok"})
    assert cleaned["pin_code"] == "[redacted]"
    assert "pin_code" in report.redacted_keys
    assert redactor.rules == (rule,)
    disabled = ActivityRedactor(enabled=False)
    passthrough, untouched = disabled.redact_with_report({"token": "visible"})
    assert passthrough == {"token": "visible"}
    assert untouched.applied is False
    assert disabled.enabled is False


def test_depth_limit_and_report_merge() -> None:
    redactor = ActivityRedactor(depth_limit=1)
    cleaned, report = redactor.redact_with_report({"a": {"b": {"c": 1}}})
    assert cleaned["a"]["b"] == {"_truncated": True}
    assert report.dropped_depth == 1
    merged = RedactionReport(("a",), 2, 1, 5).merge(RedactionReport(("a", "b"), 1, 0, 3))
    assert merged.redacted_keys == ("a", "b")
    assert merged.rewritten_values == 3
    assert merged.keys_inspected == 8
    assert summarize_redactions((report, merged)).dropped_depth == 2


def test_projection_applies_redaction_to_events(records: tuple[EventRecord, ...]) -> None:
    projector = ActivityProjector(timezone="UTC")
    first = projector.entry(records[0])
    fourth = projector.entry(records[3])
    assert first.payload["token"] == "[redacted]"
    assert first.redactions == ("token",)
    assert fourth.payload["api_key"] == "[redacted]"
    assert fourth.payload["filename"] == "proof.png"


def test_display_redaction_helper() -> None:
    cleaned, report = redact_for_display(
        {"flag": "flag{secret_value}", "extra": "one"},
        extra_keys=("extra",),
    )
    assert cleaned["flag"] == "[flag-redacted]"
    assert cleaned["extra"] == "[redacted]"
    assert report.applied is True


def test_redactor_rejects_bad_depth() -> None:
    with pytest.raises(ValueError, match="depth_limit"):
        ActivityRedactor(depth_limit=0)


def test_record_redaction_helper(records: tuple[EventRecord, ...]) -> None:
    redactor = ActivityRedactor()
    payload, report = redactor.redact_record(make_record(9, "x.y", payload={"secret": "v"}))
    assert payload == {"secret": "[redacted]"}
    assert report.redacted_keys == ("secret",)
