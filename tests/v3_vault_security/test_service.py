"""Tests for the complete vault security service lifecycle."""

from __future__ import annotations

import json

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.vault_security.audit import AuditAction, AuditOutcome
from redscribe.v3.vault_security.crypto import MIN_ITERATIONS, VaultKdfParams
from redscribe.v3.vault_security.policy import (
    ConsentScope,
    PolicyRule,
    RedactionMode,
)
from redscribe.v3.vault_security.recovery import RecoveryCodeError
from redscribe.v3.vault_security.service import (
    InvalidPassphraseError,
    VaultAlreadyInitializedError,
    VaultLockedError,
    VaultNotInitializedError,
    VaultSecurityError,
    VaultSecurityService,
    VaultState,
    parse_scope,
)

FAST = VaultKdfParams(iterations=MIN_ITERATIONS)
PASSPHRASE = "a very long setup passphrase 2026!"
ROTATED = "another very long passphrase 2026!"
RECOVERED = "a recovery replacement passphrase 2026!"


def build(content: dict[str, object] | None = None) -> VaultSecurityService:
    service = VaultSecurityService(vault_id="case-9", clock=FixedClock(1000.0))
    service.setup(
        PASSPHRASE,
        content=content or {"notes": [{"id": "n1", "title": "first"}], "count": 1},
        recovery_count=3,
        params=FAST,
    )
    return service


def test_fresh_vault_requires_setup() -> None:
    service = VaultSecurityService(clock=FixedClock(1000.0))
    assert service.state is VaultState.UNINITIALIZED
    assert service.is_initialized is False
    assert service.status()["initialized"] is False
    assert service.posture().warnings == ("Vault encryption has not been configured",)
    with pytest.raises(VaultNotInitializedError, match="not configured"):
        service.unlock(PASSPHRASE)
    with pytest.raises(VaultNotInitializedError, match="not configured"):
        service.rotate(ROTATED)
    with pytest.raises(VaultLockedError, match="locked"):
        service.content()


def test_setup_is_locked_and_secret_free() -> None:
    service = VaultSecurityService(clock=FixedClock(1000.0))
    result = service.setup(
        PASSPHRASE,
        content={"notes": [{"id": "n1"}]},
        recovery_count=4,
        params=FAST,
        request_id="req-setup",
    )
    assert len(result.recovery_codes) == 4
    assert service.state is VaultState.LOCKED
    assert service.is_initialized is True
    assert service.seal is not None
    assert PASSPHRASE not in service.seal.to_json()
    assert PASSPHRASE not in json.dumps(service.status())
    assert result.as_dict()["recovery_codes"] == list(result.recovery_codes)
    with pytest.raises(VaultAlreadyInitializedError, match="already configured"):
        service.setup(ROTATED, params=FAST)
    with pytest.raises(VaultLockedError, match="locked"):
        service.content()


def test_wrong_key_refusal_is_audited() -> None:
    service = build()
    with pytest.raises(InvalidPassphraseError, match="verification failed"):
        service.unlock("a completely wrong passphrase", request_id="req-bad")
    assert service.state is VaultState.LOCKED
    denied = [
        entry
        for entry in service.audit_list()["entries"]
        if entry["outcome"] == AuditOutcome.DENIED.value
    ]
    assert len(denied) == 1
    assert denied[0]["action"] == AuditAction.ACCESS_DENIED.value
    assert "a completely wrong passphrase" not in json.dumps(denied)


def test_unlock_lock_and_content_updates() -> None:
    service = build()
    unlocked = service.unlock(PASSPHRASE, request_id="req-ok")
    assert unlocked.state is VaultState.UNLOCKED
    assert unlocked.version == 1
    content = service.content()
    assert content["count"] == 1
    content["count"] = 999
    assert service.content()["count"] == 1
    service.replace_content({"notes": [], "count": 2}, request_id="req-update")
    assert service.content()["count"] == 2
    locked = service.lock(request_id="req-lock")
    assert locked.state is VaultState.LOCKED
    with pytest.raises(VaultLockedError, match="locked"):
        service.content()
    assert service.unlock(PASSPHRASE).state is VaultState.UNLOCKED
    assert service.content()["count"] == 2


def test_rotation_preserves_data_and_invalidates_old_codes() -> None:
    service = build({"notes": [{"id": "keep"}], "count": 7})
    old_codes = service.unlock(PASSPHRASE).state
    assert old_codes is VaultState.UNLOCKED
    old_recovery = service.audit_list()["entries"][0]
    assert old_recovery["action"] == AuditAction.SETUP.value
    rotated = service.rotate(ROTATED, params=FAST, request_id="req-rotate")
    assert rotated.plan.from_version == 1
    assert rotated.plan.to_version == 2
    assert len(rotated.recovery_codes) == 3
    assert service.content()["count"] == 7
    assert service.status()["rotation_count"] == 1
    assert service.status()["active_key_id"] != ""
    assert service.unlock(ROTATED).state is VaultState.UNLOCKED
    service.lock()
    with pytest.raises(InvalidPassphraseError):
        service.unlock(PASSPHRASE)
    service.unlock(ROTATED)
    with pytest.raises(VaultSecurityError, match="differ"):
        service.rotate(ROTATED)
    service.lock()
    with pytest.raises(VaultLockedError, match="locked"):
        service.rotate(RECOVERED)


