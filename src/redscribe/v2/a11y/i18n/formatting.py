"""Locale-aware plural, number, date, time, and list formatting."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from redscribe.v2.a11y.i18n.locales import (
    language_of,
    lookup_locale,
    normalize_locale,
    plural_category,
    plural_rule_for,
)

DIGIT_MAPS: dict[str, str] = {
    "ar": "٠١٢٣٤٥٦٧٨٩",
    "he": "٠١٢٣٤٥٦٧٨٩",
    "fa": "۰۱۲۳۴۵۶۷۸۹",
}

MONTH_NAMES: dict[str, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "es": (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ),
    "fr": (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ),
    "de": (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
    "ja": ("1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"),
    "zh": (
        "一月",
        "二月",
        "三月",
        "四月",
        "五月",
        "六月",
        "七月",
        "八月",
        "九月",
        "十月",
        "十一月",
        "十二月",
    ),
}

WEEKDAY_NAMES: dict[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "ja": ("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "RUB": "₽",
    "ILS": "₪",
}

RELATIVE_UNITS: tuple[tuple[int, str, str], ...] = (
    (31_536_000, "year", "years"),
    (2_592_000, "month", "months"),
    (604_800, "week", "weeks"),
    (86_400, "day", "days"),
    (3_600, "hour", "hours"),
    (60, "minute", "minutes"),
)

ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
ISO_DATETIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$")


def _locale_info(locale: str) -> Mapping[str, Any]:
    info = lookup_locale(locale)
    if info is None:
        return {
            "decimal_separator": ".",
            "group_separator": ",",
            "date_format": "yyyy-MM-dd",
        }
    return {
        "decimal_separator": info.decimal_separator,
        "group_separator": info.group_separator,
        "date_format": info.date_format,
    }


def localize_digits(value: str, locale: str) -> str:
    """Replace ASCII digits with locale-specific digit glyphs."""
    digits = DIGIT_MAPS.get(language_of(locale))
    if not digits:
        return value
    return "".join(digits[int(char)] if char.isdigit() else char for char in value)


def pluralize(
    key: str,
    count: int,
    *,
    locale: str = "en",
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Return the plural form of a message key for a count."""
    category = plural_category(locale, count)
    options = dict(overrides or {})
    selected = options.get(f"{key}.{category}")
    if selected is None and category != "other":
        selected = options.get(f"{key}.other")
    if selected is None:
        selected = options.get(key)
    if selected is None:
        selected = f"{key}.{category}"
    try:
        return selected.format(count=count)
    except (KeyError, ValueError):
        return selected


def plural_options(
    singular: str,
    plural: str,
    *,
    locale: str = "en",
    zero: str | None = None,
) -> dict[str, str]:
    """Build a category-to-template mapping for a plural message."""
    categories = plural_rule_for(locale).categories
    result: dict[str, str] = {}
    for category in categories:
        if category == "zero" and zero is not None:
            result[category] = zero
        elif category == "one":
            result[category] = singular
        else:
            result[category] = plural
    return result


