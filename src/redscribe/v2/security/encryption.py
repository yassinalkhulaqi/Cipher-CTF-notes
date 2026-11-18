"""Stdlib-only encryption-at-rest helpers.

The implementation uses PBKDF2-HMAC-SHA256 for key derivation and an
HMAC-SHA256 based keystream for confidentiality with a separate HMAC tag for
integrity. It is intended as a local helper for vault export and storage
workflows where third-party cryptography dependencies are unavailable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from redscribe.v2.security.kdf import KdfParams, derive_key_material

MAGIC = "RSENC1"
DEFAULT_NONCE_BYTES = 16
STREAM_LABEL = b"redscribe-stream"
MAC_LABEL = b"redscribe-mac"


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """Serialized encrypted payload with metadata for decryption."""

    version: int
    salt_b64: str
    nonce_b64: str
    ciphertext_b64: str
    tag_b64: str
    kdf: KdfParams

    def to_dict(self) -> dict[str, Any]:
        return {
            "magic": MAGIC,
            "version": self.version,
            "salt": self.salt_b64,
            "nonce": self.nonce_b64,
            "ciphertext": self.ciphertext_b64,
            "tag": self.tag_b64,
            "kdf": self.kdf.as_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EncryptedPayload:
        magic = str(payload.get("magic", ""))
        if magic and magic != MAGIC:
            raise ValueError("Unsupported encrypted payload format")
        version = int(payload.get("version", 1))
        if version != 1:
            raise ValueError("Unsupported encrypted payload version")
        kdf_raw = payload.get("kdf")
        if not isinstance(kdf_raw, dict):
            raise ValueError("Encrypted payload is missing kdf metadata")
        return cls(
            version=version,
            salt_b64=str(payload["salt"]),
            nonce_b64=str(payload["nonce"]),
            ciphertext_b64=str(payload["ciphertext"]),
            tag_b64=str(payload["tag"]),
            kdf=KdfParams.from_dict(kdf_raw),
        )

    @classmethod
    def from_json(cls, text: str) -> EncryptedPayload:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Encrypted payload must be a JSON object")
        return cls.from_dict(data)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64decode(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text.encode("ascii"))
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("Invalid base64 payload") from exc


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = hmac.new(
            key,
            STREAM_LABEL + nonce + counter.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _xor_bytes(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream, strict=True))


def _mac(key: bytes, nonce: bytes, ciphertext: bytes, params: KdfParams) -> bytes:
    header = (
        MAGIC.encode("ascii")
        + b"\x01"
        + params.digest.encode("ascii")
        + params.iterations.to_bytes(4, "big")
        + params.length.to_bytes(4, "big")
    )
    return hmac.new(key, MAC_LABEL + header + nonce + ciphertext, hashlib.sha256).digest()


def encrypt_bytes(
    plaintext: bytes,
    passphrase: str,
    *,
    params: KdfParams | None = None,
    salt: bytes | None = None,
    nonce: bytes | None = None,
    associated_data: bytes = b"",
) -> EncryptedPayload:
    """Encrypt bytes with a passphrase and return a serializable payload."""
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("plaintext must be bytes")
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    if not isinstance(associated_data, (bytes, bytearray)):
        raise TypeError("associated_data must be bytes")

    params = params or KdfParams()
    salt_bytes = salt if salt is not None else secrets.token_bytes(params.salt_bytes)
    nonce_bytes = nonce if nonce is not None else secrets.token_bytes(DEFAULT_NONCE_BYTES)
    if len(salt_bytes) < 8:
        raise ValueError("salt must be at least 8 bytes")
    if len(nonce_bytes) < 8:
        raise ValueError("nonce must be at least 8 bytes")

    material = derive_key_material(passphrase, salt_bytes, params=params)
    stream_key = material[:32]
    mac_key = material[32:] if len(material) >= 64 else hashlib.sha256(material).digest()
    stream = _keystream(stream_key, nonce_bytes + bytes(associated_data), len(plaintext))
    ciphertext = _xor_bytes(bytes(plaintext), stream)
    tag = _mac(mac_key, nonce_bytes + bytes(associated_data), ciphertext, params)
    return EncryptedPayload(
        version=1,
        salt_b64=_b64encode(salt_bytes),
        nonce_b64=_b64encode(nonce_bytes),
        ciphertext_b64=_b64encode(ciphertext),
        tag_b64=_b64encode(tag),
        kdf=params,
    )


def decrypt_bytes(
    payload: EncryptedPayload | Mapping[str, Any] | str,
    passphrase: str,
    *,
    associated_data: bytes = b"",
) -> bytes:
    """Decrypt a payload produced by :func:`encrypt_bytes`."""
    if isinstance(payload, str):
        envelope = EncryptedPayload.from_json(payload)
    elif isinstance(payload, EncryptedPayload):
        envelope = payload
    elif isinstance(payload, Mapping):
        envelope = EncryptedPayload.from_dict(dict(payload))
    else:
        raise TypeError("payload must be EncryptedPayload, mapping, or JSON string")
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    if not isinstance(associated_data, (bytes, bytearray)):
        raise TypeError("associated_data must be bytes")

    salt = _b64decode(envelope.salt_b64)
    nonce = _b64decode(envelope.nonce_b64)
    ciphertext = _b64decode(envelope.ciphertext_b64)
    expected_tag = _b64decode(envelope.tag_b64)
    material = derive_key_material(passphrase, salt, params=envelope.kdf)
    stream_key = material[:32]
    mac_key = material[32:] if len(material) >= 64 else hashlib.sha256(material).digest()
    actual_tag = _mac(mac_key, nonce + bytes(associated_data), ciphertext, envelope.kdf)
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise ValueError("Decryption failed: authentication tag mismatch")
    stream = _keystream(stream_key, nonce + bytes(associated_data), len(ciphertext))
    return _xor_bytes(ciphertext, stream)


def encrypt_text(
    plaintext: str,
    passphrase: str,
    *,
    params: KdfParams | None = None,
    associated_data: str = "",
) -> dict[str, Any]:
    """Encrypt UTF-8 text and return a JSON-serializable payload dict."""
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be a string")
    payload = encrypt_bytes(
        plaintext.encode("utf-8"),
        passphrase,
        params=params,
        associated_data=associated_data.encode("utf-8"),
    )
    return payload.to_dict()


def decrypt_text(
    payload: EncryptedPayload | Mapping[str, Any] | str,
    passphrase: str,
    *,
    associated_data: str = "",
) -> str:
    """Decrypt UTF-8 text from a payload produced by :func:`encrypt_text`."""
    data = decrypt_bytes(payload, passphrase, associated_data=associated_data.encode("utf-8"))
    return data.decode("utf-8")