def test_recovery_code_single_use_and_rekey() -> None:
    service = build({"notes": [{"id": "recover-me"}], "count": 5})
    codes = service.audit_list({"actions": ["vault.setup"]})
    assert len(codes["entries"]) >= 1
    issued = service.issue_recovery_codes(PASSPHRASE, count=2, request_id="req-codes")
    assert len(issued) == 2
    with pytest.raises(InvalidPassphraseError):
        service.issue_recovery_codes("wrong passphrase here")
    recovery = service.recover(issued[0], RECOVERED, request_id="req-recover")
    assert recovery.remaining_active == 1
    assert len(recovery.recovery_codes) == 2
    assert service.state is VaultState.LOCKED
    assert service.unlock(RECOVERED).state is VaultState.UNLOCKED
    assert service.content()["count"] == 5
    service.lock()
    with pytest.raises(InvalidPassphraseError):
        service.unlock(PASSPHRASE)
    with pytest.raises(RecoveryCodeError, match="not recognized"):
        service.recover(issued[0], PASSPHRASE)


def test_recovery_rejects_unknown_code() -> None:
    service = build()
    with pytest.raises(RecoveryCodeError, match="not recognized"):
        service.recover("RS-ZZZZZ-ZZZZZ-ZZZZZ", RECOVERED)
    denied = [
        entry
        for entry in service.audit_list()["entries"]
        if entry["outcome"] == AuditOutcome.DENIED.value
    ]
    assert denied
    assert denied[0]["detail"]["reason"] == "recovery_code_rejected"


def test_policy_preview_and_update() -> None:
    service = build()
    sample = "password: hunter2secret"
    preview = service.preview_policy(sample, ConsentScope.EXPORT_PLAINTEXT)
    assert preview["decision"]["allowed"] is False
    assert "hunter2secret" not in preview["preview"]["text"]
    service.update_policy(
        rules=(
            PolicyRule(
                rule_id="custom-remove",
                pattern_name="assigned_password",
                mode=RedactionMode.REMOVE,
                priority=9,
            ).as_dict(),
        ),
        grants=(ConsentScope.EXPORT_PLAINTEXT,),
        actor="operator",
        request_id="req-policy",
    )
    assert service.policy_snapshot()["consents"]["granted"] == ["export_plaintext"]
    allowed = service.preview_policy(sample, ConsentScope.EXPORT_PLAINTEXT)
    assert allowed["decision"]["allowed"] is True
    assert "hunter2secret" not in allowed["preview"]["text"]
    service.update_policy(revocations=(ConsentScope.EXPORT_PLAINTEXT,))
    assert service.policy_snapshot()["consents"]["granted"] == []


def test_audit_export_is_redacted_and_secret_free() -> None:
    service = build()
    service.unlock(PASSPHRASE)
    service.preview_policy("password: hunter2secret", ConsentScope.LOG_CONTENT)
    document = service.audit_export(fmt="json", request_id="req-export")
    assert "hunter2secret" not in document
    assert PASSPHRASE not in document
    assert json.loads(document)["count"] >= 1
    jsonl = service.audit_export(fmt="jsonl")
    assert PASSPHRASE not in jsonl
    with pytest.raises(ValueError, match="format"):
        service.audit_export(fmt="csv")


def test_posture_and_events_never_expose_secrets() -> None:
    service = build()
    service.unlock(PASSPHRASE)
    service.rotate(ROTATED, params=FAST)
    report = service.posture()
    assert report.contains_secrets is False
    rendered = json.dumps(
        {
            "status": service.status(),
            "posture": report.as_dict(),
            "events": service.events(),
            "audit": service.audit_list()["entries"],
            "policy": service.policy_snapshot(),
        }
    )
    for secret in (PASSPHRASE, ROTATED, "hunter2secret"):
        assert secret not in rendered
    assert service.status()["state"] == "unlocked"
    assert any(event["kind"] == "vault.rotate" for event in service.events())


def test_input_validation_messages_do_not_echo_secrets() -> None:
    service = VaultSecurityService(clock=FixedClock(1.0))
    with pytest.raises(VaultSecurityError, match="at least 12"):
        service.setup("short")
    service.setup(PASSPHRASE, params=FAST, recovery_count=1)
    with pytest.raises(ValueError, match="between 1 and 8"):
        service.issue_recovery_codes(PASSPHRASE, count=99)
    with pytest.raises(InvalidPassphraseError, match="verification failed"):
        service.unlock("short")
    assert "short" not in json.dumps(service.events())


def test_scope_parsing() -> None:
    from redscribe.v3.vault_security.policy import PolicyError

    assert parse_scope("log_content") is ConsentScope.LOG_CONTENT
    with pytest.raises(PolicyError, match="Unknown consent scope"):
        parse_scope("everything")
