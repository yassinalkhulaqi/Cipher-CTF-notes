"""Multi-hash provenance panel (SHA-256 + BLAKE2b).

Digests are always computed by streaming fixed-size chunks. Verification is
constant-time and gracefully handles a stored record that only carries one of
the two digests.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import BinaryIO

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.types import (
    DEFAULT_CHUNK_SIZE,
    HashDigest,
    HashPanel,
    IntegrityBadge,
    IntegrityState,
    normalize_hex_digest,
)

SHA256_HEX_LENGTH = 64
DEFAULT_BLAKE2B_SIZE = 32


def validate_chunk_size(chunk_size: int) -> int:
    """Validate a streaming chunk size."""
    if chunk_size < 4_096 or chunk_size > 8 * 1024 * 1024:
        raise InvalidInputError("chunk_size must be between 4096 and 8388608")
    return chunk_size


def validate_digest_size(size: int) -> int:
    """Validate a BLAKE2b digest size."""
    if not 16 <= size <= 64:
        raise InvalidInputError("BLAKE2b digest size must be between 16 and 64")
    return size


def normalize_expected(value: str, *, length: int) -> str:
    """Normalize an expected digest or return an empty string."""
    if not value:
        return ""
    return normalize_hex_digest(value, length=length)


def hash_stream_panel(
    stream: BinaryIO,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    digest_size: int = DEFAULT_BLAKE2B_SIZE,
    computed_at: str = "",
    expected_sha256: str = "",
    expected_blake2b: str = "",
) -> HashPanel:
    """Compute both digests by streaming a binary file-like object."""
    validate_chunk_size(chunk_size)
    validate_digest_size(digest_size)
    sha = hashlib.sha256()
    blake = hashlib.blake2b(digest_size=digest_size)
    total = 0
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        sha.update(chunk)
        blake.update(chunk)
        total += len(chunk)
    return HashPanel(
        sha256=sha.hexdigest(),
        blake2b=blake.hexdigest(),
        size_bytes=total,
        computed_at=computed_at,
        blake2b_size=digest_size,
        expected_sha256=normalize_expected(expected_sha256, length=SHA256_HEX_LENGTH),
        expected_blake2b=normalize_expected(expected_blake2b, length=digest_size * 2),
    )


def compute_panel(
    data: bytes,
    *,
    computed_at: str = "",
    digest_size: int = DEFAULT_BLAKE2B_SIZE,
    expected_sha256: str = "",
    expected_blake2b: str = "",
) -> HashPanel:
    """Compute a hash panel from an in-memory byte string."""
    from io import BytesIO

    with BytesIO(data) as stream:
        return hash_stream_panel(
            stream,
            computed_at=computed_at,
            digest_size=digest_size,
            expected_sha256=expected_sha256,
            expected_blake2b=expected_blake2b,
        )


def digest_equal(actual: str, expected: str) -> bool:
    """Compare two digests in constant time when an expectation exists."""
    if not expected:
        return False
    return hmac.compare_digest(actual.casefold(), expected.strip().casefold())


def verify_panel(
    panel: HashPanel,
    *,
    stored_sha256: str = "",
    stored_blake2b: str = "",
    stored_size: int | None = None,
) -> IntegrityBadge:
    """Compare a live panel with a stored provenance record."""
    sha_expected = normalize_expected(
        stored_sha256 or panel.expected_sha256, length=SHA256_HEX_LENGTH
    )
    blake_expected = normalize_expected(
        stored_blake2b or panel.expected_blake2b, length=panel.blake2b_size * 2
    )
    sha_match = digest_equal(panel.sha256, sha_expected) if sha_expected else False
    blake_match = digest_equal(panel.blake2b, blake_expected) if blake_expected else False
    size_match = stored_size is None or stored_size == panel.size_bytes
    reasons: list[str] = []
    if sha_expected and not sha_match:
        reasons.append("sha256 mismatch")
    if blake_expected and not blake_match:
        reasons.append("blake2b mismatch")
    if not size_match:
        reasons.append("size mismatch")
    if reasons:
        state = IntegrityState.MISMATCH
    elif sha_expected or blake_expected or stored_size is not None:
        state = IntegrityState.VERIFIED
    else:
        state = IntegrityState.UNVERIFIED
    return IntegrityBadge(
        state=state,
        sha256_match=sha_match,
        blake2b_match=blake_match,
        size_match=size_match,
        reasons=tuple(reasons),
    )


def panel_digests(panel: HashPanel) -> tuple[HashDigest, ...]:
    """Return the panel as a list of named digests."""
    return (
        HashDigest("sha256", panel.sha256, panel.size_bytes),
        HashDigest("blake2b", panel.blake2b, panel.size_bytes),
    )


def panel_fingerprint(panel: HashPanel) -> str:
    """Return a single content fingerprint for the panel."""
    return f"sha256:{panel.sha256}|blake2b:{panel.blake2b}"


def compare_panels(left: HashPanel, right: HashPanel) -> dict[str, object]:
    """Return a field-by-field comparison of two panels."""
    return {
        "sha256": digest_equal(left.sha256, right.sha256),
        "blake2b": digest_equal(left.blake2b, right.blake2b),
        "size": left.size_bytes == right.size_bytes,
        "same_digest_size": left.blake2b_size == right.blake2b_size,
    }


def mask_hex(value: str, *, visible: int = 8) -> str:
    """Return a shortened hex digest for compact UI chips."""
    if len(value) <= visible * 2 + 3:
        return value
    return f"{value[:visible]}...{value[-visible:]}"
