"""Tests for live redaction preview and enforcement."""

from __future__ import annotations

import pytest

from redscribe.v3.report_designer.model import (
    FindingItem,
    LayoutDocument,
    LayoutSection,
    RedactionRule,
)
from redscribe.v3.report_designer.redaction import (
    RedactionSpan,
    apply_redactions,
    builtin_redactions,
    compile_rule,
    preview_document,
    redact_evidence,
    redact_finding,
    redact_section,
    redact_text,
    rule_digest,
    rules_for_scope,
    sorted_rules,
    verify_redactions,
)


def test_builtin_rules_and_ordering() -> None:
    rules = builtin_redactions()
    assert [rule.name for rule in rules] == [
        "private-key",
        "api-secret",
        "email",
        "flag",
        "ipv4",
    ]
    extended = builtin_redactions(include_hosts=True, include_phones=True)
    assert "host" in [rule.name for rule in extended]
    assert "phone" in [rule.name for rule in extended]
    assert [rule.priority for rule in sorted_rules(rules)] == sorted(
        rule.priority for rule in rules
    )
    assert compile_rule(rules[0]).search("-----BEGIN PRIVATE KEY-----") is not None


def test_redact_text_audit(finding: FindingItem) -> None:
    text = "Contact admin@example.com from 10.0.0.5 with flag{ctfsecret}."
    result = redact_text(text, builtin_redactions(), section_key="s", field_name="body")
    assert result.total_matches == 3
    assert result.applied == ("email", "flag", "ipv4")
    assert result.counts == {"email": 1, "flag": 1, "ipv4": 1}
    assert "[EMAIL]" in result.text
    assert "[IP]" in result.text
    assert "[FLAG]" in result.text
    assert result.is_complete is True
    assert all(span.section_key == "s" for span in result.spans)
    assert all(isinstance(span, RedactionSpan) for span in result.spans)
    assert result.as_dict()["is_complete"] is True
    with pytest.raises(ValueError):
        redact_text("x", builtin_redactions(), context=-1)


def test_redaction_preserves_context() -> None:
    result = redact_text("start admin@example.com end", builtin_redactions(), context=6)
    span = result.spans[0]
    assert span.before.endswith("start ")
    assert span.after.startswith(" end")
    assert span.matched == "admin@example.com"


def test_scope_filtering() -> None:
    rules = (
        RedactionRule("email", r"\S+@\S+", "[EMAIL]", scope="title"),
        RedactionRule("ip", r"\d+\.\d+\.\d+\.\d+", "[IP]", scope="body"),
        RedactionRule("off", r"secret", "[X]", enabled=False),
    )
    assert [rule.name for rule in rules_for_scope(rules, "title")] == ["email"]
    assert [rule.name for rule in rules_for_scope(rules, "body")] == ["ip"]
    assert len(sorted_rules(rules)) == 2
    assert rule_digest(rules) == rule_digest(tuple(reversed(rules)))


def test_redact_evidence_and_finding(finding: FindingItem) -> None:
    redacted = redact_evidence(finding.evidence[0], builtin_redactions())
    assert "[EMAIL]" in redacted.content
    assert "[IP]" in redacted.content
    assert "[FLAG]" in redacted.content
    changed = redact_finding(finding, builtin_redactions())
    assert "[EMAIL]" in changed.summary
    assert changed.title == finding.title
    assert changed.evidence[0].content != finding.evidence[0].content


def test_apply_redactions_to_document(finding: FindingItem) -> None:
    section = LayoutSection(
        key="s",
        title="Report",
        body="Contact admin@example.com from 10.0.0.5.",
        findings=(finding,),
    )
    document = LayoutDocument(key="doc", title="Admin Report", sections=(section,))
    redacted = apply_redactions(document, builtin_redactions())
    assert "[EMAIL]" in redacted.sections[0].body
    assert "[IP]" in redacted.sections[0].body
    assert "[EMAIL]" in redacted.sections[0].findings[0].summary
    assert "[EMAIL]" in redacted.sections[0].findings[0].evidence[0].content
    assert verify_redactions(redacted, builtin_redactions()) is True
    assert verify_redactions(document, builtin_redactions()) is False


def test_preview_document(finding: FindingItem) -> None:
    document = LayoutDocument(
        key="doc",
        title="Report for admin@example.com",
        sections=(LayoutSection(key="s", title="S", findings=(finding,)),),
    )
    preview = preview_document(document, builtin_redactions(), context=4)
    assert preview.total_matches >= 5
    assert "email" in preview.applied
    assert all(span.field_name for span in preview.spans)
    assert all(span.before is not None for span in preview.spans)
    assert preview.as_dict()["total_matches"] == preview.total_matches
    with pytest.raises(ValueError):
        preview_document(document, builtin_redactions(), max_spans=0)


def test_redact_section_recursive(finding: FindingItem) -> None:
    child = LayoutSection(
        key="child", title="Child", body="mail admin@example.com", findings=(finding,)
    )
    root = LayoutSection(key="root", title="Root", children=(child,))
    redacted = redact_section(root, builtin_redactions())
    assert "[EMAIL]" in redacted.children[0].body
    assert "[EMAIL]" in redacted.children[0].findings[0].summary
    assert root.children[0].body == "mail admin@example.com"


def test_redaction_rule_validation() -> None:
    with pytest.raises(ValueError):
        RedactionRule(name="", pattern="x")
    with pytest.raises(ValueError):
        RedactionRule(name="x", pattern="")
    with pytest.raises(ValueError):
        RedactionRule(name="x", pattern="y", scope="other")  # type: ignore[arg-type]
