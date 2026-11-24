"""Vault key derivation, verification, and rotation state.

The key ring stores descriptors and verifiers only. Passphrases live in memory
while the vault is unlocked and are never serialized, logged, or exported.
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.vault_security.crypto import (
    DEFAULT_ITERATIONS,
    VaultKdfParams,
    derive_vault_key,
    key_verifier,
)


class KeyStatus(str, Enum):
    """Lifecycle state of one derived key generation."""

    ACTIVE = "active"
    RETIRED = "retired"
    REVOKED = "revoked"


class KeyRingError(Exception):
    """Raised for invalid key-ring transitions."""


@dataclass(frozen=True, slots=True)
class KeyDescriptor:
    """Public metadata for one generation of the vault encryption key."""

    key_id: str
    version: int
    created_at: float
    status: KeyStatus
    params: VaultKdfParams
    verifier: str
    salt_b64: str
    reason: str = "initial"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without key material."""
        return {
            "key_id": self.key_id,
            "version": self.version,
            "created_at": self.created_at,
            "status": self.status.value,
            "iterations": self.params.iterations,
            "algorithm": self.params.algorithm,
            "verifier": self.verifier,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RotationPlan:
    """Description of a completed or proposed key rotation."""

    from_key_id: str
    to_key_id: str
    from_version: int
    to_version: int
    created_at: float
    steps: tuple[str, ...] = (
        "verify_current_key",
        "derive_replacement_key",
        "rescale_ciphertext",
        "retire_previous_key",
    )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "from_key_id": self.from_key_id,
            "to_key_id": self.to_key_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "created_at": self.created_at,
            "steps": list(self.steps),
        }


