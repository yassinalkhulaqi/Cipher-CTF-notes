"""Vault security service: the complete encryption lifecycle.

This service wires together encryption, key rotation, single-use recovery,
policy, audit, and posture scoring. It reuses the B00 entity and event
contracts and emits only redacted, secret-free event payloads.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.types import ENTITY_EVIDENCE, EntityRef
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.types import make_event
from redscribe.v3.vault_security.audit import (
    AuditAction,
    AuditOutcome,
    AuditTrail,
    parse_audit_filter,
)
from redscribe.v3.vault_security.crypto import (
    VaultIntegrityError,
    VaultKdfParams,
    VaultSeal,
    decrypt_vault,
    encrypt_vault,
    seal_json,
    unseal_json,
)
from redscribe.v3.vault_security.keyring import KeyRing, KeyRingError, RotationPlan
from redscribe.v3.vault_security.policy import (
    ConsentScope,
    PolicyEngine,
    PolicyError,
    default_policy,
)
from redscribe.v3.vault_security.posture import (
    PostureReport,
    assert_secret_free,
    score_posture,
)
from redscribe.v3.vault_security.recovery import (
    RecoveryCodeError,
    RecoveryCodeStore,
    normalize_code,
)

MIN_PASSPHRASE_LENGTH = 12
MAX_RECOVERY_CODES = 8
DEFAULT_RECOVERY_CODES = 6
RECOVERY_AUDIT_LIMIT = 200


class VaultState(str, Enum):
    """Lifecycle state of the vault security service."""

    UNINITIALIZED = "uninitialized"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class VaultSecurityError(Exception):
    """Base error for the vault security lifecycle."""


class VaultNotInitializedError(VaultSecurityError):
    """Raised when an operation requires a configured vault."""


class VaultAlreadyInitializedError(VaultSecurityError):
    """Raised when setup is attempted twice."""


class VaultLockedError(VaultSecurityError):
    """Raised when an operation requires an unlocked vault."""


class InvalidPassphraseError(VaultSecurityError):
    """Raised when a passphrase cannot be verified."""


@dataclass(frozen=True, slots=True)
class SetupResult:
    """Result of initializing vault encryption."""

    vault_id: str
    key_id: str
    created_at: float
    recovery_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation including the one-time codes."""
        return {
            "vault_id": self.vault_id,
            "key_id": self.key_id,
            "created_at": self.created_at,
            "recovery_codes": list(self.recovery_codes),
        }


@dataclass(frozen=True, slots=True)
class UnlockResult:
    """Result of a successful unlock."""

    state: VaultState
    key_id: str
    version: int
    unlocked_at: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "state": self.state.value,
            "key_id": self.key_id,
            "version": self.version,
            "unlocked_at": self.unlocked_at,
        }


@dataclass(frozen=True, slots=True)
class LockResult:
    """Result of locking the vault."""

    state: VaultState
    locked_at: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"state": self.state.value, "locked_at": self.locked_at}


