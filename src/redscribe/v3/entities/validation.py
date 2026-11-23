"""Validation helpers shared by every V3 feature model."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

MAX_TITLE_LENGTH = 240
MAX_SUMMARY_LENGTH = 4000
MAX_TAG_LENGTH = 64
MAX_TAGS = 64

_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,63}$")


def clean_text(value: str, *, limit: int = MAX_TITLE_LENGTH) -> str:
    """Normalize whitespace and enforce a length limit."""
    cleaned = " ".join(value.split())
    if len(cleaned) > limit:
        raise ValueError(f"Text exceeds {limit} characters")
    return cleaned


def normalize_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Normalize, deduplicate, and sort a tag collection."""
    normalized: set[str] = set()
    for tag in tags:
        candidate = tag.strip().strip("#").casefold()
        if not candidate:
            continue
        if len(candidate) > MAX_TAG_LENGTH:
            raise ValueError(f"Tag exceeds {MAX_TAG_LENGTH} characters")
        if not _TAG_PATTERN.fullmatch(candidate):
            raise ValueError(f"Invalid tag: {tag}")
        normalized.add(candidate)
    if len(normalized) > MAX_TAGS:
        raise ValueError(f"At most {MAX_TAGS} tags are allowed")
    return tuple(sorted(normalized))


def require_string(payload: Mapping[str, Any], key: str, *, limit: int = MAX_TITLE_LENGTH) -> str:
    """Return a required, cleaned string field."""
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Field '{key}' must be a string")
    return clean_text(value, limit=limit)


def optional_string(
    payload: Mapping[str, Any], key: str, *, default: str = "", limit: int = MAX_SUMMARY_LENGTH
) -> str:
    """Return an optional cleaned string field."""
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"Field '{key}' must be a string")
    return clean_text(value, limit=limit)


def require_number(payload: Mapping[str, Any], key: str, *, minimum: float = 0.0) -> float:
    """Return a required numeric field within bounds."""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Field '{key}' must be a number")
    number = float(value)
    if number < minimum:
        raise ValueError(f"Field '{key}' must be at least {minimum}")
    return number


def check_metadata(metadata: Mapping[str, Any], *, max_keys: int = 64) -> dict[str, Any]:
    """Validate a metadata mapping for JSON persistence."""
    if len(metadata) > max_keys:
        raise ValueError(f"Metadata supports at most {max_keys} keys")
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise ValueError("Metadata keys must be 1-64 character strings")
        if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
            raise ValueError(f"Unsupported metadata value for '{key}'")
        result[key] = value
    return result
