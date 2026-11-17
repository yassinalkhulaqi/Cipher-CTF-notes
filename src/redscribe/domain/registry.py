"""Flag format registry with confidence scoring and category inference."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from redscribe.domain.flags import FLAG_PREFIXES, clean_flag, flag_body, flag_prefix

GENERIC_CATEGORY = "generic"
PLATFORM_CATEGORIES: frozenset[str] = frozenset({"htb", "thm", "picoctf"})

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "crypto": ("crypto", "rsa", "aes", "xor", "cipher", "hashed", "base64", "key"),
    "web": ("web", "sqli", "xss", "ssti", "jwt", "cookie", "admin", "http"),
    "pwn": ("pwn", "overflow", "bof", "rop", "heap", "shellcode", "got"),
    "reversing": ("reverse", "reversing", "rev", "obfusc", "disassembl", "vm"),
    "forensics": ("forensic", "pcap", "memory", "disk", "packet", "carve"),
    "stego": ("steg", "stego", "lsb", "hidden", "image", "audio"),
    "misc": ("misc", "trivia", "encoding", "brainfuck", "regex"),
}

HIGH_BAND = "high"
MEDIUM_BAND = "medium"
LOW_BAND = "low"
INVALID_BAND = "invalid"


@dataclass(frozen=True, slots=True)
class FlagFormat:
    """A registered flag prefix with its default weight and category."""

    key: str
    confidence: float
    category: str


@dataclass(frozen=True, slots=True)
class FlagAssessment:
    """A scored interpretation of a single flag value."""

    value: str
    prefix: str
    body: str
    category: str
    confidence: float
    band: str
    known_prefix: bool
    reasons: tuple[str, ...]


def _build_formats() -> tuple[FlagFormat, ...]:
    formats: list[FlagFormat] = []
    for key in FLAG_PREFIXES:
        if key in PLATFORM_CATEGORIES:
            category, confidence = key, 0.95
        elif key in ("flag", "ctf"):
            category, confidence = GENERIC_CATEGORY, 0.45
        else:
            category, confidence = "ctf", 0.80
        formats.append(FlagFormat(key=key, confidence=confidence, category=category))
    return tuple(formats)


FLAG_FORMATS: tuple[FlagFormat, ...] = _build_formats()
FORMATS_BY_KEY: dict[str, FlagFormat] = {entry.key: entry for entry in FLAG_FORMATS}


def infer_category(value: str) -> str:
    """Infer a CTF category from a flag payload, then from its prefix."""
    lowered = clean_flag(value).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    prefix = lowered.split("{", 1)[0]
    entry = FORMATS_BY_KEY.get(prefix)
    if entry is not None:
        return entry.category
    return GENERIC_CATEGORY


def confidence_band(confidence: float) -> str:
    """Map a numeric confidence score onto a stable band name."""
    if confidence <= 0.0:
        return INVALID_BAND
    if confidence >= 0.85:
        return HIGH_BAND
    if confidence >= 0.60:
        return MEDIUM_BAND
    return LOW_BAND


def score_confidence(value: str) -> float:
    """Score how likely a value is to be a genuine, usable CTF flag."""
    cleaned = clean_flag(value)
    prefix, body = flag_prefix(cleaned), flag_body(cleaned)
    if not prefix or not body:
        return 0.0
    score = 0.30
    entry = FORMATS_BY_KEY.get(prefix.lower())
    if entry is not None:
        score += entry.confidence * 0.40
    length = len(body)
    if 8 <= length <= 64:
        score += 0.18
    elif 4 <= length < 8 or 64 < length <= 128:
        score += 0.08
    if all(char.isalnum() or char in "_-" for char in body):
        score += 0.08
    if infer_category(cleaned) not in (GENERIC_CATEGORY, "ctf"):
        score += 0.04
    return round(min(score, 1.0), 3)


def assess_flag(value: str) -> FlagAssessment:
    """Return the full scoring breakdown for one flag value."""
    cleaned = clean_flag(value)
    prefix, body = flag_prefix(cleaned), flag_body(cleaned)
    confidence = score_confidence(cleaned)
    entry = FORMATS_BY_KEY.get(prefix.lower())
    reasons: list[str] = []
    if entry is not None:
        reasons.append(f"known prefix: {prefix}")
    if 8 <= len(body) <= 64:
        reasons.append("plausible payload length")
    if all(char.isalnum() or char in "_-" for char in body) and body:
        reasons.append("flag-safe payload characters")
    category = infer_category(cleaned)
    if category not in (GENERIC_CATEGORY, "ctf"):
        reasons.append(f"category hint: {category}")
    if not reasons:
        reasons.append("insufficient evidence")
    return FlagAssessment(
        value=cleaned,
        prefix=prefix,
        body=body,
        category=category,
        confidence=confidence,
        band=confidence_band(confidence),
        known_prefix=entry is not None,
        reasons=tuple(reasons),
    )


def rank_candidates(values: Iterable[str]) -> tuple[FlagAssessment, ...]:
    """Assess every candidate and return them ordered by confidence."""
    assessments = [assess_flag(value) for value in values]
    return tuple(sorted(assessments, key=lambda item: (-item.confidence, item.value)))


def best_candidate(values: Iterable[str]) -> FlagAssessment | None:
    """Return the highest-confidence assessment, if any values were given."""
    ranked = rank_candidates(values)
    return ranked[0] if ranked else None
