"""Canonical serialization and digest helpers for portable bundles."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from redscribe.v3.portability.errors import PortabilityError

MAX_CANONICAL_DEPTH = 32


def canonical_bytes(payload: Any) -> bytes:
    """Serialize a JSON-compatible value with stable key and separator rules."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    """Return the hexadecimal SHA-256 digest of a byte string."""
    return hashlib.sha256(payload).hexdigest()


def digest_value(payload: Any) -> str:
    """Return the digest of a canonical JSON value."""
    return sha256_hex(canonical_bytes(payload))


def digest_entity(payload: dict[str, Any]) -> str:
    """Return the verified checksum of one portable entity."""
    return digest_value(
        {
            "record": payload.get("record", {}),
            "vector": payload.get("vector", {}),
            "body": payload.get("body", ""),
            "deleted": payload.get("deleted", False),
        }
    )


def digest_collection(
    entities: tuple[dict[str, Any], ...], links: tuple[dict[str, Any], ...]
) -> str:
    """Return the payload digest of a complete entity/link collection."""
    return digest_value(
        {
            "entities": [digest_entity(entity) for entity in entities],
            "links": [digest_value(link) for link in links],
        }
    )


def ensure_json_safe(payload: Any, *, path: str = "$", depth: int = 0) -> None:
    """Reject values that cannot be represented in a portable JSON bundle."""
    if depth > MAX_CANONICAL_DEPTH:
        raise PortabilityError(f"Payload is too deeply nested at {path}")
    if payload is None or isinstance(payload, (str, int, bool)):
        return
    if isinstance(payload, float):
        if payload != payload or payload in (float("inf"), float("-inf")):
            raise PortabilityError(f"Non-finite number at {path}")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(key, str) or not key:
                raise PortabilityError(f"Invalid object key at {path}")
            ensure_json_safe(value, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            ensure_json_safe(value, path=f"{path}[{index}]", depth=depth + 1)
        return
    raise PortabilityError(f"Unsupported value type at {path}: {type(payload).__name__}")
