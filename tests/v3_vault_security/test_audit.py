"""Tests for redacted audit trail and export."""

from __future__ import annotations

import json

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.vault_security.audit import (
    AuditAction,
    AuditExport,
    AuditFilter,
    AuditOutcome,
    AuditTrail,
    parse_audit_filter,
)


def make_trail() -> AuditTrail:
    return AuditTrail(
        clock=FixedClock(1000.0),
        text_redactor=lambda value: value.replace("hunter2secret", "[redacted]"),
    )


def test_record_and_query() -> None:
    trail = make_trail()
    first = trail.record(
        AuditAction.SETUP,
        actor="local",
        subject="case-1",
        detail={"key_id": "key_001"},
    )
    second = trail.record(
        AuditAction.UNLOCK,
        actor="operator@example.com",
        subject="case-1",
        detail={"version": 1},
        request_id="req-1",
        timestamp=1010.0,
    )
    assert len(trail.entries()) == 2
    assert trail.query(AuditFilter(actions=(AuditAction.SETUP,))) == (first,)
    assert trail.query(AuditFilter(outcomes=(AuditOutcome.SUCCESS,))) == (first, second)
    assert trail.query(AuditFilter(actor="operator")) == (second,)
    assert trail.query(AuditFilter(since=1005.0)) == (second,)
    assert trail.query(AuditFilter(limit=1, offset=1)) == (second,)
    assert trail.query(AuditFilter(request_id="req-1")) == (second,)
    assert trail.query(AuditFilter(subject="case")) == (first, second)
    assert trail.query(AuditFilter(actor="nobody")) == ()


def test_detail_redaction_recursive() -> None:
    trail = make_trail()
    entry = trail.record(
        AuditAction.POLICY_UPDATE,
        actor="local",
        subject="case-1",
        detail={
            "password": "hunter2secret",
            "note": "password: hunter2secret",
            "nested": {"api_key": "abcdefghijklmnop", "message": "hunter2secret"},
            "items": [{"token": "abcdefghijklmnop"}, "hunter2secret"],
            "safe": 42,
        },
    )
    rendered = json.dumps(entry.as_dict())
    assert "hunter2secret" not in rendered
    assert "abcdefghijklmnop" not in rendered
    assert entry.detail["password"] == "[redacted]"
    assert entry.detail["nested"]["api_key"] == "[redacted]"
    assert entry.detail["items"][0]["token"] == "[redacted]"
    assert entry.detail["safe"] == 42


def test_b00_redaction_of_email_and_flags() -> None:
    trail = AuditTrail(clock=FixedClock(5.0))
    entry = trail.record(
        AuditAction.AUDIT_EXPORT,
        actor="local",
        subject="case-1",
        detail={"note": "contact admin@example.com for flag{abc123}"},
    )
    assert "admin@example.com" not in str(entry.detail)
    assert "flag{abc123}" not in str(entry.detail)


def test_export_json_and_jsonl() -> None:
    trail = make_trail()
    trail.record(AuditAction.LOCK, actor="local", subject="case-1", detail={"ok": True})
    trail.record(
        AuditAction.ROTATE,
        actor="local",
        subject="case-1",
        detail={"note": "hunter2secret"},
    )
    document = trail.export(fmt="json")
    assert isinstance(document, AuditExport)
    assert document.format == "json"
    assert document.count == 2
    parsed = json.loads(document.to_json())
    assert parsed["count"] == 2
    assert "hunter2secret" not in document.to_json()
    jsonl = trail.export(fmt="jsonl").to_jsonl()
    assert len(jsonl.strip().splitlines()) == 2
    assert all(json.loads(line)["action"] for line in jsonl.strip().splitlines())
    assert trail.export(fmt="jsonl").render() == jsonl
    with pytest.raises(ValueError, match="format"):
        trail.export(fmt="xml")
    with pytest.raises(ValueError, match="format"):
        AuditExport(format="xml", generated_at=0.0, entries=())


def test_stats_and_capacity() -> None:
    trail = AuditTrail(clock=FixedClock(1.0), max_entries=3)
    for index in range(5):
        trail.record(
            AuditAction.LOCK,
            actor="local",
            subject="case-1",
            timestamp=float(index),
        )
    assert len(trail.entries()) == 3
    assert trail.stats()["total"] == 3
    assert trail.stats()["by_action"][AuditAction.LOCK.value] == 3
    with pytest.raises(ValueError, match="actor and subject"):
        trail.record(AuditAction.LOCK, actor="", subject="case-1")
    trail.clear()
    assert trail.entries() == ()
    with pytest.raises(ValueError, match="max_entries"):
        AuditTrail(max_entries=0)


def test_filter_validation_and_parsing() -> None:
    with pytest.raises(ValueError, match="limit"):
        AuditFilter(limit=0)
    with pytest.raises(ValueError, match="offset"):
        AuditFilter(offset=-1)
    with pytest.raises(ValueError, match="since"):
        AuditFilter(since=10.0, until=5.0)
    parsed = parse_audit_filter(
        {
            "actions": ["vault.setup"],
            "outcomes": ["success"],
            "actor": "local",
            "since": 1.0,
            "until": 2.0,
            "limit": 5,
            "offset": 1,
        }
    )
    assert parsed.actions == (AuditAction.SETUP,)
    assert parsed.outcomes == (AuditOutcome.SUCCESS,)
    assert parsed.limit == 5
    assert parsed.as_dict()["offset"] == 1
