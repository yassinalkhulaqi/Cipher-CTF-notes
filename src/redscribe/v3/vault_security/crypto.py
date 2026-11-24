"""Stdlib-only at-rest vault encryption wiring.

The vault seal format combines PBKDF2-HMAC-SHA256 key derivation with an
HMAC-SHA256 keystream for confidentiality and a separate authentication tag.
No third-party cryptography package is required and no plaintext is ever
written to disk by this module.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MAGIC = "RSV3VAULT"
FORMAT_VERSION = 1
DEFAULT_ITERATIONS = 120_000
MIN_ITERATIONS = 10_000
MAX_ITERATIONS = 2_000_000
RECOMMENDED_ITERATIONS = 100_000
SALT_BYTES = 16
NONCE_BYTES = 16
KEY_BYTES = 64

_STREAM_LABEL = b"redscribe-v3-vault-stream"
_MAC_LABEL = b"redscribe-v3-vault-mac"
_KEY_LABEL = b"redscribe-v3-vault-key"


class VaultIntegrityError(Exception):
    """Raised when a seal is malformed, tampered with, or opened with a wrong key."""


@dataclass(frozen=True, slots=True)
class VaultKdfParams:
    """Public parameters required to reproduce a vault encryption key."""

    algorithm: str = "pbkdf2_hmac_sha256"
    iterations: int = DEFAULT_ITERATIONS
    salt_bytes: int = SALT_BYTES
    length: int = KEY_BYTES
    digest: str = "sha256"

    def __post_init__(self) -> None:
        if self.algorithm != "pbkdf2_hmac_sha256":
            raise ValueError(f"Unsupported KDF algorithm: {self.algorithm}")
        if not MIN_ITERATIONS <= self.iterations <= MAX_ITERATIONS:
            raise ValueError("iterations must be between 10000 and 2000000")
        if self.salt_bytes < SALT_BYTES:
            raise ValueError("salt_bytes must be at least 16")
        if self.length != KEY_BYTES:
            raise ValueError("length must be 64 bytes")
        if self.digest != "sha256":
            raise ValueError("Only sha256 is supported")

    @property
    def strong(self) -> bool:
        """Whether the iteration count meets the recommended floor."""
        return self.iterations >= RECOMMENDED_ITERATIONS

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "algorithm": self.algorithm,
            "iterations": self.iterations,
            "salt_bytes": self.salt_bytes,
            "length": self.length,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VaultKdfParams:
        """Rebuild parameters from a persisted mapping."""
        return cls(
            algorithm=str(payload.get("algorithm", "pbkdf2_hmac_sha256")),
            iterations=int(payload.get("iterations", DEFAULT_ITERATIONS)),
            salt_bytes=int(payload.get("salt_bytes", SALT_BYTES)),
            length=int(payload.get("length", KEY_BYTES)),
            digest=str(payload.get("digest", "sha256")),
        )


@dataclass(frozen=True, slots=True)
class VaultSeal:
    """Serialized ciphertext plus the metadata needed to open it."""

    version: int
    salt_b64: str
    nonce_b64: str
    ciphertext_b64: str
    tag_b64: str
    params: VaultKdfParams
    vault_id: str = "primary"
    reserved: dict[str, Any] = field(default_factory=dict)

    @property
    def ciphertext_bytes(self) -> int:
        """Length of the ciphertext in bytes."""
        return len(_decode(self.ciphertext_b64))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the seal."""
        return {
            "magic": MAGIC,
            "version": self.version,
            "vault_id": self.vault_id,
            "salt": self.salt_b64,
            "nonce": self.nonce_b64,
            "ciphertext": self.ciphertext_b64,
            "tag": self.tag_b64,
            "kdf": self.params.as_dict(),
            "reserved": dict(self.reserved),
        }

    def to_json(self) -> str:
        """Serialize the seal to a compact JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VaultSeal:
        """Parse a seal from a mapping, validating its envelope."""
        magic = str(payload.get("magic", ""))
        if magic != MAGIC:
            raise VaultIntegrityError("Unsupported vault seal format")
        version = int(payload.get("version", 0))
        if version != FORMAT_VERSION:
            raise VaultIntegrityError("Unsupported vault seal version")
        params_raw = payload.get("kdf")
        if not isinstance(params_raw, Mapping):
            raise VaultIntegrityError("Vault seal is missing kdf metadata")
        reserved = payload.get("reserved", {})
        if not isinstance(reserved, Mapping):
            raise VaultIntegrityError("Vault seal reserved field must be an object")
        try:
            return cls(
                version=version,
                vault_id=str(payload.get("vault_id", "primary")),
                salt_b64=_required_text(payload, "salt"),
                nonce_b64=_required_text(payload, "nonce"),
                ciphertext_b64=_required_text(payload, "ciphertext"),
                tag_b64=_required_text(payload, "tag"),
                params=VaultKdfParams.from_dict(params_raw),
                reserved=dict(reserved),
            )
        except ValueError as error:
            raise VaultIntegrityError(str(error)) from error

    @classmethod
    def from_json(cls, text: str) -> VaultSeal:
        """Parse a seal from a JSON string."""
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError) as error:
            raise VaultIntegrityError("Vault seal is not valid JSON") from error
        if not isinstance(decoded, Mapping):
            raise VaultIntegrityError("Vault seal must be a JSON object")
        return cls.from_dict(decoded)


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise VaultIntegrityError(f"Vault seal is missing {key}")
    return value


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _decode(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise VaultIntegrityError("Vault seal contains invalid base64") from error


def derive_vault_key(
    passphrase: str,
    salt: bytes,
    *,
    params: VaultKdfParams | None = None,
) -> bytes:
    """Derive 64 bytes of key material from a passphrase and salt."""
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    if not isinstance(salt, (bytes, bytearray)):
        raise TypeError("salt must be bytes")
    resolved = params or VaultKdfParams()
    if len(salt) < resolved.salt_bytes:
        raise ValueError("salt is shorter than the configured salt length")
    return hashlib.pbkdf2_hmac(
        resolved.digest,
        passphrase.encode("utf-8"),
        bytes(salt),
        resolved.iterations,
        dklen=resolved.length,
    )


def key_verifier(key: bytes) -> str:
    """Return a non-reversible verifier for derived key material."""
    if not isinstance(key, (bytes, bytearray)):
        raise TypeError("key must be bytes")
    return _encode(hashlib.blake2b(bytes(key), digest_size=16).digest())


def _split_key(key: bytes) -> tuple[bytes, bytes]:
    if len(key) != KEY_BYTES:
        raise VaultIntegrityError("Derived key has the wrong length")
    return key[:32], key[32:]


def _bound_nonce(nonce: bytes, vault_id: str, associated_data: bytes) -> bytes:
    binding = vault_id.encode("utf-8") + b"\x00" + associated_data
    return hashlib.sha256(nonce + b"\x00" + binding).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = hmac.new(
            key,
            _STREAM_LABEL + nonce + counter.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(left ^ right for left, right in zip(data, stream, strict=True))


def _tag(mac_key: bytes, nonce: bytes, ciphertext: bytes, params: VaultKdfParams) -> bytes:
    header = (
        MAGIC.encode("ascii")
        + FORMAT_VERSION.to_bytes(2, "big")
        + params.digest.encode("ascii")
        + params.iterations.to_bytes(4, "big")
        + params.length.to_bytes(4, "big")
    )
    return hmac.new(mac_key, _MAC_LABEL + header + nonce + ciphertext, hashlib.sha256).digest()


def encrypt_vault(
    plaintext: bytes,
    passphrase: str,
    *,
    params: VaultKdfParams | None = None,
    vault_id: str = "primary",
    associated_data: bytes = b"",
) -> VaultSeal:
    """Encrypt bytes into a self-describing vault seal."""
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("plaintext must be bytes")
    if not isinstance(associated_data, (bytes, bytearray)):
        raise TypeError("associated_data must be bytes")
    if not vault_id or "\x00" in vault_id:
        raise ValueError("vault_id must be non-empty and cannot contain NUL")
    resolved = params or VaultKdfParams()
    salt = secrets.token_bytes(resolved.salt_bytes)
    nonce = secrets.token_bytes(NONCE_BYTES)
    bound = _bound_nonce(nonce, vault_id, bytes(associated_data))
    stream_key, mac_key = _split_key(derive_vault_key(passphrase, salt, params=resolved))
    ciphertext = _xor(bytes(plaintext), _keystream(stream_key, bound, len(plaintext)))
    tag = _tag(mac_key, bound, ciphertext, resolved)
    return VaultSeal(
        version=FORMAT_VERSION,
        salt_b64=_encode(salt),
        nonce_b64=_encode(nonce),
        ciphertext_b64=_encode(ciphertext),
        tag_b64=_encode(tag),
        params=resolved,
        vault_id=vault_id,
    )


def decrypt_vault(
    seal: VaultSeal | Mapping[str, Any] | str,
    passphrase: str,
    *,
    vault_id: str = "primary",
    associated_data: bytes = b"",
) -> bytes:
    """Decrypt a seal, refusing wrong keys and tampered ciphertext."""
    parsed = _coerce_seal(seal)
    if parsed.vault_id != vault_id:
        raise VaultIntegrityError("Vault seal belongs to a different vault")
    bound = _bound_nonce(_decode(parsed.nonce_b64), vault_id, bytes(associated_data))
    ciphertext = _decode(parsed.ciphertext_b64)
    stream_key, mac_key = _split_key(
        derive_vault_key(passphrase, _decode(parsed.salt_b64), params=parsed.params)
    )
    expected_tag = _decode(parsed.tag_b64)
    actual_tag = _tag(mac_key, bound, ciphertext, parsed.params)
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise VaultIntegrityError("Decryption failed: authentication tag mismatch")
    return _xor(ciphertext, _keystream(stream_key, bound, len(ciphertext)))


def verify_vault_passphrase(
    seal: VaultSeal | Mapping[str, Any] | str,
    passphrase: str,
    *,
    vault_id: str = "primary",
) -> bool:
    """Check a passphrase without decrypting or exposing vault content."""
    parsed = _coerce_seal(seal)
    if parsed.vault_id != vault_id:
        return False
    bound = _bound_nonce(_decode(parsed.nonce_b64), vault_id, b"")
    _, mac_key = _split_key(
        derive_vault_key(passphrase, _decode(parsed.salt_b64), params=parsed.params)
    )
    expected_tag = _decode(parsed.tag_b64)
    return hmac.compare_digest(
        _tag(mac_key, bound, _decode(parsed.ciphertext_b64), parsed.params),
        expected_tag,
    )


def _coerce_seal(
    seal: VaultSeal | Mapping[str, Any] | str,
) -> VaultSeal:
    if isinstance(seal, VaultSeal):
        return seal
    if isinstance(seal, str):
        return VaultSeal.from_json(seal)
    if isinstance(seal, Mapping):
        return VaultSeal.from_dict(seal)
    raise TypeError("seal must be a VaultSeal, mapping, or JSON string")


def seal_json(
    payload: Mapping[str, Any],
    passphrase: str,
    *,
    params: VaultKdfParams | None = None,
    vault_id: str = "primary",
) -> VaultSeal:
    """Serialize a JSON mapping and seal it."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return encrypt_vault(encoded, passphrase, params=params, vault_id=vault_id)


def unseal_json(
    seal: VaultSeal | Mapping[str, Any] | str,
    passphrase: str,
    *,
    vault_id: str = "primary",
) -> dict[str, Any]:
    """Unseal JSON content and validate that it is an object."""
    raw = decrypt_vault(seal, passphrase, vault_id=vault_id)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise VaultIntegrityError("Unsealed content is not valid UTF-8 JSON") from error
    if not isinstance(decoded, dict):
        raise VaultIntegrityError("Vault content must be a JSON object")
    return decoded
