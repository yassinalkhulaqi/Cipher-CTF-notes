"""Small, dependency-free helpers shared across RedScribe."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def utc_now() -> str:
    """Return the current UTC time as a second-precision ISO 8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO timestamp, treating naive values as UTC.

    Python 3.10's ``fromisoformat`` does not accept the ``Z`` suffix, so the
    value is normalized before parsing.
    """
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def humanize_delta(value: str, *, now: datetime | None = None, long: bool = False) -> str:
    """Render a timestamp as a relative time such as ``3m ago``.

    Set ``long`` for fully spelled units, for example ``2 hours ago``.
    """
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    current = now or datetime.now(timezone.utc)
    seconds = max(0, int((current - parsed).total_seconds()))
    units: tuple[tuple[int, str, str], ...] = (
        (31_536_000, "year", "y"),
        (2_592_000, "month", "mo"),
        (604_800, "week", "w"),
        (86_400, "day", "d"),
        (3_600, "hour", "h"),
        (60, "minute", "m"),
    )
    if seconds < 45:
        return "just now"
    for unit_seconds, unit_name, short in units:
        if seconds >= unit_seconds:
            amount = seconds // unit_seconds
            if long:
                suffix = "" if amount == 1 else "s"
                return f"{amount} {unit_name}{suffix} ago"
            return f"{amount}{short} ago"
    return "just now"


def slugify(text: str, *, fallback: str = "note", max_length: int = 60) -> str:
    """Return a filesystem- and URL-friendly slug."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_RE.sub("-", ascii_text).strip("-")
    if not slug:
        slug = fallback
    return slug[:max_length].strip("-") or fallback


def safe_filename(title: str, *, fallback: str = "note", extension: str = "") -> str:
    """Create a human-readable but safe filename stem."""
    cleaned = _INVALID_FILENAME_RE.sub("-", title).strip(" .")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)[:80].strip()
    if not cleaned:
        cleaned = fallback
    if extension:
        return f"{cleaned}{extension}"
    return cleaned


def word_count(text: str) -> int:
    """Count word-like tokens in Markdown text."""
    return len(_WORD_RE.findall(text))


def truncate(text: str, length: int, *, suffix: str = "…") -> str:
    """Trim text to ``length`` characters, appending an ellipsis."""
    collapsed = _WHITESPACE_RE.sub(" ", text).strip()
    if len(collapsed) <= length:
        return collapsed
    return collapsed[: max(1, length - len(suffix))].rstrip() + suffix


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


def format_number(value: int) -> str:
    return f"{value:,}"
