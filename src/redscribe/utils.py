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
    """Parse an ISO timestamp, treating naive values as UTC."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def humanize_delta(value: str, *, now: datetime | None = None) -> str:
    """Render a timestamp as a compact relative time such as ``3m ago``."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    current = now or datetime.now(timezone.utc)
    seconds = max(0, int((current - parsed).total_seconds()))
    if seconds < 45:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{days // 7}w ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


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
