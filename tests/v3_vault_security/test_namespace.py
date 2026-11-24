"""Tests for the V3 security namespace routes."""

from __future__ import annotations

import json

import pytest

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.clock import FixedClock
from redscribe.v3.namespaces import security as security_namespace
from redscribe.v3.vault_security.crypto import MIN_ITERATIONS, VaultKdfParams
from redscribe.v3.vault_security.service import VaultSecurityService

FAST = VaultKdfParams(iterations=MIN_ITERATIONS)
PASSPHRASE = "namespace setup passphrase 2026!"
ROTATED = "namespace rotation passphrase 2026!"


@pytest.fixture
def router() -> V3Router:
    candidate = V3Router()
    candidate.install_namespaces()
    security_namespace.set_service(VaultSecurityService(clock=FixedClock(2000.0)))
    return candidate


def test_namespace_discovery_registers_routes(router: V3Router) -> None:
    routes = {route.key for route in router.routes() if route.namespace == "security"}
    assert len(routes) == 14
    assert ("security", "status") in routes
    assert ("security", "recover") in routes
    assert "security" in router.namespaces()
    assert router.get("security", "posture") is not None
    assert router.get("security", "posture").public is True  # type: ignore[union-attr]


def test_status_and_posture_routes(router: V3Router) -> None:
    status = router.dispatch("security", "status")
    assert status["state"] == "uninitialized"
    assert status["initialized"] is False
    posture = router.dispatch("security", "posture")
    assert posture["contains_secrets"] is False
    assert posture["level"] in ("weak", "critical")


def test_setup_validation_and_conflict(router: V3Router) -> None:
    with pytest.raises(V3Error) as missing:
        router.dispatch("security", "setup", {})
    assert missing.value.code is V3ErrorCode.MISSING_FIELD
    with pytest.raises(V3Error) as invalid:
        router.dispatch("security", "setup", {"passphrase": PASSPHRASE, "recovery_count": 99})
    assert invalid.value.code is V3ErrorCode.INVALID_REQUEST
    result = router.dispatch(
        "security",
        "setup",
        {"passphrase": PASSPHRASE, "content": {"notes": []}, "recovery_count": 2},
    )
    assert len(result["recovery_codes"]) == 2
    with pytest.raises(V3Error) as conflict:
        router.dispatch("security", "setup", {"passphrase": ROTATED})
    assert conflict.value.code is V3ErrorCode.CONFLICT


def test_unlock_rotate_and_recovery_routes(router: V3Router) -> None:
    router.dispatch("security", "setup", {"passphrase": PASSPHRASE, "recovery_count": 2})
    with pytest.raises(V3Error) as wrong:
        router.dispatch("security", "unlock", {"passphrase": "wrong passphrase here"})
    assert wrong.value.code is V3ErrorCode.FORBIDDEN
    assert "wrong passphrase here" not in json.dumps(wrong.value.envelope().as_dict())
    unlocked = router.dispatch("security", "unlock", {"passphrase": PASSPHRASE})
    assert unlocked["state"] == "unlocked"
    rotated = router.dispatch("security", "rotate", {"new_passphrase": ROTATED})
    assert rotated["to_version"] == 2
    locked = router.dispatch("security", "lock")
    assert locked["state"] == "locked"
    router.dispatch("security", "unlock", {"passphrase": ROTATED})
    issued = router.dispatch("security", "recovery_issue", {"passphrase": ROTATED, "count": 1})
    assert len(issued["recovery_codes"]) == 1
    recovered = router.dispatch(
        "security",
        "recover",
        {"code": issued["recovery_codes"][0], "new_passphrase": PASSPHRASE},
    )
    assert recovered["key_id"]
    with pytest.raises(V3Error) as replay:
        router.dispatch(
            "security",
            "recover",
            {"code": issued["recovery_codes"][0], "new_passphrase": ROTATED},
        )
    assert replay.value.code is V3ErrorCode.FORBIDDEN


def test_policy_routes(router: V3Router) -> None:
    current = router.dispatch("security", "policy_get")
    assert len(current["patterns"]) >= 5
    with pytest.raises(V3Error) as invalid_scope:
        router.dispatch("security", "policy_preview", {"text": "x", "scope": "everything"})
    assert invalid_scope.value.code is V3ErrorCode.INVALID_REQUEST
    preview = router.dispatch(
        "security",
        "policy_preview",
        {"text": "password: hunter2secret", "scope": "log_content"},
    )
    assert preview["decision"]["allowed"] is True
    assert "hunter2secret" not in preview["preview"]["text"]
    updated = router.dispatch(
        "security",
        "policy_update",
        {
            "rules": [
                {
                    "rule_id": "remove-all",
                    "pattern": "*",
                    "mode": "remove",
                    "priority": 9,
                }
            ],
            "grants": ["export_plaintext"],
        },
    )
    assert updated["rules"][0]["rule_id"] == "remove-all"
    assert updated["consents"]["granted"] == ["export_plaintext"]
    with pytest.raises(V3Error) as bad_rules:
        router.dispatch("security", "policy_update", {"rules": "nope"})
    assert bad_rules.value.code is V3ErrorCode.INVALID_REQUEST


def test_audit_routes_and_manifest(router: V3Router) -> None:
    router.dispatch("security", "setup", {"passphrase": PASSPHRASE, "recovery_count": 1})
    listed = router.dispatch("security", "audit_list", {"limit": 5})
    assert listed["total"] >= 1
    assert listed["entries"][0]["action"] == "vault.setup"
    exported = router.dispatch("security", "audit_export", {"format": "json"})
    assert PASSPHRASE not in exported["document"]
    with pytest.raises(V3Error) as bad_format:
        router.dispatch("security", "audit_export", {"format": "pdf"})
    assert bad_format.value.code is V3ErrorCode.INVALID_REQUEST
    events = router.dispatch("security", "events")
    assert any(event["kind"] == "vault.setup" for event in events["events"])
    manifest = router.manifest()
    assert "/api/v3/security/status" in [route["path"] for route in manifest["routes"]]
