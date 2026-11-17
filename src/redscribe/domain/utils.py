"""Small, dependency-free helpers shared across RedScribe."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
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


def iso_z(moment: datetime) -> str:
    """Format a datetime as a UTC ISO 8601 string with a ``Z`` suffix."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relative_time(value: str, *, now: datetime | None = None, long: bool = False) -> str:
    """Render a timestamp as ``3m ago`` or ``in 3 minutes``.

    Unlike :func:`humanize_delta`, future timestamps are described instead of
    being collapsed to ``just now``. Invalid input still yields an empty string.
    """
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    current = now or datetime.now(timezone.utc)
    seconds = int((current - parsed).total_seconds())
    if abs(seconds) < 45:
        return "just now"
    units: tuple[tuple[int, str, str], ...] = (
        (31_536_000, "year", "y"),
        (2_592_000, "month", "mo"),
        (604_800, "week", "w"),
        (86_400, "day", "d"),
        (3_600, "hour", "h"),
        (60, "minute", "m"),
    )
    amount = 1
    unit_name = "second"
    short = "s"
    for unit_seconds, candidate_name, candidate_short in units:
        if abs(seconds) >= unit_seconds:
            amount = abs(seconds) // unit_seconds
            unit_name = candidate_name
            short = candidate_short
            break
    if long:
        noun = f"{unit_name}{'' if amount == 1 else 's'}"
        return f"{amount} {noun} ago" if seconds > 0 else f"in {amount} {noun}"
    label = f"{amount}{short}"
    return f"{label} ago" if seconds > 0 else f"in {label}"


def format_duration(milliseconds: float) -> str:
    """Format an elapsed duration for human-readable CLI reports."""
    if milliseconds < 10:
        return f"{milliseconds:.1f}ms"
    if milliseconds < 1_000:
        return f"{milliseconds:.0f}ms"
    if milliseconds < 60_000:
        return f"{milliseconds / 1_000:.2f}s"
    return f"{milliseconds / 60_000:.1f}m"


def unique_slug(
    text: str,
    existing: Iterable[str],
    *,
    fallback: str = "note",
    max_length: int = 60,
) -> str:
    """Return a slug not present in ``existing``, adding a numeric suffix."""
    base = slugify(text, fallback=fallback, max_length=max_length)
    taken = set(existing)
    if base not in taken:
        return base
    counter = 2
    while True:
        suffix = f"-{counter}"
        room = max_length - len(suffix)
        candidate = f"{base[:room].rstrip('-')}{suffix}" if room > 0 else suffix[:max_length]
        if candidate not in taken:
            return candidate
        counter += 1


def slug_hash(text: str, *, length: int = 8) -> str:
    """Return a stable short hexadecimal digest for fixture identifiers."""
    size = max(1, min(64, length))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]
