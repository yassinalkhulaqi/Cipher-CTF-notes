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
