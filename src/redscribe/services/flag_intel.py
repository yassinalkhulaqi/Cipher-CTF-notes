"""Flag intelligence: known event flag formats, format validation, and insights."""

from __future__ import annotations

import dataclasses
import re
from collections import Counter

from redscribe.domain.flags import FLAG_PREFIXES, find_flags
from redscribe.storage.db import Vault

CURATED_DISPLAY: dict[str, str] = {
    "htb": "HTB",
    "thm": "THM",
    "picoctf": "picoCTF",
    "csaw": "CSAW",
    "csawctf": "csawCTF",
    "ductf": "DUCTF",
    "bcactf": "bcaCTF",
    "corctf": "corCTF",
    "lactf": "LACTF",
    "sekai": "SekaiCTF",
    "justctf": "JustCTF",
    "tjctf": "TJCTF",
    "angstromctf": "angstromCTF",
    "irisctf": "irisCTF",
    "amateursctf": "amateursCTF",
    "nahamcon": "NahamCon",
    "hsctf": "HSCTF",
    "hitcon": "HITCON",
    "idek": "idek",
    "grey": "grey",
}

CURATED_PLATFORM: dict[str, str] = {
    "htb": "Hack The Box",
    "thm": "TryHackMe",
    "picoctf": "picoCTF",
    "flag": "Generic",
    "ctf": "Generic",
    "csaw": "CSAW CTF",
    "csawctf": "CSAW CTF",
    "ductf": "DownUnderCTF",
    "bcactf": "BuckeyeCTF",
    "corctf": "corCTF",
    "lactf": "LA CTF",
    "sekai": "SekaiCTF",
    "justctf": "Just CTF",
    "tjctf": "TJ CTF",
    "angstromctf": "Angstrom CTF",
    "irisctf": "IrisCTF",
    "amateursctf": "AmateursCTF",
    "nahamcon": "NahamCon",
    "hsctf": "HSCTF",
    "hitcon": "HITCON",
    "idek": "IDEK CTF",
    "grey": "GreyCTF",
}

CURATED_HINT: dict[str, str] = {
    "htb": "words or hex, 4-63 chars",
    "thm": "words, usually 20+ chars",
    "picoctf": "snake_case words",
}

CURATED_CATEGORY: dict[str, str] = {
    "htb": "htb",
    "thm": "thm",
    "picoctf": "picoctf",
}

GENERIC_HINT = "any content inside braces"

PREFERRED_PREFIXES: tuple[str, ...] = (
    "flag",
    "ctf",
    "htb",
    "thm",
    "picoctf",
    "csaw",
    "ductf",
    "corctf",
    "lactf",
    "sekai",
)


@dataclasses.dataclass(frozen=True, slots=True)
class FlagPattern:
    """A known event flag prefix with metadata for hints and autocomplete."""

    prefix: str
    pattern_key: str
    platform: str
    example: str
    hint: str
    category: str


def _build_patterns() -> tuple[FlagPattern, ...]:
    patterns: list[FlagPattern] = []
    for key in FLAG_PREFIXES:
        display = CURATED_DISPLAY.get(key, key)
        platform = CURATED_PLATFORM.get(key, f"{key.upper()} CTF")
        hint = CURATED_HINT.get(key, GENERIC_HINT)
        category = CURATED_CATEGORY.get(key, "generic" if key == "flag" else "ctf")
        patterns.append(
            FlagPattern(
                prefix=display,
                pattern_key=key,
                platform=platform,
                example=f"{display}{{...}}",
                hint=hint,
                category=category,
            )
        )
    preferred_rank = {key: rank for rank, key in enumerate(PREFERRED_PREFIXES)}
    original_rank = {key: rank for rank, key in enumerate(FLAG_PREFIXES)}
    patterns.sort(
        key=lambda pattern: (
            preferred_rank.get(pattern.pattern_key, len(PREFERRED_PREFIXES)),
            original_rank.get(pattern.pattern_key, len(FLAG_PREFIXES)),
        )
    )
    return tuple(patterns)


KNOWN_FLAG_PATTERNS: tuple[FlagPattern, ...] = _build_patterns()

PATTERNS_BY_PREFIX: dict[str, FlagPattern] = {
    pattern.pattern_key: pattern for pattern in KNOWN_FLAG_PATTERNS
}

_FLAG_FORMAT_RE = re.compile(r"^(\w[\w-]*)\{(.*)\}$", re.DOTALL)


@dataclasses.dataclass(frozen=True, slots=True)
class FlagCheck:
    """The result of validating a single flag value."""

    ok: bool
    known_prefix: bool
    prefix: str
    platform: str
    hint: str
    value_length: int


