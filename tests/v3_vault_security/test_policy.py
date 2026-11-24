"""Tests for secret patterns, redaction precedence, and consent gates."""

from __future__ import annotations

import re

import pytest

from redscribe.v3.vault_security.policy import (
    ConsentRegistry,
    ConsentScope,
    PatternKind,
    PolicyEngine,
    PolicyError,
    PolicyRule,
    RedactionMode,
    SecretPattern,
    builtin_patterns,
    default_policy,
    masked_preview,
    policy_rules_from_dict,
)


def test_builtin_patterns_detect_secrets() -> None:
    engine = default_policy()
    sample = (
        "aws=AKIAIOSFODNN7EXAMPLE github=ghp_abcdefghijklmnopqrstuvwxyz0123456789 "
        "password: hunter2secret token=Bearer abcdefghijklmnopqrstuvwxyz"
    )
    result = engine.redact(sample)
    assert result.redactions >= 4
    assert "AKIAIOSFODNN7EXAMPLE" not in result.text
    assert "hunter2secret" not in result.text
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in result.text
    assert result.changed is True
    assert all(secret not in str(result.as_dict()) for secret in ("hunter2secret",))


def test_flag_and_private_key_detection() -> None:
    engine = default_policy()
    text = "flag{ctf_secret_value} and -----BEGIN RSA PRIVATE KEY-----"
    result = engine.redact(text)
    assert result.redactions == 2
    assert "ctf_secret_value" not in result.text
    assert "PRIVATE KEY" not in result.text
    assert "flag{" not in result.text


def test_no_matches_is_unchanged() -> None:
    engine = default_policy()
    result = engine.redact("a harmless research note")
    assert result.changed is False
    assert result.text == "a harmless research note"
    assert engine.scan("") == ()


def test_rule_precedence_and_ties() -> None:
    engine = default_policy()
    sample = "password: hunter2secret"
    engine.add_rule(
        PolicyRule(
            rule_id="a-hash",
            pattern_name="assigned_password",
            mode=RedactionMode.HASH,
            priority=10,
        )
    )
    engine.add_rule(
        PolicyRule(
            rule_id="b-remove",
            pattern_name="assigned_password",
            mode=RedactionMode.REMOVE,
            priority=10,
        )
    )
    low = PolicyRule(
        rule_id="c-mask",
        pattern_name="assigned_password",
        mode=RedactionMode.MASK,
        priority=1,
    )
    engine.add_rule(low)
    result = engine.redact(sample)
    assert "hunter2secret" not in result.text
    assert result.applied_rules[0] == "a-hash"
    assert "[hash:" in result.text
    engine.remove_rule("a-hash")
    engine.remove_rule("b-remove")
    assert engine.redact(sample).applied_rules == ("c-mask",)
    assert engine.remove_rule("c-mask") is True
    assert engine.remove_rule("c-mask") is False


def test_wildcard_rule_and_default_mode() -> None:
    engine = default_policy()
    engine.add_rule(
        PolicyRule(rule_id="global-remove", pattern_name="*", mode=RedactionMode.REMOVE, priority=5)
    )
    result = engine.redact("password: hunter2secret")
    assert result.text == ""
    assert result.applied_rules == ("global-remove",)
    custom = SecretPattern(
        name="internal_ticket",
        expression=r"TICKET-[0-9]{4}",
        default_mode=RedactionMode.HASH,
    )
    engine.add_pattern(custom)
    custom_result = engine.redact("ref TICKET-1234")
    assert "TICKET-1234" not in custom_result.text
    assert engine.remove_pattern("internal_ticket") is True
    assert engine.remove_pattern("internal_ticket") is False


def test_disabled_rule_and_pattern() -> None:
    engine = default_policy()
    engine.add_rule(
        PolicyRule(
            rule_id="off",
            pattern_name="assigned_password",
            mode=RedactionMode.REMOVE,
            enabled=False,
        )
    )
    assert "hunter2secret" not in engine.redact("password: hunter2secret").text
    disabled = SecretPattern(name="disabled_one", expression=r"SECRET123", enabled=False)
    engine.add_pattern(disabled)
    assert engine.redact("SECRET123").redactions == 0


