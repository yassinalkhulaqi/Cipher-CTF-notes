"""Deterministic identifiers, digests, and anchors for report designs.

Every value produced here is a pure function of its inputs. The report designer
relies on that property so two designs with the same logical content render
byte-for-byte identical output, including anchors and manifest digests.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

_WORD_RE = re.compile(r"[^a-z0-9]+")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ANCHOR_RE = re.compile(r"[^a-z0-9]+")


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value with stable keys and compact separators."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def digest(value: Any) -> str:
    """Return a SHA-256 digest of the canonical JSON form of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_text(text: str) -> str:
    """Return a SHA-256 digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(value: str, *, fallback: str = "item", max_length: int = 72) -> str:
    """Convert human text to a stable lowercase slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _WORD_RE.sub("-", ascii_text.casefold()).strip("-")
    return slug[:max_length].rstrip("-") or fallback


def is_identifier(value: str) -> bool:
    """Return whether ``value`` is safe as a machine identifier."""
    return bool(_IDENTIFIER_RE.fullmatch(value))


def unique_slug(value: str, used: set[str] | frozenset[str]) -> str:
    """Return ``value`` or a numeric variant not present in ``used``."""
    base = slugify(value)
    if base not in used:
        return base
    counter = 2
    while f"{base}-{counter}" in used:
        counter += 1
    return f"{base}-{counter}"


def anchor_for(section_id: str) -> str:
    """Return the stable HTML anchor for a section identifier."""
    return f"sec-{slugify(section_id, fallback='section')}"


def page_anchor(page_index: int) -> str:
    """Return the stable anchor for a page number (one-based)."""
    if page_index < 1:
        raise ValueError("Page index must be positive")
    return f"page-{page_index}"


def page_label(page_index: int, total_pages: int) -> str:
    """Return a human-readable page label."""
    if page_index < 1 or total_pages < 1:
        raise ValueError("Page numbers must be positive")
    return f"Page {page_index} of {total_pages}"


def short_hash(value: str, *, length: int = 12) -> str:
    """Return a short human-readable hash suffix."""
    if length < 4 or length > 64:
        raise ValueError("length must be between 4 and 64")
    return digest_text(value)[:length]


def stable_id(prefix: str, *parts: object) -> str:
    """Build a stable identifier from a prefix and ordered parts."""
    cleaned = slugify(prefix, fallback="item")
    rendered = [str(part) for part in parts if str(part).strip()]
    if not rendered:
        return cleaned
    return f"{cleaned}-{short_hash(canonical_json(rendered), length=10)}"


def anchor_value(anchor: str) -> str:
    """Normalize a free-form anchor string for use in a URL fragment."""
    normalized = unicodedata.normalize("NFKD", anchor)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = _ANCHOR_RE.sub("-", ascii_text.casefold()).strip("-")
    return cleaned or "section"