@dataclass(slots=True)
class KeyRing:
    """In-memory key state for one vault.

    The passphrase is held only for the lifetime of an unlocked session. A
    custom ``__repr__`` keeps it out of tracebacks and debug logs.
    """

    vault_id: str = "primary"
    _passphrase: str = field(default="", repr=False)
    _keys: list[KeyDescriptor] = field(default_factory=list, repr=False)
    _next_version: int = field(default=1, repr=False)
    _rotation_count: int = field(default=0, repr=False)

    def __repr__(self) -> str:
        return (
            f"KeyRing(vault_id={self.vault_id!r}, unlocked={self.is_unlocked}, "
            f"version={self.current_version}, keys={len(self._keys)})"
        )

    @property
    def is_unlocked(self) -> bool:
        """Whether a passphrase is currently held in memory."""
        return bool(self._passphrase)

    @property
    def is_initialized(self) -> bool:
        """Whether at least one key generation exists."""
        return bool(self._keys)

    @property
    def current_version(self) -> int:
        """Active key version, or zero when uninitialized."""
        active = self.active()
        return active.version if active is not None else 0

    @property
    def rotation_count(self) -> int:
        """Number of rotations performed on this ring."""
        return self._rotation_count

    def active(self) -> KeyDescriptor | None:
        """Return the active descriptor, if any."""
        for descriptor in reversed(self._keys):
            if descriptor.status is KeyStatus.ACTIVE:
                return descriptor
        return None

    def install(
        self,
        passphrase: str,
        *,
        created_at: float,
        params: VaultKdfParams | None = None,
        key_id: str = "",
        reason: str = "initial",
    ) -> KeyDescriptor:
        """Install the first key generation for a fresh vault."""
        if self._keys:
            raise KeyRingError("Vault key ring is already initialized")
        resolved = params or VaultKdfParams()
        descriptor = self._build_descriptor(
            passphrase, resolved, created_at=created_at, key_id=key_id, reason=reason
        )
        self._keys.append(descriptor)
        self._next_version = descriptor.version + 1
        self._passphrase = passphrase
        return descriptor

    def unlock(self, passphrase: str) -> bool:
        """Verify a passphrase against the active verifier and unlock in memory."""
        active = self.active()
        if active is None:
            raise KeyRingError("Vault key ring is not initialized")
        if not passphrase:
            return False
        derived = derive_vault_key(passphrase, _salt_bytes(active.salt_b64), params=active.params)
        if not secrets.compare_digest(key_verifier(derived), active.verifier):
            return False
        self._passphrase = passphrase
        return True

    def verify(self, passphrase: str, *, key_id: str = "") -> bool:
        """Verify a passphrase against any known generation without unlocking."""
        candidates = [key for key in self._keys if key_id in ("", key.key_id)]
        if not candidates or not passphrase:
            return False
        for descriptor in candidates:
            derived = derive_vault_key(
                passphrase, _salt_bytes(descriptor.salt_b64), params=descriptor.params
            )
            if secrets.compare_digest(key_verifier(derived), descriptor.verifier):
                return True
        return False

    def rotate(
        self,
        new_passphrase: str,
        *,
        created_at: float,
        params: VaultKdfParams | None = None,
        key_id: str = "",
    ) -> RotationPlan:
        """Create a new active generation and retire the previous one."""
        previous = self.active()
        if previous is None:
            raise KeyRingError("Vault key ring is not initialized")
        if not self.is_unlocked:
            raise KeyRingError("Vault must be unlocked before rotating keys")
        if new_passphrase == self._passphrase:
            raise KeyRingError("New passphrase must differ from the current one")
        resolved = params or previous.params
        descriptor = self._build_descriptor(
            new_passphrase, resolved, created_at=created_at, key_id=key_id, reason="rotation"
        )
        self._retire(previous.key_id)
        self._keys.append(descriptor)
        self._next_version = descriptor.version + 1
        self._passphrase = new_passphrase
        self._rotation_count += 1
        return RotationPlan(
            from_key_id=previous.key_id,
            to_key_id=descriptor.key_id,
            from_version=previous.version,
            to_version=descriptor.version,
            created_at=created_at,
        )

    def reset(self, passphrase: str, *, created_at: float) -> KeyDescriptor:
        """Rebuild the ring after recovery, replacing all prior generations."""
        if not passphrase:
            raise KeyRingError("Recovery passphrase cannot be empty")
        self._keys.clear()
        self._passphrase = ""
        self._rotation_count = 0
        self._next_version = 1
        return self.install(passphrase, created_at=created_at, reason="recovery")

    def current_passphrase(self) -> str:
        """Return the in-memory passphrase for an unlocked vault."""
        if not self.is_unlocked:
            raise KeyRingError("Vault key ring is locked")
        return self._passphrase

    def lock(self) -> None:
        """Forget the in-memory passphrase."""
        self._passphrase = ""

    def revoke(self, key_id: str) -> bool:
        """Mark a non-active generation as revoked."""
        active = self.active()
        if active is not None and active.key_id == key_id:
            return False
        for descriptor in self._keys:
            if descriptor.key_id == key_id:
                object.__setattr__(descriptor, "status", KeyStatus.REVOKED)
                return True
        return False

    def descriptors(self) -> tuple[KeyDescriptor, ...]:
        """Return all key descriptors in version order."""
        return tuple(sorted(self._keys, key=lambda item: item.version))

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable, secret-free key-ring summary."""
        active = self.active()
        return {
            "vault_id": self.vault_id,
            "initialized": self.is_initialized,
            "unlocked": self.is_unlocked,
            "active_key_id": active.key_id if active else "",
            "active_version": active.version if active else 0,
            "key_count": len(self._keys),
            "rotation_count": self._rotation_count,
            "keys": [descriptor.as_dict() for descriptor in self.descriptors()],
        }

    def _retire(self, key_id: str) -> None:
        for descriptor in self._keys:
            if descriptor.key_id == key_id:
                object.__setattr__(descriptor, "status", KeyStatus.RETIRED)

    def _build_descriptor(
        self,
        passphrase: str,
        params: VaultKdfParams,
        *,
        created_at: float,
        key_id: str,
        reason: str,
    ) -> KeyDescriptor:
        if not passphrase:
            raise KeyRingError("Passphrase cannot be empty")
        salt = secrets.token_bytes(params.salt_bytes)
        derived = derive_vault_key(passphrase, salt, params=params)
        clean_id = key_id.strip() or f"key_{self._next_version:03d}_{salt[:4].hex()}"
        return KeyDescriptor(
            key_id=clean_id,
            version=self._next_version,
            created_at=created_at,
            status=KeyStatus.ACTIVE,
            params=params,
            verifier=key_verifier(derived),
            salt_b64=base64.urlsafe_b64encode(salt).decode("ascii"),
            reason=reason,
        )


def _salt_bytes(salt_b64: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise KeyRingError("Stored key salt is invalid") from error


def fresh_iterations(base: int = DEFAULT_ITERATIONS, *, step: int = 20_000) -> int:
    """Return a slightly hardened iteration count for a rotation."""
    if base < 0 or step <= 0:
        raise ValueError("base and step must be valid")
    return min(base + step, 2_000_000)


def descriptor_from_dict(payload: Mapping[str, Any]) -> KeyDescriptor:
    """Rebuild a descriptor from persisted metadata."""
    return KeyDescriptor(
        key_id=str(payload["key_id"]),
        version=int(payload["version"]),
        created_at=float(payload["created_at"]),
        status=KeyStatus(str(payload.get("status", KeyStatus.ACTIVE.value))),
        params=VaultKdfParams.from_dict(payload.get("params", {})),
        verifier=str(payload["verifier"]),
        salt_b64=str(payload["salt_b64"]),
        reason=str(payload.get("reason", "")),
    )
