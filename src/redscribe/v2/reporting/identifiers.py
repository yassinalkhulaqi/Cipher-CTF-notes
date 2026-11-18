"""Deterministic identifiers and digests used by the reporting studio."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

SLUG_SEPARATOR = "-"
_WORD_RE = re.compile(r"[^a-z0-9]+")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def canonical_json(value: Any) -> str:
    """Serialize a JSON value with stable key order and compact separators."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def digest(value: Any) -> str:
    """Return a SHA-256 digest of a canonical JSON value."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_text(value: str) -> str:
    """Return a SHA-256 digest of a UTF-8 string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str, *, fallback: str = "item", max_length: int = 72) -> str:
    """Convert human text to a stable lowercase slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _WORD_RE.sub(SLUG_SEPARATOR, ascii_text.casefold()).strip(SLUG_SEPARATOR)
    slug = slug[:max_length].rstrip(SLUG_SEPARATOR)
    return slug or fallback


def is_identifier(value: str) -> bool:
    """Return whether ``value`` is a safe machine identifier."""
    return bool(_IDENTIFIER_RE.fullmatch(value))


def unique_identifier(value: str, used: set[str] | frozenset[str]) -> str:
    """Return ``value`` or a numbered variant not present in ``used``."""
    base = slugify(value)
    if base not in used:
        return base
    counter = 2
    while f"{base}-{counter}" in used:
        counter += 1
    return f"{base}-{counter}"


def short_hash(value: str, *, length: int = 12) -> str:
    """Return a short, human-readable hash suffix."""
    if length < 4 or length > 64:
        raise ValueError("length must be between 4 and 64")
    return digest_text(value)[:length]


def citation_label(prefix: str, *parts: object) -> str:
    """Build a compact citation label from a prefix and ordered parts."""
    rendered = [str(part).strip() for part in parts if str(part).strip()]
    label = f"{prefix}:{':'.join(rendered)}" if rendered else prefix
    return slugify(label, fallback=slugify(prefix))
