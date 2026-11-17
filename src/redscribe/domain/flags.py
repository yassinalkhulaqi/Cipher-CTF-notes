"""CTF flag detection for note content."""

from __future__ import annotations

import re

FLAG_PREFIXES: tuple[str, ...] = (
    "flag",
    "ctf",
    "htb",
    "thm",
    "picoctf",
    "nite",
    "uiuctf",
    "ductf",
    "bcactf",
    "csawctf",
    "csaw",
    "hitcon",
    "ictf",
    "sekai",
    "idek",
    "wctf",
    "justctf",
    "crew",
    "vsctf",
    "corctf",
    "lactf",
    "buckeye",
    "utflag",
    "sdctf",
    "nahamcon",
    "shakti",
    "irisctf",
    "maple",
    "amateursctf",
    "tjctf",
    "angstromctf",
    "hacktoday",
    "grey",
    "ractf",
    "zh3r0",
    "pbctf",
    "damctf",
    "rgbctf",
    "hsctf",
    "csictf",
    "flagyard",
)

_PREFIX_PATTERN = "|".join(
    re.escape(prefix) for prefix in sorted(FLAG_PREFIXES, key=len, reverse=True)
)
FLAG_RE = re.compile(
    rf"(?<![\w])(?:{_PREFIX_PATTERN})\{{[^}}\r\n]{{1,256}}\}}",
    re.IGNORECASE,
)


def find_flags(text: str) -> list[str]:
    """Return unique flags found in text, preserving order."""
    seen: set[str] = set()
    results: list[str] = []
    for match in FLAG_RE.finditer(text):
        value = match.group(0)
        if value not in seen:
            seen.add(value)
            results.append(value)
    return results


def primary_flag(text: str) -> str | None:
    """Return the first flag in text, if any."""
    flags = find_flags(text)
    return flags[0] if flags else None


def has_flag(text: str) -> bool:
    return FLAG_RE.search(text) is not None


def merge_flags(*values: str) -> list[str]:
    """Merge flags from several strings into a unique ordered list."""
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        for flag in find_flags(value):
            if flag not in seen:
                seen.add(flag)
                results.append(flag)
    return results


def clean_flag(value: str) -> str:
    """Return a flag value without surrounding quotes or whitespace."""
    return value.strip().strip("\"'").strip()


def flag_prefix(value: str) -> str:
    """Return the prefix before the first brace, or an empty string."""
    cleaned = clean_flag(value)
    return cleaned.split("{", 1)[0] if "{" in cleaned else ""


def flag_body(value: str) -> str:
    """Return the payload inside a balanced ``prefix{body}`` pair."""
    cleaned = clean_flag(value)
    if "{" not in cleaned or not cleaned.endswith("}"):
        return ""
    body = cleaned.split("{", 1)[1][:-1]
    if "{" in body or "}" in body:
        return ""
    return body


def flag_fingerprint(value: str) -> str:
    """Return a deduplication key that normalizes the prefix only."""
    cleaned = clean_flag(value)
    prefix, body = flag_prefix(cleaned), flag_body(cleaned)
    if prefix and body:
        return f"{prefix.lower()}{{{body}}}"
    return cleaned.casefold()


def flags_by_prefix(text: str) -> dict[str, list[str]]:
    """Group every detected flag by its lowercased prefix."""
    grouped: dict[str, list[str]] = {}
    for flag in find_flags(text):
        grouped.setdefault(flag_prefix(flag).lower(), []).append(flag)
    return grouped
