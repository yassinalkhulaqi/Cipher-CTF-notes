"""Typed, secret-free data contracts for the v4 security vault.

Every structure in this module is deliberately *data only*: key records carry
metadata but no key bytes, recovery records carry digests but no plaintext
codes, and sealed envelopes carry ciphertext that is meaningless without an
external key. Validation is strict and happens at construction time so that a
malformed record can never reach the service or storage layers.

The module depends only on the Python standard library and the shared v4
contracts; it never performs I/O and never executes user-supplied input.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

ENVELOPE_VERSION = 1
KEY_BYTES = 32
NONCE_BYTES = 16
MAC_BYTES = 32
SALT_BYTES = 16
DEFAULT_ITERATIONS = 100_000
MIN_PASSPHRASE_LENGTH = 12

HEX_PATTERN = re.compile(r"^[0-9a-fA-F]*$")
ID_PATTERN = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$")
FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*|\.\*)*$")
TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class KeyState(str, Enum):
    """Lifecycle state of a vault key.

    Only ACTIVE keys may seal new envelopes. ROTATED keys remain available for
    opening historical envelopes, while REVOKED keys are retained for audit
    metadata only and cannot be used for either operation.
    """

    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"

    @classmethod
    def parse(cls, value: str) -> KeyState:
        """Parse a case-insensitive state name."""
        normalized = value.strip().casefold()
        for state in cls:
            if state.value == normalized:
                return state
        raise ValueError(f"Unknown key state: {value}")

    @property
    def label(self) -> str:
        """Return a human-readable label."""
        return self.value.title()

    @property
    def can_seal(self) -> bool:
        return self is KeyState.ACTIVE

    @property
    def can_open(self) -> bool:
        return self in (KeyState.ACTIVE, KeyState.ROTATED)


class PrivacyMode(str, Enum):
    """How aggressively the UI and API redact sensitive fields."""

    NORMAL = "normal"
    REDACTED = "redacted"
    LOCKED = "locked"

    @classmethod
    def parse(cls, value: str) -> PrivacyMode:
        normalized = value.strip().casefold()
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(f"Unknown privacy mode: {value}")

    @property
    def label(self) -> str:
        return self.value.title()

    @property
    def hides_content(self) -> bool:
        return self is not PrivacyMode.NORMAL


def require_text(value: object, field: str, *, allow_empty: bool = False) -> str:
    """Validate and normalize a text field."""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError(f"{field} must not be empty")
    return text


def require_identifier(value: object, field: str) -> str:
    """Validate an opaque identifier without prescribing its generator."""
    text = require_text(value, field)
    if not ID_PATTERN.match(text):
        raise ValueError(f"{field} has an invalid shape")
    return text.casefold()


def require_positive_int(value: object, field: str) -> int:
    """Validate a strictly positive integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def require_bool(value: object, field: str) -> bool:
    """Validate a boolean, rejecting truthy strings and integers."""
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def normalize_hex(
    value: object,
    field: str,
    *,
    allow_empty: bool = False,
    exact_bytes: int | None = None,
) -> str:
    """Validate a hex string and return it in lowercase."""
    text = require_text(value, field, allow_empty=allow_empty)
    if not text:
        return ""
    if len(text) % 2 != 0 or not HEX_PATTERN.match(text):
        raise ValueError(f"{field} must be even-length hexadecimal")
    if exact_bytes is not None and len(text) // 2 != exact_bytes:
        raise ValueError(f"{field} must encode exactly {exact_bytes} bytes")
    return text.casefold()


def normalize_timestamp(value: object, field: str) -> str:
    """Validate an ISO-8601 timestamp with an explicit UTC offset."""
    text = require_text(value, field)
    if not TIMESTAMP_PATTERN.match(text):
        raise ValueError(f"{field} must be an ISO-8601 timestamp with a timezone")
    return text