def format_number(
    value: int | float | Decimal | str,
    *,
    locale: str = "en",
    minimum_fraction_digits: int = 0,
    maximum_fraction_digits: int = 3,
    grouping: bool = True,
    sign_display: str = "auto",
) -> str:
    """Format a number with locale separators and grouping."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid number: {value}") from exc
    if not number.is_finite():
        raise ValueError("Number must be finite")
    settings = _locale_info(locale)
    quantum = Decimal(1).scaleb(-max(0, maximum_fraction_digits))
    rounded = number.quantize(quantum)
    text = f"{rounded:.{max(minimum_fraction_digits, 0)}f}"
    if maximum_fraction_digits > 0 and "." in text:
        text = text.rstrip("0").rstrip(".")
    if minimum_fraction_digits > 0 and "." not in text:
        text = f"{text}.{'0' * minimum_fraction_digits}"
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    integer, _, fraction = text.partition(".")
    if grouping:
        chunks: list[str] = []
        while len(integer) > 3:
            chunks.append(integer[-3:])
            integer = integer[:-3]
        chunks.append(integer)
        integer = str(settings["group_separator"]).join(reversed(chunks))
    result = integer
    if fraction:
        result += str(settings["decimal_separator"]) + fraction
    if negative:
        prefix = "−" if sign_display in {"auto", "always"} else "-"
        result = prefix + result
    elif sign_display == "always":
        result = "+" + result
    return localize_digits(result, locale)


def format_percent(
    value: float,
    *,
    locale: str = "en",
    digits: int = 0,
    already_scaled: bool = False,
) -> str:
    """Format a percentage value."""
    number = value if already_scaled else value * 100.0
    formatted = format_number(
        number,
        locale=locale,
        minimum_fraction_digits=digits,
        maximum_fraction_digits=digits,
    )
    return f"{formatted}%"


def format_currency(
    value: float,
    currency: str,
    *,
    locale: str = "en",
    digits: int = 2,
    symbol: bool = True,
) -> str:
    """Format a currency amount."""
    amount = format_number(
        value,
        locale=locale,
        minimum_fraction_digits=digits,
        maximum_fraction_digits=digits,
    )
    token = CURRENCY_SYMBOLS.get(currency.upper(), currency.upper())
    if symbol:
        if language_of(locale) in {"fr", "de", "es"}:
            return f"{amount}\u00a0{token}"
        return f"{token}{amount}"
    return f"{amount} {currency.upper()}"


def format_bytes(value: int, *, locale: str = "en", binary: bool = False) -> str:
    """Format a byte count with a unit suffix."""
    base = 1024.0 if binary else 1000.0
    suffixes = ("B", "KiB", "MiB", "GiB", "TiB") if binary else ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    index = 0
    while abs(amount) >= base and index < len(suffixes) - 1:
        amount /= base
        index += 1
    digits = 0 if index == 0 else 1
    return (
        f"{format_number(amount, locale=locale, maximum_fraction_digits=digits)} {suffixes[index]}"
    )


def parse_iso_date(value: str) -> date:
    """Parse an ISO date string."""
    match = ISO_DATE_RE.match(value.strip())
    if match is None:
        raise ValueError(f"Invalid ISO date: {value}")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO date-time string, assuming UTC when no offset is present."""
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        match = ISO_DATETIME_RE.match(value.strip())
        if match is None:
            raise ValueError(f"Invalid ISO datetime: {value}") from exc
        parsed = datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            int(match.group(5)),
            int(match.group(6) or 0),
            tzinfo=timezone.utc,
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_date(
    value: str | date | datetime,
    *,
    locale: str = "en",
    pattern: str | None = None,
) -> str:
    """Format a date according to a locale pattern."""
    current: date
    if isinstance(value, datetime):
        current = value.date()
    elif isinstance(value, date):
        current = value
    else:
        current = parse_iso_date(value)
    chosen = pattern or str(_locale_info(locale)["date_format"])
    months = MONTH_NAMES.get(language_of(locale), MONTH_NAMES["en"])
    weekdays = WEEKDAY_NAMES.get(language_of(locale), WEEKDAY_NAMES["en"])
    replacements = {
        "yyyy": f"{current.year:04d}",
        "yy": f"{current.year % 100:02d}",
        "MMMM": months[current.month - 1],
        "MMM": months[current.month - 1][:3],
        "MM": f"{current.month:02d}",
        "dd": f"{current.day:02d}",
        "d": str(current.day),
        "EEEE": weekdays[current.weekday()],
    }
    result = chosen
    for token in sorted(replacements, key=len, reverse=True):
        result = result.replace(token, replacements[token])
    return localize_digits(result, locale)


def format_time(
    value: str | time | datetime,
    *,
    locale: str = "en",
    with_seconds: bool = False,
    hour12: bool = False,
) -> str:
    """Format a time value."""
    if isinstance(value, datetime):
        current = value.timetz()
    elif isinstance(value, time):
        current = value
    else:
        parsed = parse_iso_datetime(value)
        current = parsed.timetz()
    hour = current.hour
    meridiem = ""
    if hour12:
        meridiem = " AM" if hour < 12 else " PM"
        hour = hour % 12 or 12
    parts = [f"{hour:02d}", f"{current.minute:02d}"]
    if with_seconds:
        parts.append(f"{current.second:02d}")
    return localize_digits(":".join(parts) + meridiem, locale)


def format_datetime(
    value: str | datetime,
    *,
    locale: str = "en",
    date_pattern: str | None = None,
    with_seconds: bool = False,
) -> str:
    """Format a date and time together."""
    parsed = value if isinstance(value, datetime) else parse_iso_datetime(value)
    formatted_date = format_date(parsed.date(), locale=locale, pattern=date_pattern)
    formatted_time = format_time(parsed, locale=locale, with_seconds=with_seconds)
    return f"{formatted_date} {formatted_time}"


