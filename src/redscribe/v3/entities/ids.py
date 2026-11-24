"""Identifier generation and parsing helpers for V3 entities."""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Final

from redscribe.v3.entities.types import EntityId, EntityKind

_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def is_valid_value(value: str) -> bool:
    """Return whether a raw id value is safe for storage and URLs."""
    return bool(_ID_PATTERN.fullmatch(value))


def new_value(kind: EntityKind | str, *, prefix: str = "") -> str:
    """Generate a random, URL-safe id value with an optional prefix."""
    if not isinstance(kind, EntityKind):
        EntityKind.parse(kind)
    seed = secrets.token_bytes(12)
    digest = hashlib.blake2b(seed, digest_size=10).digest()
    number = int.from_bytes(digest, "big")
    suffix_chars: list[str] = []
    for _ in range(16):
        number, index = divmod(number, len(_ALPHABET))
        suffix_chars.append(_ALPHABET[index])
    suffix = "".join(reversed(suffix_chars))
    clean_prefix = re.sub(r"[^a-z0-9]+", "-", prefix.strip().casefold()).strip("-")
    return f"{clean_prefix}_{suffix}" if clean_prefix else suffix


def new_id(kind: EntityKind | str, *, prefix: str = "") -> EntityId:
    """Generate a fresh typed entity id."""
    parsed = kind if isinstance(kind, EntityKind) else EntityKind.parse(kind)
    return EntityId(parsed, new_value(parsed, prefix=prefix))


def slugify(value: str, *, max_length: int = 64) -> str:
    """Convert human text into a stable, readable id fragment."""
    lowered = value.strip().casefold()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = replaced.strip("-")
    return slug[:max_length].rstrip("-") or "item"


def try_parse(raw: str) -> EntityId | None:
    """Parse an entity id, returning ``None`` instead of raising."""
    try:
        return EntityId.parse(raw)
    except ValueError:
        return None


def short_form(entity_id: EntityId, *, length: int = 8) -> str:
    """Return a truncated human-friendly form for logs and badges."""
    if length < 4:
        raise ValueError("Short form length must be at least 4")
    return f"{entity_id.kind.value[:3]}:{entity_id.value[:length]}"