@dataclass(frozen=True, slots=True)
class RotationResult:
    """Result of rotating the passphrase and invalidating old recovery codes."""

    plan: RotationPlan
    rotated_at: float
    recovery_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload = self.plan.as_dict()
        payload.update({"rotated_at": self.rotated_at, "recovery_codes": list(self.recovery_codes)})
        return payload


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Result of recovering a vault with a single-use code."""

    code_id: str
    key_id: str
    redeemed_at: float
    remaining_active: int
    recovery_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "code_id": self.code_id,
            "key_id": self.key_id,
            "redeemed_at": self.redeemed_at,
            "remaining_active": self.remaining_active,
            "recovery_codes": list(self.recovery_codes),
        }


@dataclass(slots=True)
class VaultSecurityService:
    """Coordinate every stage of the vault security lifecycle."""

    vault_id: str = "primary"
    clock: Clock = field(default_factory=SystemClock)
    policy: PolicyEngine = field(default_factory=default_policy)
    bus: EventBus = field(default_factory=EventBus)
    _keyring: KeyRing = field(default_factory=lambda: KeyRing("primary"), repr=False)
    _recovery: RecoveryCodeStore = field(default_factory=RecoveryCodeStore, repr=False)
    _audit: AuditTrail = field(default_factory=AuditTrail, repr=False)
    _seal: VaultSeal | None = field(default=None, repr=False)
    _content: dict[str, Any] = field(default_factory=dict, repr=False)
    _escrows: dict[str, VaultSeal] = field(default_factory=dict, repr=False)
    _state: VaultState = VaultState.UNINITIALIZED
    _created_at: float = 0.0

    def __post_init__(self) -> None:
        self._keyring = KeyRing(self.vault_id)
        self._audit = AuditTrail(
            clock=self.clock,
            text_redactor=lambda value: self.policy.redact(value).text,
        )

    def __repr__(self) -> str:
        return f"VaultSecurityService(vault_id={self.vault_id!r}, state={self._state.value})"

    @property
    def state(self) -> VaultState:
        """Current lock state."""
        return self._state

    @property
    def seal(self) -> VaultSeal | None:
        """Current encrypted seal, if initialized."""
        return self._seal

    @property
    def is_initialized(self) -> bool:
        """Whether encryption has been configured."""
        return self._seal is not None

    def setup(
        self,
        passphrase: str,
        *,
        content: Mapping[str, Any] | None = None,
        recovery_count: int = DEFAULT_RECOVERY_CODES,
        params: VaultKdfParams | None = None,
        request_id: str = "",
    ) -> SetupResult:
        """Initialize encryption, issue recovery codes, and start locked."""
        if self._seal is not None:
            raise VaultAlreadyInitializedError("Vault encryption is already configured")
        _validate_passphrase(passphrase)
        _validate_code_count(recovery_count)
        now = self.clock.now_timestamp()
        descriptor = self._keyring.install(passphrase, created_at=now, params=params)
        payload = copy.deepcopy(dict(content or {}))
        payload.setdefault("vault_id", self.vault_id)
        payload.setdefault("created_at", now)
        payload.setdefault("notes", [])
        self._seal = seal_json(payload, passphrase, params=params, vault_id=self.vault_id)
        self._content = {}
        self._created_at = now
        codes = self._replacement_recovery(passphrase, count=recovery_count, now=now)
        self._state = VaultState.LOCKED
        self._keyring.lock()
        self._audit.record(
            AuditAction.SETUP,
            actor="local",
            subject=self.vault_id,
            detail={"key_id": descriptor.key_id, "recovery_issued": len(codes)},
            request_id=request_id,
            timestamp=now,
        )
        self._publish(
            "vault.setup",
            key_id=descriptor.key_id,
            key_version=descriptor.version,
            recovery_issued=len(codes),
        )
        return SetupResult(
            vault_id=self.vault_id,
            key_id=descriptor.key_id,
            created_at=now,
            recovery_codes=codes,
        )

    def unlock(self, passphrase: str, *, request_id: str = "") -> UnlockResult:
        """Verify the passphrase, open the seal, and expose content in memory."""
        self._require_initialized()
        if not self._keyring.unlock(passphrase):
            self._keyring.lock()
            self._audit.record(
                AuditAction.ACCESS_DENIED,
                actor="local",
                subject=self.vault_id,
                outcome=AuditOutcome.DENIED,
                detail={"reason": "passphrase_verification_failed"},
                request_id=request_id,
            )
            self._publish("vault.access.denied", reason="passphrase_verification_failed")
            raise InvalidPassphraseError("Passphrase verification failed")
        try:
            assert self._seal is not None
            decoded = unseal_json(self._seal, passphrase, vault_id=self.vault_id)
        except (VaultIntegrityError, ValueError):
            self._keyring.lock()
            self._state = VaultState.LOCKED
            self._audit.record(
                AuditAction.ACCESS_DENIED,
                actor="local",
                subject=self.vault_id,
                outcome=AuditOutcome.DENIED,
                detail={"reason": "seal_authentication_failed"},
                request_id=request_id,
            )
            raise VaultSecurityError("Vault seal could not be authenticated") from None
        self._content = decoded
        self._state = VaultState.UNLOCKED
        active = self._keyring.active()
        assert active is not None
        now = self.clock.now_timestamp()
        self._audit.record(
            AuditAction.UNLOCK,
            actor="local",
            subject=self.vault_id,
            detail={"key_id": active.key_id, "key_version": active.version},
            request_id=request_id,
            timestamp=now,
        )
        self._publish("vault.unlock", key_id=active.key_id, key_version=active.version)
        return UnlockResult(
            state=self._state,
            key_id=active.key_id,
            version=active.version,
            unlocked_at=now,
        )

    def lock(self, *, request_id: str = "") -> LockResult:
        """Forget all plaintext content and key material."""
        now = self.clock.now_timestamp()
        was_unlocked = self._state is VaultState.UNLOCKED
        self._content = {}
        self._keyring.lock()
        self._state = VaultState.LOCKED
        if was_unlocked:
            self._audit.record(
                AuditAction.LOCK,
                actor="local",
                subject=self.vault_id,
                detail={"content_cleared": True},
                request_id=request_id,
                timestamp=now,
            )
            self._publish("vault.lock", reason="user_action")
        return LockResult(state=self._state, locked_at=now)

    def require_unlocked(self) -> None:
        """Raise unless the vault is unlocked."""
        if self._state is not VaultState.UNLOCKED or not self._keyring.is_unlocked:
            raise VaultLockedError("Vault is locked")

    def content(self) -> dict[str, Any]:
        """Return a defensive copy of unlocked vault content."""
        self.require_unlocked()
        return copy.deepcopy(self._content)

    def replace_content(self, payload: Mapping[str, Any], *, request_id: str = "") -> VaultSeal:
        """Replace vault content and re-seal it with the active passphrase."""
        self.require_unlocked()
        passphrase = self._keyring.current_passphrase()
        self._content = copy.deepcopy(dict(payload))
        self._seal = seal_json(self._content, passphrase, vault_id=self.vault_id)
        self._audit.record(
            AuditAction.SETUP,
            actor="local",
            subject=self.vault_id,
            detail={"reason": "content_resealed", "field_count": len(self._content)},
            request_id=request_id,
        )
        self._publish("vault.content.updated", field_count=len(self._content))
        assert self._seal is not None
        return self._seal

    def rotate(
        self,
        new_passphrase: str,
        *,
        params: VaultKdfParams | None = None,
        request_id: str = "",
    ) -> RotationResult:
        """Rotate the key, re-seal content, and replace recovery material."""
        self._require_initialized()
        self.require_unlocked()
        _validate_passphrase(new_passphrase)
        now = self.clock.now_timestamp()
        old_passphrase = self._keyring.current_passphrase()
        if new_passphrase == old_passphrase:
            raise VaultSecurityError("New passphrase must differ from the current one")
        try:
            plan = self._keyring.rotate(new_passphrase, created_at=now, params=params)
            active = self._keyring.active()
            assert active is not None
            self._seal = seal_json(
                self._content,
                new_passphrase,
                params=active.params,
                vault_id=self.vault_id,
            )
        except KeyRingError as error:
            raise VaultSecurityError("Key rotation could not be completed") from error
        codes = self._replacement_recovery(
            new_passphrase, count=len(self._recovery.records()), now=now
        )
        self._audit.record(
            AuditAction.ROTATE,
            actor="local",
            subject=self.vault_id,
            detail={
                "from_key_id": plan.from_key_id,
                "to_key_id": plan.to_key_id,
                "recovery_replaced": len(codes),
            },
            request_id=request_id,
            timestamp=now,
        )
        self._publish(
            "vault.rotate",
            from_key_id=plan.from_key_id,
            to_key_id=plan.to_key_id,
            recovery_replaced=len(codes),
        )
        return RotationResult(plan=plan, rotated_at=now, recovery_codes=codes)

    def issue_recovery_codes(
        self,
        passphrase: str,
        *,
        count: int = DEFAULT_RECOVERY_CODES,
        request_id: str = "",
    ) -> tuple[str, ...]:
        """Issue a fresh recovery batch after verifying the passphrase."""
        self._require_initialized()
        _validate_code_count(count)
        if not self._keyring.verify(passphrase):
            self._audit.record(
                AuditAction.ACCESS_DENIED,
                actor="local",
                subject=self.vault_id,
                outcome=AuditOutcome.DENIED,
                detail={"reason": "recovery_issue_passphrase_failed"},
                request_id=request_id,
            )
            raise InvalidPassphraseError("Passphrase verification failed")
        now = self.clock.now_timestamp()
        codes = self._replacement_recovery(passphrase, count=count, now=now)
        self._audit.record(
            AuditAction.RECOVERY_ISSUE,
            actor="local",
            subject=self.vault_id,
            detail={"recovery_issued": len(codes)},
            request_id=request_id,
            timestamp=now,
        )
        self._publish("vault.recovery.issued", recovery_issued=len(codes))
        return codes

    def recover(
        self,
        code: str,
        new_passphrase: str,
        *,
        request_id: str = "",
    ) -> RecoveryResult:
        """Redeem a single-use code and re-key a locked vault."""
        self._require_initialized()
        _validate_passphrase(new_passphrase)
        now = self.clock.now_timestamp()
        record = self._recovery.lookup(code)
        if record is None:
            self._audit.record(
                AuditAction.ACCESS_DENIED,
                actor="local",
                subject=self.vault_id,
                outcome=AuditOutcome.DENIED,
                detail={"reason": "recovery_code_rejected"},
                request_id=request_id,
                timestamp=now,
            )
            self._publish("vault.access.denied", reason="recovery_code_rejected")
            raise RecoveryCodeError("Recovery code is not recognized")
        escrow = self._escrows.get(record.code_id)
        if escrow is None:
            raise RecoveryCodeError("Recovery material is unavailable")
        redemption = self._recovery.redeem(code, now=now)
        try:
            old_passphrase = decrypt_vault(
                escrow,
                normalize_code(code),
                vault_id=f"recovery-{record.code_id}",
            ).decode("utf-8")
            assert self._seal is not None
            recovered = unseal_json(self._seal, old_passphrase, vault_id=self.vault_id)
        except (VaultIntegrityError, UnicodeDecodeError, ValueError):
            self._audit.record(
                AuditAction.RECOVERY_REDEEM,
                actor="local",
                subject=self.vault_id,
                outcome=AuditOutcome.FAILURE,
                detail={"reason": "recovery_material_invalid", "code_id": record.code_id},
                request_id=request_id,
                timestamp=now,
            )
            raise VaultSecurityError("Recovery material could not be authenticated") from None
        descriptor = self._keyring.reset(new_passphrase, created_at=now)
        active = self._keyring.active()
        assert active is not None
        self._content = recovered
        self._seal = seal_json(
            recovered, new_passphrase, params=active.params, vault_id=self.vault_id
        )
        codes = self._replacement_recovery(
            new_passphrase, count=len(self._recovery.records()), now=now
        )
        self._state = VaultState.LOCKED
        self._content = {}
        self._keyring.lock()
        self._audit.record(
            AuditAction.RECOVERY_REDEEM,
            actor="local",
            subject=self.vault_id,
            detail={
                "code_id": record.code_id,
                "key_id": descriptor.key_id,
                "recovery_replaced": len(codes),
            },
            request_id=request_id,
            timestamp=now,
        )
        self._publish(
            "vault.recovery.redeemed",
            code_id=record.code_id,
            key_id=descriptor.key_id,
            recovery_replaced=len(codes),
        )
        return RecoveryResult(
            code_id=record.code_id,
            key_id=descriptor.key_id,
            redeemed_at=now,
            remaining_active=redemption.remaining_active,
            recovery_codes=codes,
        )

    def update_policy(
        self,
        *,
        rules: tuple[Mapping[str, Any], ...] = (),
        grants: tuple[ConsentScope, ...] = (),
        revocations: tuple[ConsentScope, ...] = (),
        actor: str = "local",
        request_id: str = "",
    ) -> dict[str, Any]:
        """Replace redaction rules and consent grants atomically."""
        rule_count = self.policy.replace_all(rules)
        now = self.clock.now_timestamp()
        for scope in grants:
            self.policy.consents.grant(scope, actor=actor, at=now)
        for scope in revocations:
            self.policy.consents.revoke(scope)
        self._audit.record(
            AuditAction.POLICY_UPDATE,
            actor=actor,
            subject=self.vault_id,
            detail={"rule_count": rule_count, "grants": [scope.value for scope in grants]},
            request_id=request_id,
            timestamp=now,
        )
        self._publish("vault.policy.updated", rule_count=rule_count)
        return self.policy_snapshot()

    def preview_policy(self, text: str, scope: ConsentScope) -> dict[str, Any]:
        """Return a redacted preview and consent decision for sample text."""
        decision = self.policy.evaluate(text, scope)
        result = self.policy.redact(text)
        return {"decision": decision.as_dict(), "preview": result.as_dict()}

    def audit_list(self, criteria: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return a filtered, redacted audit page."""
        audit_filter = parse_audit_filter(criteria or {})
        entries = self._audit.query(audit_filter)
        return {
            "entries": [entry.as_dict() for entry in entries],
            "total": len(self._audit.entries()),
            "filter": audit_filter.as_dict(),
            "stats": self._audit.stats(),
        }

    def audit_export(
        self,
        *,
        fmt: str = "json",
        criteria: Mapping[str, Any] | None = None,
        request_id: str = "",
    ) -> str:
        """Export the audit trail after asserting that no secret is present."""
        audit_filter = parse_audit_filter(criteria or {})
        exported = self._audit.export(criteria=audit_filter, fmt=fmt)
        rendered = exported.render()
        try:
            self.policy.assert_clean(rendered)
        except PolicyError as error:
            raise VaultSecurityError("Audit export failed secret-free validation") from error
        self._audit.record(
            AuditAction.AUDIT_EXPORT,
            actor="local",
            subject=self.vault_id,
            detail={"format": fmt, "exported": len(exported.entries)},
            request_id=request_id,
        )
        return rendered

    def policy_snapshot(self) -> dict[str, Any]:
        """Return the secret-free policy state."""
        return self.policy.snapshot()

    def snapshots(self) -> dict[str, dict[str, Any]]:
        """Collect all secret-free component snapshots for posture scoring."""
        key_snapshot = self._keyring.snapshot()
        return {
            "vault": {
                "vault_id": self.vault_id,
                "state": self._state.value,
                "initialized": self.is_initialized,
                "created_at": self._created_at,
                "ciphertext_bytes": self._seal.ciphertext_bytes if self._seal else 0,
            },
            "keyring": key_snapshot,
            "recovery": self._recovery.snapshot(now=self.clock.now_timestamp()),
            "policy": self.policy_snapshot(),
            "audit": {"stats": self._audit.stats(), "max_entries": self._audit.max_entries},
        }

    def posture(self) -> PostureReport:
        """Score the current posture without exposing any secret values."""
        warnings: tuple[str, ...] = ()
        if self._state is VaultState.UNINITIALIZED:
            warnings = ("Vault encryption has not been configured",)
        report = score_posture(self.snapshots(), now=self.clock.now_timestamp(), warnings=warnings)
        assert_secret_free(report, self.policy)
        return report

    def status(self) -> dict[str, Any]:
        """Return a compact, secret-free dashboard status payload."""
        report = self.posture()
        active = self._keyring.active()
        return {
            "vault_id": self.vault_id,
            "state": self._state.value,
            "initialized": self.is_initialized,
            "active_key_id": active.key_id if active else "",
            "key_version": active.version if active else 0,
            "rotation_count": self._keyring.rotation_count,
            "recovery_active": self._recovery.active_count(self.clock.now_timestamp()),
            "audit_total": len(self._audit.entries()),
            "posture": report.as_dict(),
        }

    def events(self) -> tuple[dict[str, Any], ...]:
        """Return recorded events for the activity timeline."""
        return tuple(dict(item) for item in self.bus.snapshot()["events"])

    def _publish(self, kind: str, **payload: Any) -> None:
        try:
            self.policy.assert_clean(json.dumps(payload, sort_keys=True))
        except PolicyError as error:
            raise VaultSecurityError("Event payload failed secret-free validation") from error
        subject = EntityRef.of(ENTITY_EVIDENCE, self.vault_id, "Security vault").entity_id
        self.bus.publish(make_event(kind, subject=subject, **payload))

    def _require_initialized(self) -> None:
        if self._seal is None or not self._keyring.is_initialized:
            raise VaultNotInitializedError("Vault encryption is not configured")

    def _replacement_recovery(self, passphrase: str, *, count: int, now: float) -> tuple[str, ...]:
        self._recovery.clear()
        self._escrows.clear()
        codes = self._recovery.issue(count, created_at=now)
        for code in codes:
            record = self._recovery.lookup(code)
            assert record is not None
            self._escrows[record.code_id] = encrypt_vault(
                passphrase.encode("utf-8"),
                normalize_code(code),
                vault_id=f"recovery-{record.code_id}",
            )
        return codes


def _validate_passphrase(passphrase: str) -> None:
    if not isinstance(passphrase, str) or len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise VaultSecurityError(f"Passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters")
    if passphrase.strip() != passphrase:
        raise VaultSecurityError("Passphrase cannot have leading or trailing whitespace")


def _validate_code_count(count: int) -> None:
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("recovery count must be an integer")
    if not 1 <= count <= MAX_RECOVERY_CODES:
        raise ValueError(f"recovery count must be between 1 and {MAX_RECOVERY_CODES}")


def parse_scope(value: str) -> ConsentScope:
    """Parse a consent scope from an API string."""
    try:
        return ConsentScope(value)
    except ValueError as error:
        raise PolicyError(f"Unknown consent scope: {value}") from error
