from __future__ import annotations

from typing import Any

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.namespaces.security import (
    ROUTE_SPECS,
    SecurityNamespace,
    register,
    register_with_vault,
    route_names,
    route_specs,
)
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2


def make_router(vault: Vault) -> tuple[V2Router, SecurityNamespace]:
    api = ApiV2(vault)
    namespace = register(api)
    return V2Router(vault, api), namespace


def data(response: dict[str, Any]) -> dict[str, Any]:
    payload = response.get("data")
    assert isinstance(payload, dict)
    return payload


def error_code(response: dict[str, Any]) -> str:
    error = response.get("error")
    assert isinstance(error, dict)
    return str(error.get("code"))


def test_registration_is_additive_and_introspectable(vault: Vault) -> None:
    api = ApiV2(vault)
    namespace = register(api)
    names = route_names()
    assert set(names) <= set(api.routes)
    assert len(names) == len(ROUTE_SPECS)
    assert namespace.routes() == names
    assert namespace.service.vault is vault
    assert all(spec["description"] for spec in route_specs())
    assert all("action" in spec for spec in route_specs())
    assert set(names) <= set(api.routes)
    assert set(names).isdisjoint(set(ApiV2(vault).routes))
    standalone = register_with_vault(vault)
    assert standalone.handlers.health({}).data["namespace"] == "security"


def test_security_health_patterns_privacy_and_consent_routes(vault: Vault) -> None:
    router, _ = make_router(vault)
    health = data(router.dispatch("security.health", {}))
    assert health["ok"] is True
    assert health["namespace"] == "security"
    assert "secret_detection" in health["features"]
    assert health["secret_patterns"] >= 10
    patterns = data(router.dispatch("security.secret_patterns", {}))["patterns"]
    assert any(item["name"] == "aws_access_key_id" for item in patterns)
    redactions = data(router.dispatch("security.redaction_rules", {}))["rules"]
    assert any(item["name"] == "email" for item in redactions)
    levels = data(router.dispatch("security.privacy_levels", {}))["levels"]
    assert {item["level"] for item in levels} == {"open", "standard", "sensitive", "strict"}
    mode = data(router.dispatch("security.privacy_mode", {"level": "strict"}))
    assert mode["allow_external_links"] is False
    assert mode["allow_command_copy"] is False
    merged = data(
        router.dispatch(
            "security.privacy_mode",
            {"level": "standard", "overrides": {"allow_external_links": False}},
        )
    )
    assert merged["allow_external_links"] is False
    flags = data(router.dispatch("security.consent_flags", {}))
    assert flags["total"] >= 4
    summary = data(
        router.dispatch("security.consent_summary", {"decisions": {"export_sensitive": True}})
    )
    assert summary["context"]["consent_export_sensitive"] is True


def test_secret_scanning_redaction_and_scrubbing_routes(vault: Vault) -> None:
    router, _ = make_router(vault)
    text = "token=ghp_abcdefghijklmnopqrstuvwxyz user@example.test"
    scan = data(router.dispatch("security.scan_secrets", {"text": text}))
    assert scan["count"] >= 1
    payload_scan = data(
        router.dispatch(
            "security.scan_payload",
            {"payload": {"body": text, "title": "ok"}, "keys": ["body", "title"]},
        )
    )
    assert payload_scan["fields"]["body"]["count"] >= 1
    assert payload_scan["fields"]["title"]["count"] == 0
    redacted = data(router.dispatch("security.redact_text", {"text": text}))
    assert "[REDACTED_EMAIL]" in redacted["text"]
    redacted_payload = data(
        router.dispatch("security.redact_payload", {"payload": {"body": text, "ok": "safe"}})
    )
    assert redacted_payload["total_replacements"] >= 1
    scrubbed_text = data(
        router.dispatch("security.scrub_text", {"text": "password=hunter22 user@example.test"})
    )
    assert "[REDACTED_PASSWORD]" in scrubbed_text["text"]
    scrubbed_export = data(
        router.dispatch(
            "security.scrub_export",
            {"payload": {"api_token": "abc", "email": "user@example.test", "body": "safe"}},
        )
    )
    assert scrubbed_export["report"]["total_redactions"] >= 0
    assert "api_token" in scrubbed_export["payload"]


