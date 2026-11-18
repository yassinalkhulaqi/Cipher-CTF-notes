"""Hashing and canonical digest helpers for evidence files.

MD5 is computed for compatibility with legacy manifests only. SHA-256 is the
authoritative digest used for integrity decisions.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO

from redscribe.v2.evidence.models import DigestSet
from redscribe.v2.evidence.validation import now_iso

DEFAULT_CHUNK_SIZE = 1024 * 1024
SHA256_LENGTH = 64
MD5_LENGTH = 32
SUPPORTED_ALGORITHMS = ("sha256", "md5")


def hash_with(data: bytes, algorithm: str) -> str:
    """Hex digest one byte string with a supported algorithm."""
    normalized = algorithm.strip().casefold()
    if normalized not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    return hashlib.new(normalized, data).hexdigest()


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def md5_hex(data: bytes) -> str:
    """Return the MD5 hex digest of ``data`` for manifest compatibility."""
    return hashlib.md5(data).hexdigest()


def hash_bytes(data: bytes, *, computed_at: str = "") -> DigestSet:
    """Compute the complete digest set for an in-memory byte string."""
    return DigestSet(
        sha256=sha256_hex(data),
        md5=md5_hex(data),
        size_bytes=len(data),
        computed_at=computed_at or now_iso(),
    )


def hash_stream(
    stream: BinaryIO,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    computed_at: str = "",
) -> DigestSet:
    """Compute digests by streaming a binary file-like object."""
    size = max(4_096, min(8 * 1024 * 1024, chunk_size))
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    total = 0
    while True:
        chunk = stream.read(size)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise TypeError("Binary streams must return bytes")
        sha.update(chunk)
        md5.update(chunk)
        total += len(chunk)
    return DigestSet(
        sha256=sha.hexdigest(),
        md5=md5.hexdigest(),
        size_bytes=total,
        computed_at=computed_at or now_iso(),
    )


def hash_file(
    path: str | Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    computed_at: str = "",
) -> DigestSet:
    """Compute digests for a file without loading it entirely into memory."""
    target = Path(path)
    with target.open("rb") as handle:
        return hash_stream(handle, chunk_size=chunk_size, computed_at=computed_at)


def verify_digest(data: bytes, expected: str, *, algorithm: str = "sha256") -> bool:
    """Compare a computed digest with an expected hex string in constant time."""
    if not isinstance(expected, str) or not expected:
        return False
    candidate = hash_with(data, algorithm)
    return hmac.compare_digest(candidate, expected.strip().casefold())


def verify_digest_set(data: bytes, digests: DigestSet) -> tuple[bool, bool]:
    """Return ``(sha256_ok, md5_ok)`` for a digest set."""
    return (
        verify_digest(data, digests.sha256, algorithm="sha256"),
        verify_digest(data, digests.md5, algorithm="md5"),
    )


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically for hashing and manifests."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def canonical_digest(value: Any) -> str:
    """Hash a canonical JSON representation of any JSON-safe value."""
    return sha256_hex(canonical_json(value).encode("utf-8"))


def chain_hash(previous: str, payload: Mapping[str, Any]) -> str:
    """Compute an append-only chain hash from a previous hash and payload."""
    body = {
        "previous": previous,
        "payload": dict(payload),
    }
    return canonical_digest(body)


def digest_matches(left: object, right: object) -> bool:
    """Compare two digest strings without leaking timing information."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    return hmac.compare_digest(left.strip().casefold(), right.strip().casefold())


def mask_digest(value: object, *, visible: int = 8) -> str:
    """Shorten a digest for compact display while keeping it identifiable."""
    if not isinstance(value, str):
        return ""
    size = max(4, min(32, visible))
    if len(value) <= size * 2 + 1:
        return value
    return f"{value[:size]}…{value[-size:]}"


def digest_label(algorithm: str) -> str:
    """Return a human-readable label for a digest algorithm."""
    normalized = algorithm.strip().casefold()
    if normalized == "sha256":
        return "SHA-256"
    if normalized == "md5":
        return "MD5 (compatibility)"
    return normalized.upper() or "Unknown"


def normalize_digest(value: object, *, length: int) -> str:
    """Normalize a digest to lowercase hex, or an empty string when invalid."""
    if not isinstance(value, str):
        return ""
    candidate = value.strip().casefold()
    if len(candidate) != length:
        return ""
    try:
        int(candidate, 16)
    except ValueError:
        return ""
    return candidate


def decode_base64_payload(value: object, *, max_bytes: int) -> bytes:
    """Decode a base64 payload, rejecting malformed or oversized input."""
    if not isinstance(value, str) or not value:
        raise ValueError("Base64 payload must be a non-empty string")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 payload") from exc
    if not data:
        raise ValueError("Base64 payload decodes to zero bytes")
    if len(data) > max_bytes:
        raise ValueError(f"Payload exceeds {max_bytes} bytes")
    return data


def encode_base64_payload(data: bytes) -> str:
    """Encode bytes as a base64 string for API transport."""
    return base64.b64encode(data).decode("ascii")


def digest_profile(data: bytes) -> dict[str, Any]:
    """Return a compact digest profile useful for API responses."""
    digests = hash_bytes(data)
    return {
        **digests.as_dict(),
        "sha256_short": mask_digest(digests.sha256),
        "md5_short": mask_digest(digests.md5),
    }


def compare_digest_sets(left: DigestSet, right: DigestSet) -> dict[str, bool]:
    """Compare all digest and size fields between two digest sets."""
    return {
        "sha256": digest_matches(left.sha256, right.sha256),
        "md5": digest_matches(left.md5, right.md5),
        "size": left.size_bytes == right.size_bytes,
    }


def flatten_digests(values: Sequence[DigestSet]) -> dict[str, str]:
    """Build an id-independent lookup of digests to evidence references."""
    result: dict[str, str] = {}
    for item in values:
        result[item.sha256] = item.sha256
        result[item.md5] = item.sha256
    return result