def format_relative_time(
    value: str | datetime,
    *,
    locale: str = "en",
    now: datetime | None = None,
    future_prefix: str = "in ",
    past_suffix: str = " ago",
) -> str:
    """Format a relative time expression."""
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    target = value if isinstance(value, datetime) else parse_iso_datetime(value)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    delta = (target - reference).total_seconds()
    past = delta < 0
    absolute = abs(delta)
    for seconds, singular, plural in RELATIVE_UNITS:
        if absolute >= seconds:
            count = int(absolute // seconds)
            unit = singular if count == 1 else plural
            core = f"{count} {unit}"
            if past:
                return core + past_suffix
            return future_prefix + core
    return "just now" if past else "soon"


def format_list(
    items: Sequence[str],
    *,
    locale: str = "en",
    conjunction: str | None = None,
    oxford_comma: bool = False,
) -> str:
    """Join a list with a localized conjunction."""
    values = [item for item in items if item]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    word = conjunction or {
        "en": "and",
        "es": "y",
        "fr": "et",
        "de": "und",
        "ja": "と",
        "zh": "和",
    }.get(language_of(locale), "and")
    if len(values) == 2:
        return f"{values[0]} {word} {values[1]}"
    separator = "、" if language_of(locale) in {"ja", "zh"} else ", "
    head = separator.join(values[:-1])
    comma = "," if oxford_comma else ""
    return f"{head}{comma} {word} {values[-1]}"


def format_ordinal(value: int, *, locale: str = "en") -> str:
    """Format an ordinal number."""
    base = language_of(locale)
    if base in {"ja", "zh"}:
        return f"第{localize_digits(str(value), locale)}"
    if base == "de":
        return f"{value}."
    if base == "es" or base == "fr":
        return f"{value}.º" if base == "es" else f"{value}e"
    if value % 100 in (11, 12, 13):
        suffix = "th"
    elif value % 10 == 1:
        suffix = "st"
    elif value % 10 == 2:
        suffix = "nd"
    elif value % 10 == 3:
        suffix = "rd"
    else:
        suffix = "th"
    return f"{value}{suffix}"


def format_duration(seconds: int, *, locale: str = "en") -> str:
    """Format a duration using hours, minutes, and seconds."""
    if seconds < 0:
        raise ValueError("Duration cannot be negative")
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if secs or not parts:
        parts.append(f"{secs} s")
    return format_list(parts, locale=locale)


def format_range(start: int, end: int, *, locale: str = "en") -> str:
    """Format an inclusive numeric range."""
    if end < start:
        raise ValueError("Range end must not be before start")
    separator = "–" if language_of(locale) != "en" else "-"
    return f"{format_number(start, locale=locale)}{separator}{format_number(end, locale=locale)}"


def rounding_step(value: float, *, decimals: int = 1) -> float:
    """Round a value to a decimal step."""
    factor = 10 ** max(0, decimals)
    return float(math.floor(value * factor) / factor)


def format_label_value(label: str, value: Any, *, locale: str = "en") -> str:
    """Format a label/value pair for announcement text."""
    if isinstance(value, bool):
        rendered = "yes" if value else "no"
    elif isinstance(value, (int, float, Decimal)):
        rendered = format_number(value, locale=locale)
    elif value is None:
        rendered = "none"
    else:
        rendered = str(value)
    return f"{label}: {rendered}"


def normalize_number_string(value: str, *, locale: str = "en") -> str:
    """Normalize a localized number string to plain decimal notation."""
    settings = _locale_info(locale)
    text = value.strip()
    digit_map = DIGIT_MAPS.get(language_of(locale))
    if digit_map:
        text = "".join(str(digit_map.index(char)) if char in digit_map else char for char in text)
    text = text.replace(str(settings["group_separator"]), "")
    return text.replace(str(settings["decimal_separator"]), ".")


def formatting_options(locale: str) -> dict[str, Any]:
    """Return formatting defaults for a locale."""
    settings = _locale_info(locale)
    return {
        "locale": normalize_locale(locale),
        "decimal_separator": settings["decimal_separator"],
        "group_separator": settings["group_separator"],
        "date_format": settings["date_format"],
        "language": language_of(locale),
        "digits": DIGIT_MAPS.get(language_of(locale), "0123456789"),
    }
