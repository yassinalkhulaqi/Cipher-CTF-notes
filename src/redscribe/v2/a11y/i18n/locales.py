"""Locale metadata, matching, fallback chains, and plural categories."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.a11y.models import Direction, LocaleInfo

LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")


@dataclass(frozen=True, slots=True)
class PluralRule:
    """A locale plural rule with named categories."""

    categories: tuple[str, ...]
    description: str

    def category(self, count: int) -> str:
        """Return the plural category for a count."""
        if not self.categories:
            return "other"
        if len(self.categories) == 1:
            return self.categories[0]
        if count == 1:
            return "one" if "one" in self.categories else self.categories[0]
        if count == 0 and "zero" in self.categories:
            return "zero"
        if count == 2 and "two" in self.categories:
            return "two"
        if count > 1 and "few" in self.categories and count % 10 in (2, 3, 4):
            return "few"
        if count > 1 and "many" in self.categories and count % 10 in (0, 5, 6, 7, 8, 9):
            return "many"
        return "other" if "other" in self.categories else self.categories[-1]

    def as_dict(self) -> dict[str, Any]:
        return {
            "categories": list(self.categories),
            "description": self.description,
        }


PLURAL_RULES: dict[str, PluralRule] = {
    "en": PluralRule(("one", "other"), "Singular one, everything else other"),
    "de": PluralRule(("one", "other"), "Singular one, everything else other"),
    "es": PluralRule(("one", "many", "other"), "One, millions, and other"),
    "fr": PluralRule(("one", "many", "other"), "One, large cardinalities, and other"),
    "pt": PluralRule(("one", "many", "other"), "One, large cardinalities, and other"),
    "ar": PluralRule(("zero", "one", "two", "few", "many", "other"), "Six-category Arabic rule"),
    "he": PluralRule(("one", "two", "many", "other"), "One, two, many, other"),
    "ja": PluralRule(("other",), "No inflection"),
    "ko": PluralRule(("other",), "No inflection"),
    "zh": PluralRule(("other",), "No inflection"),
    "ru": PluralRule(("one", "few", "many", "other"), "Slavic pluralization"),
    "uk": PluralRule(("one", "few", "many", "other"), "Slavic pluralization"),
}

LOCALES: dict[str, LocaleInfo] = {
    info.code: info
    for info in (
        LocaleInfo(
            "en",
            "English",
            "English",
            Direction.LTR,
            "Latn",
            ("one", "other"),
            ("en",),
            "yyyy-MM-dd",
            ".",
            ",",
        ),
        LocaleInfo(
            "en-GB",
            "English (UK)",
            "English (UK)",
            Direction.LTR,
            "Latn",
            ("one", "other"),
            ("en",),
            "dd/MM/yyyy",
            ".",
            ",",
        ),
        LocaleInfo(
            "es",
            "Spanish",
            "Español",
            Direction.LTR,
            "Latn",
            ("one", "many", "other"),
            ("en",),
            "dd/MM/yyyy",
            ",",
            ".",
        ),
        LocaleInfo(
            "fr",
            "French",
            "Français",
            Direction.LTR,
            "Latn",
            ("one", "many", "other"),
            ("en",),
            "dd/MM/yyyy",
            ",",
            " ",
        ),
        LocaleInfo(
            "de",
            "German",
            "Deutsch",
            Direction.LTR,
            "Latn",
            ("one", "other"),
            ("en",),
            "dd.MM.yyyy",
            ",",
            ".",
        ),
        LocaleInfo(
            "pt",
            "Portuguese",
            "Português",
            Direction.LTR,
            "Latn",
            ("one", "many", "other"),
            ("en",),
            "dd/MM/yyyy",
            ",",
            ".",
        ),
        LocaleInfo(
            "ar",
            "Arabic",
            "العربية",
            Direction.RTL,
            "Arab",
            ("zero", "one", "two", "few", "many", "other"),
            ("en",),
            "dd/MM/yyyy",
            "٫",
            "٬",
        ),
        LocaleInfo(
            "he",
            "Hebrew",
            "עברית",
            Direction.RTL,
            "Hebr",
            ("one", "two", "many", "other"),
            ("en",),
            "dd/MM/yyyy",
            ".",
            ",",
        ),
        LocaleInfo(
            "ja",
            "Japanese",
            "日本語",
            Direction.LTR,
            "Jpan",
            ("other",),
            ("en",),
            "yyyy/MM/dd",
            ".",
            ",",
        ),
        LocaleInfo(
            "ko",
            "Korean",
            "한국어",
            Direction.LTR,
            "Hang",
            ("other",),
            ("en",),
            "yyyy. MM. dd.",
            ".",
            ",",
        ),
        LocaleInfo(
            "zh",
            "Chinese",
            "中文",
            Direction.LTR,
            "Hans",
            ("other",),
            ("en",),
            "yyyy-MM-dd",
            ".",
            ",",
        ),
        LocaleInfo(
            "ru",
            "Russian",
            "Русский",
            Direction.LTR,
            "Cyrl",
            ("one", "few", "many", "other"),
            ("en",),
            "dd.MM.yyyy",
            ",",
            " ",
        ),
    )
}

RTL_LOCALES: frozenset[str] = frozenset({"ar", "he", "fa", "ur", "ps", "yi"})


def normalize_locale(value: str) -> str:
    """Normalize a locale tag to lowercase language and uppercase region."""
    text = value.strip().replace("_", "-")
    if not text:
        return "en"
    parts = text.split("-")
    language = parts[0].lower()
    tail = [part.upper() if len(part) == 2 else part.title() for part in parts[1:]]
    return "-".join([language, *tail])


def is_valid_locale(value: str) -> bool:
    """Return whether a locale tag is syntactically valid."""
    return bool(LOCALE_PATTERN.match(value.strip().replace("_", "-")))


def language_of(locale: str) -> str:
    """Return the base language of a locale tag."""
    return normalize_locale(locale).split("-", 1)[0]


def region_of(locale: str) -> str:
    """Return the region subtag of a locale, if any."""
    parts = normalize_locale(locale).split("-")
    return parts[1] if len(parts) > 1 else ""


def direction_for(locale: str) -> Direction:
    """Return the text direction for a locale."""
    info = lookup_locale(locale)
    if info is not None:
        return info.direction
    base = language_of(locale)
    return Direction.RTL if base in RTL_LOCALES else Direction.LTR


def is_rtl(locale: str) -> bool:
    """Return whether a locale uses right-to-left text."""
    return direction_for(locale) == Direction.RTL


def lookup_locale(locale: str) -> LocaleInfo | None:
    """Look up an exact locale, falling back to the language subtag."""
    normalized = normalize_locale(locale)
    if normalized in LOCALES:
        return LOCALES[normalized]
    base = language_of(normalized)
    return LOCALES.get(base)


def fallback_chain(locale: str) -> tuple[str, ...]:
    """Return an ordered message fallback chain for a locale."""
    normalized = normalize_locale(locale)
    chain: list[str] = [normalized]
    parts = normalized.split("-")
    while len(parts) > 1:
        parts.pop()
        chain.append("-".join(parts))
    info = lookup_locale(normalized)
    if info is not None:
        for fallback in info.fallbacks:
            if fallback not in chain:
                chain.append(fallback)
    if "en" not in chain:
        chain.append("en")
    return tuple(dict.fromkeys(chain))


def match_locale(requested: str, available: Iterable[str]) -> str | None:
    """Find the best available locale for a requested tag."""
    options = [normalize_locale(item) for item in available]
    if not options:
        return None
    normalized = normalize_locale(requested)
    if normalized in options:
        return normalized
    base = language_of(normalized)
    for option in options:
        if language_of(option) == base:
            return option
    for option in options:
        if language_of(option) == "en":
            return option
    return options[0]


def plural_rule_for(locale: str) -> PluralRule:
    """Return the plural rule for a language."""
    base = language_of(locale)
    return PLURAL_RULES.get(base, PLURAL_RULES["en"])


def plural_category(locale: str, count: int) -> str:
    """Return the plural category for a locale and count."""
    return plural_rule_for(locale).category(count)


def locale_summary(locale: str) -> dict[str, Any]:
    """Return a summary record for a locale."""
    info = lookup_locale(locale)
    if info is None:
        return {
            "code": normalize_locale(locale),
            "supported": False,
            "direction": direction_for(locale).value,
            "fallbacks": list(fallback_chain(locale)),
        }
    payload = info.as_dict()
    payload["supported"] = True
    payload["plural_rule"] = plural_rule_for(locale).as_dict()
    return payload


def all_locales() -> tuple[LocaleInfo, ...]:
    """Return all registered locales in stable order."""
    return tuple(LOCALES[code] for code in sorted(LOCALES))


def register_locale(info: LocaleInfo) -> LocaleInfo:
    """Register or replace a locale definition."""
    LOCALES[normalize_locale(info.code)] = info
    return info


def locale_options() -> list[dict[str, Any]]:
    """Return locale options for a picker UI."""
    return [
        {
            "value": info.code,
            "label": info.label,
            "native_name": info.native_name,
            "direction": info.direction.value,
            "script": info.script,
        }
        for info in all_locales()
    ]


def parse_accept_language(value: str) -> tuple[str, ...]:
    """Parse an Accept-Language header into ordered locale tags."""
    result: list[str] = []
    for part in value.split(","):
        tag = part.split(";", 1)[0].strip()
        if tag == "*" or not tag:
            continue
        normalized = normalize_locale(tag)
        if is_valid_locale(normalized):
            result.append(normalized)
    return tuple(result)


def best_match_header(value: str, available: Sequence[str]) -> str | None:
    """Select the best available locale from an Accept-Language header."""
    for requested in parse_accept_language(value):
        matched = match_locale(requested, available)
        if matched is not None:
            return matched
    return None


def locale_metadata_map() -> dict[str, dict[str, Any]]:
    """Return all locales keyed by code."""
    return {code: locale_summary(code) for code in sorted(LOCALES)}


def plural_patterns() -> dict[str, dict[str, Any]]:
    """Return plural rules keyed by language."""
    return {key: rule.as_dict() for key, rule in sorted(PLURAL_RULES.items())}


def direction_label(direction: Direction) -> str:
    """Return a user-facing label for a text direction."""
    if direction == Direction.RTL:
        return "Right to left"
    if direction == Direction.LTR:
        return "Left to right"
    return "Automatic"


def locale_from_mapping(payload: Mapping[str, Any]) -> LocaleInfo:
    """Build a LocaleInfo from a serialized mapping."""
    code = str(payload.get("code", "en"))
    direction_raw = str(payload.get("direction", direction_for(code).value))
    try:
        direction = Direction(direction_raw)
    except ValueError:
        direction = direction_for(code)
    fallbacks = tuple(str(item) for item in payload.get("fallbacks") or ("en",))
    categories = tuple(str(item) for item in payload.get("plural_categories") or ("one", "other"))
    return LocaleInfo(
        code=normalize_locale(code),
        label=str(payload.get("label", code)),
        native_name=str(payload.get("native_name", code)),
        direction=direction,
        script=str(payload.get("script", "Latn")),
        plural_categories=categories,
        fallbacks=fallbacks,
        date_format=str(payload.get("date_format", "yyyy-MM-dd")),
        decimal_separator=str(payload.get("decimal_separator", ".")),
        group_separator=str(payload.get("group_separator", ",")),
    )