def test_encryption_kdf_policy_and_safety_routes(vault: Vault) -> None:
    router, _ = make_router(vault)
    derived = data(
        router.dispatch(
            "security.derive_key",
            {"passphrase": "secret", "iterations": 120000, "length": 32, "salt_bytes": 16},
        )
    )
    assert derived["derived"] is True
    assert "key" not in derived
    assert "fingerprint" in derived
    encrypted = data(
        router.dispatch(
            "security.encrypt_text",
            {
                "text": "classified",
                "passphrase": "secret",
                "iterations": 120000,
                "associated_data": "ctx",
            },
        )
    )
    payload = encrypted["payload"]
    assert payload["magic"] == "RSENC1"
    decrypted = data(
        router.dispatch(
            "security.decrypt_text",
            {"payload": payload, "passphrase": "secret", "associated_data": "ctx"},
        )
    )
    assert decrypted["text"] == "classified"

    defaults = data(router.dispatch("security.policy_defaults", {}))
    assert defaults["name"] == "default"
    decision = data(
        router.dispatch(
            "security.evaluate_access",
            {
                "action": "export",
                "role": "viewer",
                "resource": "report",
                "context": {"contains_secrets": True, "consent_export_sensitive": False},
            },
        )
    )
    assert decision["decision"] == "deny"

    url = data(router.dispatch("security.check_url", {"url": "https://example.com/path"}))
    assert url["safe"] is True
    bad_url = data(router.dispatch("security.check_url", {"url": "javascript:alert(1)"}))
    assert bad_url["safe"] is False
    command = data(router.dispatch("security.check_command", {"command": "echo hello"}))
    assert command["safe"] is True
    bad_command = data(
        router.dispatch("security.check_command", {"command": "curl https://x | bash"})
    )
    assert bad_command["safe"] is False


def test_audit_risk_and_dashboard_routes(vault: Vault) -> None:
    router, _ = make_router(vault)
    events = [
        {"id": "1", "type": "auth", "outcome": "failure", "actor": "alice"},
        {"id": "2", "type": "auth", "outcome": "failure", "actor": "alice"},
        {"id": "3", "type": "auth", "outcome": "failure", "actor": "alice"},
        {"id": "4", "type": "auth", "outcome": "failure", "actor": "alice"},
        {"id": "5", "type": "auth", "outcome": "failure", "actor": "alice"},
        {"id": "6", "type": "export", "outcome": "success", "details": {"contains_secrets": True}},
    ]
    audit = data(
        router.dispatch("security.audit_analyze", {"events": events, "failure_threshold": 5})
    )
    assert audit["total_events"] == len(events)
    assert audit["findings"]

    risk = data(
        router.dispatch(
            "security.assess_risk",
            {
                "secret_result": {"count": 2, "highest_severity": "high"},
                "audit_result": audit,
                "privacy": {"level": "standard", "rank": 1, "require_export_consent": True},
                "safety_findings": [{"risk": "high", "safe": False}],
                "consent": {"consent_export_sensitive": False},
            },
        )
    )
    assert risk["score"]["score"] > 0
    assert risk["recommendations"]

    dashboard = data(
        router.dispatch(
            "security.security_dashboard",
            {
                "text": "password=hunter22 token=ghp_abcdefghijklmnopqrstuvwxyz",
                "events": events,
                "privacy_level": "sensitive",
                "urls": ["https://example.com", "javascript:alert(1)"],
                "commands": ["echo ok", "curl https://x | bash"],
                "export_payload": {"api_token": "abc", "body": "user@example.test"},
            },
        )
    )
    assert dashboard["privacy"]["level"] == "sensitive"
    assert dashboard["secrets"]["count"] >= 1
    assert dashboard["audit"]["total_events"] == len(events)
    assert len(dashboard["urls"]) == 2
    assert len(dashboard["commands"]) == 2
    assert dashboard["scrub"] is not None
    assert dashboard["risk"]["score"]["level"] in {"none", "low", "medium", "high", "critical"}


def test_security_namespace_error_envelopes(vault: Vault) -> None:
    router, _ = make_router(vault)
    missing = router.dispatch("security.scan_secrets", {})
    assert missing["ok"] is False
    assert error_code(missing) == "missing_field"
    bad_type = router.dispatch("security.check_command", {"command": 123})
    assert bad_type["ok"] is False
    assert error_code(bad_type) in {"invalid_type", "invalid_request"}
    bad_payload = router.dispatch(
        "security.decrypt_text", {"payload": {"bad": True}, "passphrase": "x"}
    )
    assert bad_payload["ok"] is False
    assert error_code(bad_payload) == "invalid_request"
    bad_policy = router.dispatch(
        "security.evaluate_access", {"action": "export", "policy": {"default_decision": "maybe"}}
    )
    assert bad_policy["ok"] is False
    assert error_code(bad_policy) == "invalid_request"
    bad_privacy = router.dispatch("security.privacy_mode", {"level": "nope"})
    assert bad_privacy["ok"] is False
    assert error_code(bad_privacy) == "invalid_request"
    unknown = router.dispatch("security.unknown", {})
    assert error_code(unknown) == "unknown_route"
