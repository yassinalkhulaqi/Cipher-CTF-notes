"""Key derivation wrappers for security-sensitive workflows."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any

DEFAULT_ITERATIONS = 390_000
DEFAULT_SALT_BYTES = 16
DEFAULT_LENGTH = 32
MIN_ITERATIONS = 100_000
MIN_SALT_BYTES = 8
MAX_LENGTH = 128


@dataclass(frozen=True, slots=True)
class KdfParams:
    """Parameters controlling passphrase-based key derivation."""

    algorithm: str = "pbkdf2_hmac_sha256"
    iterations: int = DEFAULT_ITERATIONS
    salt_bytes: int = DEFAULT_SALT_BYTES
    length: int = DEFAULT_LENGTH
    digest: str = "sha256"

    def __post_init__(self) -> None:
        if self.algorithm != "pbkdf2_hmac_sha256":
            raise ValueError(f"Unsupported KDF algorithm: {self.algorithm}")
        if self.iterations < MIN_ITERATIONS:
            raise ValueError(f"iterations must be >= {MIN_ITERATIONS}")
        if self.salt_bytes < MIN_SALT_BYTES:
            raise ValueError(f"salt_bytes must be >= {MIN_SALT_BYTES}")
        if self.length < 16 or self.length > MAX_LENGTH:
            raise ValueError(f"length must be between 16 and {MAX_LENGTH}")
        if self.digest != "sha256":
            raise ValueError("Only sha256 digest is supported")

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "iterations": self.iterations,
            "salt_bytes": self.salt_bytes,
            "length": self.length,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KdfParams:
        return cls(
            algorithm=str(payload.get("algorithm", "pbkdf2_hmac_sha256")),
            iterations=int(payload.get("iterations", DEFAULT_ITERATIONS)),
            salt_bytes=int(payload.get("salt_bytes", DEFAULT_SALT_BYTES)),
            length=int(payload.get("length", DEFAULT_LENGTH)),
            digest=str(payload.get("digest", "sha256")),
        )


@dataclass(frozen=True, slots=True)
class DerivedKey:
    """Derived key material and the parameters required to reproduce it."""

    key_b64: str
    salt_b64: str
    params: KdfParams

    @property
    def key(self) -> bytes:
        return base64.urlsafe_b64decode(self.key_b64.encode("ascii"))

    @property
    def salt(self) -> bytes:
        return base64.urlsafe_b64decode(self.salt_b64.encode("ascii"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key_b64,
            "salt": self.salt_b64,
            "params": self.params.as_dict(),
        }


def generate_salt(length: int = DEFAULT_SALT_BYTES) -> bytes:
    """Generate a cryptographically random salt."""
    if length < MIN_SALT_BYTES:
        raise ValueError(f"salt length must be >= {MIN_SALT_BYTES}")
    return secrets.token_bytes(length)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))


def derive_key_material(
    passphrase: str,
    salt: bytes,
    *,
    params: KdfParams | None = None,
) -> bytes:
    """Derive raw key bytes from a passphrase and salt."""
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    if not isinstance(salt, (bytes, bytearray)):
        raise TypeError("salt must be bytes")
    params = params or KdfParams()
    if len(salt) < MIN_SALT_BYTES:
        raise ValueError(f"salt must be at least {MIN_SALT_BYTES} bytes")
    return hashlib.pbkdf2_hmac(
        params.digest,
        passphrase.encode("utf-8"),
        bytes(salt),
        params.iterations,
        dklen=params.length,
    )


def derive_key(
    passphrase: str,
    *,
    salt: str | bytes | None = None,
    params: KdfParams | None = None,
) -> DerivedKey:
    """Derive and serialize key material for storage or transport."""
    params = params or KdfParams()
    if salt is None:
        salt_bytes = generate_salt(params.salt_bytes)
    elif isinstance(salt, str):
        salt_bytes = _b64decode(salt)
    else:
        salt_bytes = bytes(salt)
    key = derive_key_material(passphrase, salt_bytes, params=params)
    return DerivedKey(
        key_b64=_b64encode(key),
        salt_b64=_b64encode(salt_bytes),
        params=params,
    )


def verify_passphrase(
    passphrase: str,
    *,
    expected_key_b64: str,
    salt_b64: str,
    params: KdfParams | dict[str, Any] | None = None,
) -> bool:
    """Return whether a passphrase reproduces the expected derived key."""
    resolved = KdfParams.from_dict(params) if isinstance(params, dict) else params or KdfParams()
    derived = derive_key_material(passphrase, _b64decode(salt_b64), params=resolved)
    expected = _b64decode(expected_key_b64)
    return hashlib.sha256(derived).digest() == hashlib.sha256(expected).digest() and len(
        derived
    ) == len(expected)


def stretch_iterations(target_ms: int = 150, *, salt_bytes: int = 16) -> int:
    """Estimate a PBKDF2 iteration count for the current host.

    The result is clamped to a safe minimum so callers can use it for
    configuration defaults without dropping below policy thresholds.
    """
    if target_ms <= 0:
        raise ValueError("target_ms must be positive")
    probe_iterations = 50_000
    salt = os.urandom(max(MIN_SALT_BYTES, salt_bytes))
    start = os.times().elapsed
    hashlib.pbkdf2_hmac("sha256", b"probe", salt, probe_iterations, dklen=32)
    elapsed = max(0.001, os.times().elapsed - start)
    estimated = int(probe_iterations * (target_ms / 1000.0) / elapsed)
    return max(MIN_ITERATIONS, estimated)
