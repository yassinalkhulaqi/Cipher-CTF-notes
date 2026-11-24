"""Dependency-free authenticated encryption for portable vault bundles.

The construction deliberately uses only the Python standard library: PBKDF2 for
key derivation, a BLAKE2b-based keystream for confidentiality, and an
HMAC-SHA256 tag over the nonce, ciphertext, and additional authenticated data
for integrity. The format is versioned so a future branch can rotate in an
audited implementation without rewriting old bundles.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from redscribe.v3.portability.errors import DecryptionError, PortabilityError

ALGORITHM = "blake2b-xor-hmac-sha256-v1"
DEFAULT_KDF_ITERATIONS = 60_000
MIN_KDF_ITERATIONS = 1_000
MAX_KDF_ITERATIONS = 1_000_000
KEY_LENGTH = 32
NONCE_LENGTH = 16
SALT_LENGTH = 16
MAX_PLAINTEXT_BYTES = 32 * 1024 * 1024

_ENC_PERSON = b"redscribe-v3-enc"
_MAC_PERSON = b"redscribe-v3-mac"


@dataclass(frozen=True, slots=True)
class EncryptedBlob:
    """A versioned, base64-friendly encrypted payload."""

    salt: bytes = field(repr=False)
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)
    tag: bytes = field(repr=False)
    iterations: int = DEFAULT_KDF_ITERATIONS
    algorithm: str = ALGORITHM
    aad: str = ""

    def __post_init__(self) -> None:
        if self.algorithm != ALGORITHM:
            raise PortabilityError(f"Unsupported encryption algorithm: {self.algorithm}")
        if len(self.salt) != SALT_LENGTH or len(self.nonce) != NONCE_LENGTH:
            raise PortabilityError("Invalid encryption salt or nonce length")
        if not MIN_KDF_ITERATIONS <= self.iterations <= MAX_KDF_ITERATIONS:
            raise PortabilityError("Unsupported KDF iteration count")
        if not self.tag:
            raise PortabilityError("Missing authentication tag")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation with base64 binary fields."""
        return {
            "algorithm": self.algorithm,
            "salt": _b64encode(self.salt),
            "nonce": _b64encode(self.nonce),
            "iterations": self.iterations,
            "ciphertext": _b64encode(self.ciphertext),
            "tag": _b64encode(self.tag),
            "aad": self.aad,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EncryptedBlob:
        """Rebuild a blob from a JSON-safe representation."""
        try:
            return cls(
                algorithm=str(payload["algorithm"]),
                salt=_b64decode(str(payload["salt"])),
                nonce=_b64decode(str(payload["nonce"])),
                iterations=int(str(payload["iterations"])),
                ciphertext=_b64decode(str(payload["ciphertext"])),
                tag=_b64decode(str(payload["tag"])),
                aad=str(payload.get("aad", "")),
            )
        except (KeyError, TypeError, ValueError, PortabilityError) as error:
            raise DecryptionError("Malformed encrypted blob") from error


def _b64encode(value: bytes) -> str:
    """Encode bytes as URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    """Decode URL-safe base64, restoring padding."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def derive_key(
    passphrase: str,
    salt: bytes,
    *,
    iterations: int = DEFAULT_KDF_ITERATIONS,
) -> bytes:
    """Derive a 32-byte master key from a passphrase and salt."""
    if not passphrase:
        raise PortabilityError("Passphrase cannot be empty")
    if len(salt) < 8:
        raise PortabilityError("Salt is too short")
    if not MIN_KDF_ITERATIONS <= iterations <= MAX_KDF_ITERATIONS:
        raise PortabilityError("Unsupported KDF iteration count")
    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, iterations, dklen=KEY_LENGTH
    )


def _subkey(master: bytes, person: bytes) -> bytes:
    """Derive a purpose-specific key from a master key."""
    return hashlib.blake2b(master, digest_size=KEY_LENGTH, person=person).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Produce a deterministic keystream for a nonce and length."""
    blocks: list[bytes] = []
    counter = 0
    produced = 0
    while produced < length:
        block = hashlib.blake2b(
            nonce + counter.to_bytes(4, "big"),
            key=key,
            digest_size=KEY_LENGTH,
        ).digest()
        blocks.append(block)
        produced += len(block)
        counter += 1
    return b"".join(blocks)[:length]


def _xor(data: bytes, stream: bytes) -> bytes:
    """XOR two byte strings of equal length."""
    return bytes(left ^ right for left, right in zip(data, stream, strict=True))


def _tag(mac_key: bytes, nonce: bytes, ciphertext: bytes, aad: str) -> bytes:
    """Compute the authentication tag over a ciphertext and its context."""
    message = nonce + len(ciphertext).to_bytes(8, "big") + ciphertext + aad.encode("utf-8")
    return hmac.new(mac_key, message, hashlib.sha256).digest()


def encrypt_bytes(
    plaintext: bytes,
    passphrase: str,
    *,
    aad: str = "",
    iterations: int = DEFAULT_KDF_ITERATIONS,
    salt: bytes | None = None,
    nonce: bytes | None = None,
) -> EncryptedBlob:
    """Encrypt bytes into an authenticated bundle blob."""
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise PortabilityError("Payload exceeds the maximum bundle size")
    chosen_salt = secrets.token_bytes(SALT_LENGTH) if salt is None else salt
    chosen_nonce = secrets.token_bytes(NONCE_LENGTH) if nonce is None else nonce
    master = derive_key(passphrase, chosen_salt, iterations=iterations)
    stream = _keystream(_subkey(master, _ENC_PERSON), chosen_nonce, len(plaintext))
    ciphertext = _xor(plaintext, stream)
    signature = _tag(_subkey(master, _MAC_PERSON), chosen_nonce, ciphertext, aad)
    return EncryptedBlob(
        salt=chosen_salt,
        nonce=chosen_nonce,
        iterations=iterations,
        ciphertext=ciphertext,
        tag=signature,
        aad=aad,
    )


def decrypt_bytes(blob: EncryptedBlob, passphrase: str) -> bytes:
    """Decrypt a blob, refusing to return data when the tag does not match."""
    master = derive_key(passphrase, blob.salt, iterations=blob.iterations)
    expected = _tag(_subkey(master, _MAC_PERSON), blob.nonce, blob.ciphertext, blob.aad)
    if not hmac.compare_digest(expected, blob.tag):
        raise DecryptionError("Bundle authentication failed; wrong passphrase or tampered data")
    stream = _keystream(_subkey(master, _ENC_PERSON), blob.nonce, len(blob.ciphertext))
    return _xor(blob.ciphertext, stream)


def passphrase_strength(passphrase: str) -> int:
    """Return a coarse 0-4 strength score used by the setup wizard."""
    if not passphrase:
        return 0
    classes = sum(
        (
            any(char.islower() for char in passphrase),
            any(char.isupper() for char in passphrase),
            any(char.isdigit() for char in passphrase),
            any(not char.isalnum() for char in passphrase),
        )
    )
    length_bonus = 1 if len(passphrase) >= 12 else 0
    return min(4, max(1, classes - 1 + length_bonus))


def is_strong_passphrase(passphrase: str, *, minimum_length: int = 10) -> bool:
    """Return whether a passphrase meets the local bundle policy."""
    return len(passphrase) >= minimum_length and passphrase_strength(passphrase) >= 2
