"""Right-to-left layout helpers and bidirectional text safety."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v2.a11y.i18n.locales import direction_for, is_rtl, normalize_locale
from redscribe.v2.a11y.models import Direction, ElementNode

LRM = "\u200e"
RLM = "\u200f"
LRE = "\u202a"
RLE = "\u202b"
PDF = "\u202c"
LRI = "\u2066"
RLI = "\u2067"
PDI = "\u2069"
FSI = "\u2068"

DIRECTIONAL_CHARS_RE = re.compile(
    r"[\u0590-\u05ff\u0600-\u06ff\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./:+-]*")
RTL_WORD_RE = re.compile(r"[\u0590-\u05ff\u0600-\u06ff]+")

LOGICAL_SIDES: tuple[str, ...] = ("start", "end")
PHYSICAL_SIDES_LTR: dict[str, str] = {"start": "left", "end": "right"}
PHYSICAL_SIDES_RTL: dict[str, str] = {"start": "right", "end": "left"}
MIRRORED_CHARS: dict[str, str] = {
    "(": ")",
    ")": "(",
    "[": "]",
    "]": "[",
    "{": "}",
    "}": "{",
    "<": ">",
    ">": "<",
    "←": "→",
    "→": "←",
    "↑": "↑",
    "↓": "↓",
    "↔": "↔",
    "⇐": "⇒",
    "⇒": "⇐",
}


def is_rtl_locale(locale: str) -> bool:
    """Return whether a locale requires right-to-left layout."""
    return is_rtl(normalize_locale(locale))


def direction_of(locale: str) -> Direction:
    """Return the direction enum for a locale."""
    return direction_for(normalize_locale(locale))


def document_direction(locale: str, *, override: str | Direction | None = None) -> str:
    """Resolve a document direction attribute value."""
    if override is not None:
        value = override.value if isinstance(override, Direction) else override.strip().lower()
        if value in {"ltr", "rtl", "auto"}:
            return value
    return direction_of(locale).value


def physical_side(side: str, *, locale: str = "en") -> str:
    """Map a logical side to a physical side for a locale."""
    normalized = side.strip().lower()
    if normalized not in LOGICAL_SIDES:
        raise ValueError(f"Unknown logical side: {side}")
    mapping = PHYSICAL_SIDES_RTL if is_rtl_locale(locale) else PHYSICAL_SIDES_LTR
    return mapping[normalized]


def logical_side(side: str, *, locale: str = "en") -> str:
    """Map a physical side to a logical side for a locale."""
    normalized = side.strip().lower()
    if normalized not in {"left", "right"}:
        raise ValueError(f"Unknown physical side: {side}")
    mapping = PHYSICAL_SIDES_RTL if is_rtl_locale(locale) else PHYSICAL_SIDES_LTR
    for logical, physical in mapping.items():
        if physical == normalized:
            return logical
    return normalized


def mirror_text(text: str, *, locale: str) -> str:
    """Mirror bracket-like characters for right-to-left display."""
    if not is_rtl_locale(locale):
        return text
    return "".join(MIRRORED_CHARS.get(char, char) for char in text)


def isolate_text(text: str, *, direction: str | None = None) -> str:
    """Wrap a text fragment in bidirectional isolation."""
    if direction == "ltr":
        return f"{LRI}{text}{PDI}"
    if direction == "rtl":
        return f"{RLI}{text}{PDI}"
    return f"{FSI}{text}{PDI}"


def isolate_embedded(
    text: str,
    *,
    fragments: Sequence[str] = (),
    locale: str = "en",
) -> str:
    """Isolate embedded Latin fragments in RTL text."""
    if not is_rtl_locale(locale) or not fragments:
        return text
    result = text
    for fragment in sorted(set(fragments), key=len, reverse=True):
        if fragment:
            result = result.replace(fragment, isolate_text(fragment, direction="ltr"))
    return result


def strip_bidi_controls(text: str) -> str:
    """Remove explicit bidirectional control characters."""
    stripped: list[str] = []
    for char in text:
        if char in {LRM, RLM, LRE, RLE, PDF, LRI, RLI, PDI, FSI}:
            continue
        stripped.append(char)
    return "".join(stripped)


def has_rtl_characters(text: str) -> bool:
    """Return whether text contains RTL script or directional controls."""
    return bool(DIRECTIONAL_CHARS_RE.search(text))


def infer_direction(text: str, *, default: Direction = Direction.LTR) -> Direction:
    """Infer text direction from its strongest script characters."""
    rtl_count = len(RTL_WORD_RE.findall(text))
    ltr_count = len(LATIN_WORD_RE.findall(text))
    if rtl_count > ltr_count:
        return Direction.RTL
    if rtl_count == ltr_count and rtl_count > 0:
        return default
    return default


def direction_class(locale: str, *, override: str | Direction | None = None) -> str:
    """Return a CSS class name for the resolved direction."""
    return f"a11y-dir-{document_direction(locale, override=override)}"


def direction_css_vars(locale: str, *, override: str | Direction | None = None) -> dict[str, str]:
    """Return logical-to-physical CSS variables for a direction."""
    resolved = document_direction(locale, override=override)
    rtl = resolved == "rtl"
    return {
        "--a11y-inline-start": "right" if rtl else "left",
        "--a11y-inline-end": "left" if rtl else "right",
        "--a11y-text-align": "right" if rtl else "left",
        "--a11y-transform": "scaleX(-1)" if rtl else "none",
        "--a11y-border-start": "border-right" if rtl else "border-left",
        "--a11y-border-end": "border-left" if rtl else "border-right",
    }


def logical_border(style: str, *, locale: str, side: str = "start") -> str:
    """Build a logical border CSS declaration for a locale."""
    return f"{physical_side(side, locale=locale)}-border: {style}"


def bidi_warnings(text: str, *, locale: str) -> list[str]:
    """Return bidirectional text hazards found in a string."""
    warnings: list[str] = []
    if not is_rtl_locale(locale):
        return warnings
    if LATIN_WORD_RE.search(text) and not (LRI in text or RLI in text or FSI in text):
        warnings.append("isolate_latin_fragments")
    if text.startswith(("(", "[", "{")):
        warnings.append("mirror_leading_bracket")
    if has_rtl_characters(text) and not (LRE in text or RLE in text):
        warnings.append("prefer_logical_controls")
    if "\n" in text and text.count(LRI) != text.count(PDI):
        warnings.append("unbalanced_isolates")
    return warnings


def normalize_direction(value: str | Direction | None, *, locale: str = "en") -> Direction:
    """Normalize an explicit direction override."""
    if value is None:
        return direction_of(locale)
    if isinstance(value, Direction):
        return value
    lowered = value.strip().lower()
    if lowered == "auto":
        return Direction.AUTO
    try:
        return Direction(lowered)
    except ValueError:
        return direction_of(locale)


def analyze_rtl_tree(nodes: Sequence[ElementNode], *, locale: str) -> dict[str, Any]:
    """Find elements in a tree that may need bidi correction."""
    findings: list[dict[str, Any]] = []
    for node in nodes:
        for item in [node, *node.descendants()]:
            explicit = item.attr("dir")
            warnings = bidi_warnings(item.text, locale=locale)
            if explicit == "ltr" and is_rtl_locale(locale):
                warnings.append("explicit_ltr_in_rtl_document")
            if warnings:
                findings.append(
                    {
                        "target": item.path or item.element_id or item.normalized_tag,
                        "warnings": warnings,
                        "text": item.text[:80],
                    }
                )
    return {
        "locale": normalize_locale(locale),
        "direction": document_direction(locale),
        "findings": findings,
        "count": len(findings),
    }


def rtl_css_class_map() -> dict[str, str]:
    """Return CSS class names used by RTL helpers."""
    return {
        "ltr": "a11y-dir-ltr",
        "rtl": "a11y-dir-rtl",
        "auto": "a11y-dir-auto",
        "isolate": "a11y-bidi-isolate",
        "mirror": "a11y-bidi-mirror",
    }


def side_summary(locale: str) -> Mapping[str, str]:
    """Return logical and physical side pairs for a locale."""
    return {
        "inline_start": physical_side("start", locale=locale),
        "inline_end": physical_side("end", locale=locale),
        "leading": physical_side("start", locale=locale),
        "trailing": physical_side("end", locale=locale),
    }
