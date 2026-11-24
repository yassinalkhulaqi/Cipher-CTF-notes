"""Deterministic encoding helpers shared by compiler, traces and stores."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize JSON data with stable key order and compact separators."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any, *, size: int = 16) -> str:
    """Return a stable blake2b digest over canonical JSON."""
    return hashlib.blake2b(canonical_json(value).encode("utf-8"), digest_size=size).hexdigest()


def chain_digest(previous: str, value: Any) -> str:
    """Extend a hash chain with one value."""
    return digest([previous, canonical_json(value)])


def copy_value(value: Any) -> Any:
    """Return a detached deep copy of JSON-like data."""
    return deepcopy(value)


def flatten(value: Any, *, prefix: str = "") -> dict[str, Any]:
    """Flatten nested mappings into dotted paths for field-level diffs."""
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (dict, list)):
                result.update(flatten(item, prefix=path))
            else:
                result[path] = item
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            if isinstance(item, (dict, list)):
                result.update(flatten(item, prefix=path))
            else:
                result[path] = item
    elif prefix:
        result[prefix] = value
    return result


def redact_value(value: Any, *, secrets: frozenset[str] = frozenset()) -> Any:
    """Mask keys whose names look like secrets, recursively."""
    if isinstance(value, dict):
        return {
            key: "***" if str(key).casefold() in secrets else redact_value(item, secrets=secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item, secrets=secrets) for item in value]
    return value