@dataclass(frozen=True, slots=True)
class KeyRecord:
    """Public metadata for a vault key.

    Key material is intentionally absent. Instances are safe to serialize, log,
    and persist; the only secret-adjacent value is the opaque identifier.
    """

    id: str
    version: int
    state: KeyState
    created_at: str
    rotated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_identifier(self.id, "id"))
        object.__setattr__(self, "version", require_positive_int(self.version, "version"))
        if not isinstance(self.state, KeyState):
            raise ValueError("state must be a KeyState")
        object.__setattr__(self, "created_at", normalize_timestamp(self.created_at, "created_at"))
        rotated = normalize_timestamp(self.rotated_at, "rotated_at") if self.rotated_at else ""
        if self.state is not KeyState.ACTIVE and not rotated:
            raise ValueError("rotated_at is required for rotated or revoked keys")
        object.__setattr__(self, "rotated_at", rotated)

    @property
    def is_usable(self) -> bool:
        return self.state.can_open

    @property
    def label(self) -> str:
        return f"v{self.version} ({self.state.label})"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe, secret-free mapping."""
        return {
            "id": self.id,
            "version": self.version,
            "state": self.state.value,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeyRecord:
        """Build a record from an untrusted mapping."""
        return cls(
            id=data.get("id", ""),
            version=data.get("version", 0),
            state=KeyState.parse(str(data.get("state", ""))),
            created_at=str(data.get("created_at", "")),
            rotated_at=str(data.get("rotated_at", "")),
        )


@dataclass(frozen=True, slots=True)
class SealedEnvelope:
    """An authenticated ciphertext blob plus the metadata needed to open it.

    The associated data string is authenticated but not encrypted; callers may
    store it openly as a context label. Nonces are unique per seal operation.
    """

    version: int
    key_id: str
    nonce: str
    ciphertext_hex: str
    mac_hex: str
    aad: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", require_positive_int(self.version, "version"))
        key_id = require_text(self.key_id, "key_id", allow_empty=True)
        if key_id:
            key_id = require_identifier(key_id, "key_id")
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(
            self, "nonce", normalize_hex(self.nonce, "nonce", exact_bytes=NONCE_BYTES)
        )
        object.__setattr__(
            self,
            "ciphertext_hex",
            normalize_hex(self.ciphertext_hex, "ciphertext_hex", allow_empty=True),
        )
        object.__setattr__(
            self, "mac_hex", normalize_hex(self.mac_hex, "mac_hex", exact_bytes=MAC_BYTES)
        )
        object.__setattr__(self, "aad", require_text(self.aad, "aad", allow_empty=True))

    @property
    def nonce_bytes(self) -> bytes:
        return bytes.fromhex(self.nonce)

    @property
    def ciphertext(self) -> bytes:
        return bytes.fromhex(self.ciphertext_hex)

    @property
    def mac(self) -> bytes:
        return bytes.fromhex(self.mac_hex)

    @property
    def plaintext_size(self) -> int:
        return len(self.ciphertext)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe mapping for transport or storage."""
        return {
            "version": self.version,
            "key_id": self.key_id,
            "nonce": self.nonce,
            "ciphertext_hex": self.ciphertext_hex,
            "mac_hex": self.mac_hex,
            "aad": self.aad,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SealedEnvelope:
        return cls(
            version=data.get("version", 0),
            key_id=str(data.get("key_id", "")),
            nonce=str(data.get("nonce", "")),
            ciphertext_hex=str(data.get("ciphertext_hex", "")),
            mac_hex=str(data.get("mac_hex", "")),
            aad=str(data.get("aad", "")),
        )


@dataclass(frozen=True, slots=True)
class RecoveryCode:
    """A single-use recovery credential stored only as a digest."""

    id: str
    code_hash: str
    used: bool
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_identifier(self.id, "id"))
        object.__setattr__(
            self, "code_hash", normalize_hex(self.code_hash, "code_hash", exact_bytes=32)
        )
        object.__setattr__(self, "used", require_bool(self.used, "used"))
        object.__setattr__(self, "created_at", normalize_timestamp(self.created_at, "created_at"))

    def matches(self, candidate_hash: str) -> bool:
        """Constant-time comparison against a normalized digest."""
        normalized = normalize_hex(candidate_hash, "candidate_hash", exact_bytes=32)
        return hmac.compare_digest(self.code_hash, normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code_hash": self.code_hash,
            "used": self.used,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoveryCode:
        return cls(
            id=str(data.get("id", "")),
            code_hash=str(data.get("code_hash", "")),
            used=require_bool(data.get("used", False), "used"),
            created_at=str(data.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class KeySaltRecord:
    """Non-secret KDF parameters persisted alongside key metadata."""

    key_id: str
    salt_hex: str
    iterations: int
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", require_identifier(self.key_id, "key_id"))
        object.__setattr__(
            self, "salt_hex", normalize_hex(self.salt_hex, "salt_hex", exact_bytes=SALT_BYTES)
        )
        object.__setattr__(self, "iterations", require_positive_int(self.iterations, "iterations"))
        object.__setattr__(self, "created_at", normalize_timestamp(self.created_at, "created_at"))

    @property
    def salt(self) -> bytes:
        return bytes.fromhex(self.salt_hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "salt_hex": self.salt_hex,
            "iterations": self.iterations,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeySaltRecord:
        return cls(
            key_id=str(data.get("key_id", "")),
            salt_hex=str(data.get("salt_hex", "")),
            iterations=data.get("iterations", 0),
            created_at=str(data.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class RedactionRule:
    """Replace one dotted field path with a fixed, non-sensitive token."""

    field: str
    replacement: str

    def __post_init__(self) -> None:
        field = require_text(self.field, "field")
        if not FIELD_PATTERN.match(field):
            raise ValueError("field must be a dotted identifier path")
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "replacement", require_text(self.replacement, "replacement"))

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.field.split("."))

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "replacement": self.replacement}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RedactionRule:
        return cls(
            field=str(data.get("field", "")),
            replacement=str(data.get("replacement", "")),
        )


__all__ = [
    "DEFAULT_ITERATIONS",
    "ENVELOPE_VERSION",
    "KEY_BYTES",
    "MAC_BYTES",
    "MIN_PASSPHRASE_LENGTH",
    "NONCE_BYTES",
    "SALT_BYTES",
    "KeyRecord",
    "KeySaltRecord",
    "KeyState",
    "PrivacyMode",
    "RecoveryCode",
    "RedactionRule",
    "SealedEnvelope",
    "normalize_hex",
    "normalize_timestamp",
    "require_bool",
    "require_identifier",
    "require_positive_int",
    "require_text",
]
