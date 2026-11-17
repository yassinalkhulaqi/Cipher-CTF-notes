"""Format validation and uniqueness checks for CTF flags."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from redscribe.domain.flags import clean_flag, flag_fingerprint, flag_prefix
from redscribe.domain.models import FlagCandidate, ValidationIssue
from redscribe.domain.registry import FORMATS_BY_KEY, score_confidence

_SHAPE_RE = re.compile(r"^([A-Za-z0-9_-]+)\{([^{}]*)\}$")
_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class FormatValidation:
    """The outcome of validating one flag against the canonical format."""

    value: str
    ok: bool
    prefix: str
    body: str
    fingerprint: str
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True, slots=True)
class UniquenessReport:
    """Deduplication statistics for a collection of flag values."""

    total: int
    unique: int
    groups: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def duplicate_count(self) -> int:
        return sum(len(values) - 1 for _, values in self.groups)


@dataclass(frozen=True, slots=True)
class ScreenedFlag:
    """A candidate annotated with validation and confidence results."""

    value: str
    source: str
    ok: bool
    confidence: float
    issues: tuple[ValidationIssue, ...]


def validate_flag_format(value: str, *, max_length: int = 256) -> FormatValidation:
    """Check a flag for balanced braces, a valid prefix, and a sane payload."""
    cleaned = clean_flag(value)
    issues: list[ValidationIssue] = []
    match = _SHAPE_RE.match(cleaned)
    if match is None:
        issues.append(
            ValidationIssue(code="shape", message="Expected prefix{value} with balanced braces.")
        )
        return FormatValidation(
            value=cleaned,
            ok=False,
            prefix="",
            body="",
            fingerprint=flag_fingerprint(cleaned),
            issues=tuple(issues),
        )
    prefix, body = match.group(1), match.group(2)
    if _PREFIX_RE.match(prefix) is None:
        issues.append(ValidationIssue(code="prefix", message="Invalid flag prefix characters."))
    if not body:
        issues.append(ValidationIssue(code="body-empty", message="Flag payload is empty."))
    if len(cleaned) > max_length:
        issues.append(
            ValidationIssue(code="too-long", message=f"Flag exceeds {max_length} characters.")
        )
    if any(not char.isprintable() or char.isspace() for char in body):
        issues.append(ValidationIssue(code="body-chars", message="Flag payload has invalid chars."))
    if prefix.lower() not in FORMATS_BY_KEY:
        issues.append(
            ValidationIssue(
                code="unknown-prefix",
                message=f"{prefix} is not a registered event prefix.",
                severity="warning",
            )
        )
    return FormatValidation(
        value=cleaned,
        ok=not any(issue.severity == "error" for issue in issues),
        prefix=prefix,
        body=body,
        fingerprint=flag_fingerprint(cleaned),
        issues=tuple(issues),
    )


def unique_flags(values: Iterable[str], *, case_sensitive: bool = True) -> list[str]:
    """Return distinct flags in first-seen order, normalizing only the prefix."""
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        cleaned = clean_flag(value)
        key = flag_fingerprint(cleaned)
        if not case_sensitive:
            key = key.casefold()
        if key not in seen:
            seen.add(key)
            results.append(cleaned)
    return results


def find_duplicate_groups(
    values: Iterable[str], *, case_sensitive: bool = True
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Group flags that share a deduplication key, preserving first-seen order."""
    groups: dict[str, list[str]] = {}
    for value in values:
        cleaned = clean_flag(value)
        key = flag_fingerprint(cleaned)
        if not case_sensitive:
            key = key.casefold()
        bucket = groups.setdefault(key, [])
        if cleaned not in bucket:
            bucket.append(cleaned)
    return tuple((key, tuple(items)) for key, items in groups.items() if len(items) > 1)


def check_uniqueness(values: Iterable[str], *, case_sensitive: bool = True) -> UniquenessReport:
    """Summarize duplicates across a collection of flag values."""
    items = [clean_flag(value) for value in values]
    distinct = unique_flags(items, case_sensitive=case_sensitive)
    return UniquenessReport(
        total=len(items),
        unique=len(distinct),
        groups=find_duplicate_groups(items, case_sensitive=case_sensitive),
    )


def screen_candidates(candidates: Iterable[FlagCandidate]) -> tuple[ScreenedFlag, ...]:
    """Validate and score each candidate, rejecting malformed values."""
    screened: list[ScreenedFlag] = []
    for candidate in candidates:
        validation = validate_flag_format(candidate.value)
        confidence = score_confidence(candidate.value) if validation.ok else 0.0
        screened.append(
            ScreenedFlag(
                value=validation.value,
                source=candidate.source,
                ok=validation.ok,
                confidence=confidence,
                issues=validation.issues,
            )
        )
    return tuple(screened)


def prefix_distribution(values: Iterable[str]) -> tuple[tuple[str, int], ...]:
    """Count flags per lowercased prefix, ordered by frequency then name."""
    counts: Counter[str] = Counter(flag_prefix(value).lower() for value in values)
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