def test_overlapping_matches_are_not_double_redacted() -> None:
    pattern = SecretPattern(name="overlap", expression=r"ABCDEF|ABC", severity="high")
    engine = PolicyEngine(patterns=(pattern,))
    result = engine.redact("prefix ABCDEF suffix")
    assert result.redactions == 1
    assert result.text == "prefix [redacted] suffix"


def test_consent_gates() -> None:
    engine = default_policy()
    text = "password: hunter2secret"
    denied = engine.evaluate(text, ConsentScope.EXPORT_PLAINTEXT)
    assert denied.allowed is False
    assert denied.requires_consent is True
    assert denied.redactions >= 1
    engine.consents.grant(ConsentScope.EXPORT_PLAINTEXT, actor="operator", at=1.0)
    allowed = engine.evaluate(text, ConsentScope.EXPORT_PLAINTEXT)
    assert allowed.allowed is True
    assert allowed.requires_consent is False
    assert engine.consents.decide(ConsentScope.EXPORT_PLAINTEXT).granted_by == "operator"
    assert engine.consents.revoke(ConsentScope.EXPORT_PLAINTEXT) is True
    assert engine.consents.revoke(ConsentScope.EXPORT_PLAINTEXT) is False
    log = engine.evaluate(text, ConsentScope.LOG_CONTENT)
    assert log.allowed is True
    assert "hunter2secret" not in str(log.as_dict())
    clean = engine.evaluate("plain note", ConsentScope.AI_ASSIST)
    assert clean.allowed is True
    assert clean.matched_patterns == ()


def test_consent_registry_decision_snapshot() -> None:
    registry = ConsentRegistry()
    decision = registry.decide(ConsentScope.AI_ASSIST)
    assert decision.requires_prompt is True
    registry.grant(ConsentScope.AI_ASSIST, actor="tester", at=2.0)
    assert registry.granted(ConsentScope.AI_ASSIST) is True
    snapshot = registry.snapshot()
    assert snapshot["granted"] == ["ai_assist"]
    assert "ai_assist" not in snapshot["pending"]
    with pytest.raises(PolicyError, match="actor"):
        registry.grant(ConsentScope.SHARE_EXTERNAL, actor="", at=1.0)


def test_assert_clean_and_invalid_definitions() -> None:
    engine = default_policy()
    engine.assert_clean("nothing to see")
    with pytest.raises(PolicyError, match="Secret pattern detected"):
        engine.assert_clean("password: hunter2secret")
    with pytest.raises(PolicyError, match="Invalid pattern expression"):
        SecretPattern(name="broken", expression="[")
    with pytest.raises(PolicyError, match="severity"):
        SecretPattern(name="bad_sev", expression="x", severity="urgent")
    with pytest.raises(PolicyError, match="Pattern name"):
        SecretPattern(name="X", expression="x")
    with pytest.raises(PolicyError, match="priority"):
        PolicyRule(rule_id="r", pattern_name="*", mode=RedactionMode.MASK, priority=9999)
    with pytest.raises(TypeError, match="text"):
        engine.scan(123)  # type: ignore[arg-type]


def test_pattern_metadata_and_serialization() -> None:
    patterns = builtin_patterns()
    assert len(patterns) >= 5
    assert patterns[0].kind in tuple(PatternKind)
    assert patterns[0].as_dict()["name"] == patterns[0].name
    assert re.compile(patterns[0].expression).search("AKIAIOSFODNN7EXAMPLE") is not None
    rules = policy_rules_from_dict(
        {"rules": [{"rule_id": "r1", "pattern": "*", "mode": "remove", "priority": 3}]}
    )
    assert rules[0].mode is RedactionMode.REMOVE
    assert rules[0].priority == 3
    with pytest.raises(PolicyError, match="rules must be a list"):
        policy_rules_from_dict({"rules": "bad"})
    engine = default_policy()
    assert engine.replace_all([rule.as_dict() for rule in rules]) == 1
    assert len(engine.rules()) == 1
    snapshot = engine.snapshot()
    assert "consents" in snapshot
    assert "patterns" in snapshot
    assert "hunter2secret" not in str(snapshot)


def test_masked_preview_never_shows_full_secret() -> None:
    secret = "supersecrettoken"
    preview = masked_preview(secret, visible=4)
    assert secret not in preview
    assert preview.startswith("supe")
    assert masked_preview("abc") == "***"
    with pytest.raises(ValueError, match="visible"):
        masked_preview(secret, visible=-1)
