from __future__ import annotations

import pytest

from redscribe.v2.security.consent import DEFAULT_FLAGS, ConsentRegistry
from redscribe.v2.security.policies import (
    AccessDecision,
    AccessPolicy,
    PolicyEffect,
    PolicyEngine,
    PolicyRule,
    default_access_policy,
    evaluate_access,
)
from redscribe.v2.security.privacy import (
    apply_privacy_level,
    compare_privacy_levels,
    merge_privacy_preferences,
    parse_privacy_level,
    privacy_mode_for,
)


def test_privacy_levels_and_aliases() -> None:
    assert parse_privacy_level(None).value == "standard"
    assert parse_privacy_level("strict").value == "strict"
    assert parse_privacy_level("private").value == "sensitive"
    assert parse_privacy_level("default").value == "standard"
    with pytest.raises(ValueError):
        parse_privacy_level("unknown")
    strict = privacy_mode_for("strict")
    assert strict.redact_secrets is True
    assert strict.allow_external_links is False
    assert strict.allow_command_copy is False
    assert strict.require_export_consent is True
    payload = apply_privacy_level("sensitive")
    assert payload["level"] == "sensitive"
    assert payload["label"] == "Sensitive"
    assert payload["description"]
    assert len(payload["controls"]) == 8
    assert compare_privacy_levels("open", "strict") == -1
    assert compare_privacy_levels("strict", "sensitive") == 1
    assert compare_privacy_levels("standard", "normal") == 0


def test_merge_privacy_preferences_overrides_boolean_controls() -> None:
    merged = merge_privacy_preferences(
        "standard", {"allow_external_links": False, "share_telemetry": False, "ignored": "x"}
    )
    assert merged["allow_external_links"] is False
    assert merged["share_telemetry"] is False
    assert merged["customized"] is True
    controls = {item["key"]: item["enabled"] for item in merged["controls"]}
    assert controls["allow_external_links"] is False
    unchanged = merge_privacy_preferences("open")
    assert unchanged["customized"] is not True


def test_consent_registry_defaults_updates_and_summary() -> None:
    registry = ConsentRegistry.with_defaults()
    assert len(registry.flags) == len(DEFAULT_FLAGS)
    assert registry.is_granted("retain_audit_details") is True
    assert registry.is_granted("export_sensitive") is False
    required = registry.required_for("export")
    assert {flag.key for flag in required} >= {"export_sensitive", "store_encrypted_exports"}
    missing = registry.missing_for("export")
    assert any(flag.key == "export_sensitive" for flag in missing)
    decision = registry.set_decision("export_sensitive", True, source="test", note="approved")
    assert decision.granted is True
    assert registry.is_granted("export_sensitive") is True
    assert registry.missing_for("export") == tuple(
        flag
        for flag in required
        if flag.key != "export_sensitive" and not registry.is_granted(flag.key)
    )
    changed = registry.apply_bulk(
        {"copy_commands": False, "unknown": True, "retain_audit_details": "no"}
    )
    assert len(changed) == 1
    assert changed[0]["key"] == "copy_commands"
    summary = registry.summary()
    assert summary["total"] == len(DEFAULT_FLAGS)
    assert summary["granted"] + summary["denied"] == summary["total"]
    context = registry.context()
    assert context["consent_export_sensitive"] is True
    with pytest.raises(KeyError):
        registry.set_decision("missing", True)


def test_policy_evaluation_and_engine() -> None:
    policy = default_access_policy()
    allowed = policy.evaluate("scan", role="viewer", resource="note")
    assert allowed.decision == AccessDecision.ALLOW
    denied = policy.evaluate(
        "export",
        role="viewer",
        resource="export",
        context={"contains_secrets": True, "consent_export_sensitive": False},
    )
    assert denied.decision == AccessDecision.DENY
    assert denied.allowed is False
    assert "deny_sensitive_export_without_consent" in ":".join(denied.matched_rules)
    consented = evaluate_access(
        "export",
        role="owner",
        resource="report",
        context={"contains_secrets": True, "consent_export_sensitive": True},
    )
    assert consented.allowed is True

    custom = AccessPolicy(
        name="custom",
        default_decision=AccessDecision.REVIEW,
        rules=(
            PolicyRule(
                name="allow_admin",
                effect=PolicyEffect.ALLOW,
                actions=("admin.*",),
                roles=("admin",),
                priority=10,
            ),
            PolicyRule(
                name="deny_blocked",
                effect=PolicyEffect.DENY,
                actions=("admin.delete",),
                roles=("admin",),
                priority=5,
                reason="blocked",
            ),
        ),
    )
    engine = PolicyEngine([custom])
    assert engine.get_policy("custom") is custom
    assert engine.evaluate("admin.delete", role="admin").decision == AccessDecision.DENY
    assert engine.evaluate("admin.view", role="admin").decision == AccessDecision.ALLOW
    assert engine.evaluate("admin.view", role="user").decision == AccessDecision.REVIEW
    assert (
        engine.evaluate("admin.view", role="admin", policy_names=["missing"]).decision
        == AccessDecision.REVIEW
    )
    exported = custom.as_dict()
    assert exported["name"] == "custom"
    assert len(exported["rules"]) == 2