@dataclasses.dataclass(frozen=True, slots=True)
class FlagSourceCount:
    """How many collected flags come from one event prefix."""

    prefix: str
    platform: str
    count: int


@dataclasses.dataclass(frozen=True, slots=True)
class DuplicateFlag:
    """A flag value captured on more than one note."""

    flag: str
    note_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class FlagInsights:
    """Aggregate flag statistics for the dashboard."""

    unique_flags: int
    manual_flags: int
    detected_flags: int
    by_source: tuple[FlagSourceCount, ...]
    duplicates: tuple[DuplicateFlag, ...]
    missing_flag_notes: int


def check_flag(value: str) -> FlagCheck:
    """Validate a flag in ``prefix{value}`` format and report what is known."""
    raw = value.strip().strip("\"'")
    if not raw:
        return FlagCheck(
            ok=False,
            known_prefix=False,
            prefix="",
            platform="",
            hint="Flag is empty.",
            value_length=0,
        )
    match = _FLAG_FORMAT_RE.match(raw)
    if match is None:
        return FlagCheck(
            ok=False,
            known_prefix=False,
            prefix="",
            platform="",
            hint="Expected prefix{value} with balanced braces.",
            value_length=0,
        )
    prefix, body = match.group(1), match.group(2)
    if not body:
        return FlagCheck(
            ok=False,
            known_prefix=False,
            prefix=prefix,
            platform="",
            hint="The flag value inside the braces is empty.",
            value_length=0,
        )
    if "{" in body or "}" in body:
        return FlagCheck(
            ok=False,
            known_prefix=False,
            prefix=prefix,
            platform="",
            hint="The flag value must not contain braces.",
            value_length=len(body),
        )
    pattern = PATTERNS_BY_PREFIX.get(prefix.lower())
    if pattern is not None:
        return FlagCheck(
            ok=True,
            known_prefix=True,
            prefix=prefix,
            platform=pattern.platform,
            hint=pattern.hint,
            value_length=len(body),
        )
    return FlagCheck(
        ok=True,
        known_prefix=False,
        prefix=prefix,
        platform="",
        hint=f"Recognized format; {prefix} is not a known event prefix.",
        value_length=len(body),
    )


def _platform_for(prefix: str) -> str:
    if not prefix:
        return "Payload only"
    pattern = PATTERNS_BY_PREFIX.get(prefix)
    if pattern is not None:
        return pattern.platform
    return prefix.upper()


def build_flag_insights(vault: Vault) -> FlagInsights:
    """Aggregate flag statistics over the live vault."""
    hits = vault.collected_flags()
    manual_flags = sum(1 for hit in hits if hit.manual)
    unique_flags = len(hits)
    sources: Counter[str] = Counter()
    for hit in hits:
        flag = hit.flag
        prefix = flag.split("{", 1)[0].strip().lower() if "{" in flag else ""
        sources[prefix] += 1
    by_source = tuple(
        FlagSourceCount(prefix=prefix, platform=_platform_for(prefix), count=count)
        for prefix, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:10]
    )

    flag_notes: dict[str, set[int]] = {}
    missing_flag_notes = 0
    for node in vault.live_nodes():
        if not node.is_note:
            continue
        flags: set[str] = set()
        if node.flag:
            flags.add(node.flag)
        flags.update(find_flags(node.content))
        for flag in flags:
            flag_notes.setdefault(flag, set()).add(node.id)
        if node.status == "done" and not flags:
            missing_flag_notes += 1
    duplicates = tuple(
        DuplicateFlag(flag=flag, note_count=len(note_ids))
        for flag, note_ids in sorted(flag_notes.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(note_ids) > 1
    )[:10]

    return FlagInsights(
        unique_flags=unique_flags,
        manual_flags=manual_flags,
        detected_flags=unique_flags - manual_flags,
        by_source=by_source,
        duplicates=duplicates,
        missing_flag_notes=missing_flag_notes,
    )


def flag_patterns_payload() -> list[dict[str, str]]:
    """Return the known flag pattern registry as plain dicts."""
    return [dataclasses.asdict(pattern) for pattern in KNOWN_FLAG_PATTERNS]


def flag_insights_payload(insights: FlagInsights) -> dict[str, object]:
    """Return the JSON-serializable flag insights payload."""
    return {
        "unique_flags": insights.unique_flags,
        "manual_flags": insights.manual_flags,
        "detected_flags": insights.detected_flags,
        "by_source": [dataclasses.asdict(item) for item in insights.by_source],
        "duplicates": [dataclasses.asdict(item) for item in insights.duplicates],
        "missing_flag_notes": insights.missing_flag_notes,
    }
