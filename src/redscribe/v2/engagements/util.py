"""Small pure helpers shared by engagement domain modules."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_CLOCK: dict[str, Any] = {"now": None}


def now_iso() -> str:
    """Return the current UTC time in a stable ISO-8601 form."""
    fixed = _CLOCK["now"]
    if isinstance(fixed, str):
        return fixed
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def set_clock(value: str | None) -> None:
    """Pin or release the clock used by model timestamps in tests."""
    _CLOCK["now"] = value


def slugify(value: str, *, fallback: str = "item") -> str:
    """Return a lowercase, hyphen-separated identifier."""
    slug = _SLUG_PATTERN.sub("-", value.strip().casefold()).strip("-")
    return slug or fallback


def tokens(value: str) -> tuple[str, ...]:
    """Extract lowercase alphanumeric tokens from free text."""
    return tuple(_TOKEN_PATTERN.findall(value.casefold()))


def dedupe(values: Iterable[str], *, casefold: bool = True) -> list[str]:
    """Remove duplicates while preserving the first occurrence."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold() if casefold else value
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Clamp a numeric value to an inclusive range."""
    return min(max(value, minimum), maximum)


def digest(value: str) -> str:
    """Return a short stable hash for fingerprint-like values."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def mapping_get(data: Mapping[str, Any], key: str, default: Any = None) -> Any:
    """Read a key from a mapping with a stable default."""
    return data.get(key, default)


def format_number(value: float, *, digits: int = 1) -> str:
    """Format a float for compact UI surfaces."""
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def truncate(value: str, *, limit: int = 80, suffix: str = "...") -> str:
    """Trim long text to a display-friendly length."""
    if len(value) <= limit:
        return value
    if limit <= len(suffix):
        return value[:limit]
    return value[: limit - len(suffix)].rstrip() + suffix


def parse_bool(value: str | bool | None, *, default: bool = False) -> bool:
    """Parse a request-style boolean value."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = value.strip().casefold()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default
