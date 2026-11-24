"""Locale-aware formatting and additional V3 message catalogs.

The module builds on V2's locale registry, plural rules, and formatters. It
adds V3-specific message keys, extra catalogs, batch formatting, round-trip
verification, and direction metadata for every formatted value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from redscribe.v2.a11y.i18n.catalogs import CatalogManager, MessageCatalog
from redscribe.v2.a11y.i18n.formatting import (
    format_bytes,
    format_currency,
    format_date,
    format_datetime,
    format_duration,
    format_list,
    format_number,
    format_ordinal,
    format_percent,
    format_range,
    format_relative_time,
    format_time,
    normalize_number_string,
    plural_options,
    pluralize,
)
from redscribe.v2.a11y.i18n.locales import (
    fallback_chain,
    language_of,
    locale_options,
    normalize_locale,
)
from redscribe.v2.a11y.i18n.rtl import isolate_text
from redscribe.v2.a11y.models import Direction, LocaleInfo
from redscribe.v3.a11y_refinement.models import FormatRequest, FormatResult

FORMAT_KINDS: tuple[str, ...] = (
    "number",
    "percent",
    "currency",
    "bytes",
    "date",
    "time",
    "datetime",
    "relative",
    "plural",
    "ordinal",
    "duration",
    "range",
    "list",
)

V3_MESSAGE_KEYS: tuple[str, ...] = (
    "v3.audit.passed",
    "v3.audit.findings",
    "v3.contrast.score",
    "v3.keyboard.binding",
    "v3.layout.direction",
    "v3.finding.severity",
    "v3.evidence.integrity",
    "v3.report.generated",
    "v3.prefs.synced",
    "v3.command.run",
    "v3.search.results",
    "v3.theme.changed",
    "v3.motion.reduced",
    "v3.shortcut.help",
)

EN_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "Audit passed for {surface}",
    "v3.audit.findings": "{count} findings on {surface}",
    "v3.contrast.score": "Contrast score {score} percent",
    "v3.keyboard.binding": "{action}: {binding}",
    "v3.layout.direction": "Layout direction {direction}",
    "v3.finding.severity": "Finding severity {severity}",
    "v3.evidence.integrity": "Evidence integrity {status}",
    "v3.report.generated": "Report generated at {time}",
    "v3.prefs.synced": "Preferences synchronized to revision {revision}",
    "v3.command.run": "Running command {name}",
    "v3.search.results": "{count} results",
    "v3.theme.changed": "Theme changed to {theme}",
    "v3.motion.reduced": "Reduced motion enabled",
    "v3.shortcut.help": "Press {key} for keyboard help",
}

PT_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "Auditoria aprovada para {surface}",
    "v3.audit.findings": "{count} problemas em {surface}",
    "v3.contrast.score": "Pontuação de contraste {score} por cento",
    "v3.keyboard.binding": "{action}: {binding}",
    "v3.report.generated": "Relatório gerado às {time}",
    "v3.search.results": "{count} resultados",
    "v3.theme.changed": "Tema alterado para {theme}",
}

IT_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "Controllo superato per {surface}",
    "v3.audit.findings": "{count} problemi in {surface}",
    "v3.contrast.score": "Punteggio di contrasto {score} percento",
    "v3.keyboard.binding": "{action}: {binding}",
    "v3.report.generated": "Report generato alle {time}",
    "v3.search.results": "{count} risultati",
    "v3.theme.changed": "Tema cambiato in {theme}",
}

NL_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "Audit geslaagd voor {surface}",
    "v3.audit.findings": "{count} bevindingen op {surface}",
    "v3.contrast.score": "Contrastscore {score} procent",
    "v3.keyboard.binding": "{action}: {binding}",
    "v3.report.generated": "Rapport gegenereerd om {time}",
    "v3.search.results": "{count} resultaten",
    "v3.theme.changed": "Thema gewijzigd naar {theme}",
}

KO_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "{surface} 감사 통과",
    "v3.audit.findings": "{surface}에서 {count}건 발견",
    "v3.contrast.score": "대비 점수 {score}퍼센트",
    "v3.keyboard.binding": "{action}: {binding}",
    "v3.report.generated": "{time}에 보고서 생성",
    "v3.search.results": "결과 {count}건",
    "v3.theme.changed": "테마를 {theme}(으)로 변경",
}

FA_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "بررسی با موفقیت برای {surface} انجام شد",
    "v3.audit.findings": "{count} یافته در {surface}",
    "v3.contrast.score": "امتیاز تضاد {score} درصد",
    "v3.keyboard.binding": "{binding} : {action}",
    "v3.layout.direction": "جهت طرحبندی {direction}",
    "v3.report.generated": "گزارش در {time} ایجاد شد",
    "v3.search.results": "{count} نتیجه",
    "v3.theme.changed": "تغییر تم به {theme}",
}

UR_MESSAGES: dict[str, str] = {
    "v3.audit.passed": "{surface} کے لیے آڈٹ کامیاب",
    "v3.audit.findings": "{surface} میں {count} نتائج",
    "v3.contrast.score": "کنٹراسٹ اسکور {score} فیصد",
    "v3.keyboard.binding": "{action}: {binding}",
    "v3.layout.direction": "ترتیب کی سمت {direction}",
    "v3.report.generated": "رپورٹ {time} پر تیار ہوئی",
    "v3.search.results": "{count} نتائج",
    "v3.theme.changed": "تھیم {theme} میں تبدیل",
}

ADDITIONAL_CATALOGS: dict[str, dict[str, str]] = {
    "pt-BR": PT_MESSAGES,
    "it": IT_MESSAGES,
    "nl": NL_MESSAGES,
    "ko": KO_MESSAGES,
    "fa": FA_MESSAGES,
    "ur": UR_MESSAGES,
}

V3_LOCALES: dict[str, LocaleInfo] = {
    "pt-BR": LocaleInfo(
        code="pt-BR",
        label="Portuguese (Brazil)",
        native_name="Português (Brasil)",
        script="Latn",
        fallbacks=("pt", "en"),
        date_format="dd/MM/yyyy",
        decimal_separator=",",
        group_separator=".",
    ),
    "it": LocaleInfo(
        code="it",
        label="Italian",
        native_name="Italiano",
        script="Latn",
        fallbacks=("en",),
        date_format="dd/MM/yyyy",
        decimal_separator=",",
        group_separator=".",
    ),
    "nl": LocaleInfo(
        code="nl",
        label="Dutch",
        native_name="Nederlands",
        script="Latn",
        fallbacks=("en",),
        date_format="dd-MM-yyyy",
        decimal_separator=",",
        group_separator=".",
    ),
    "ko": LocaleInfo(
        code="ko",
        label="Korean",
        native_name="한국어",
        script="Hang",
        plural_categories=("other",),
        fallbacks=("en",),
        date_format="yyyy-MM-dd",
    ),
    "fa": LocaleInfo(
        code="fa",
        label="Persian",
        native_name="فارسی",
        direction=Direction.RTL,
        script="Arab",
        fallbacks=("en",),
        date_format="yyyy/MM/dd",
        decimal_separator="٫",
        group_separator="٬",
    ),
    "ur": LocaleInfo(
        code="ur",
        label="Urdu",
        native_name="اردو",
        direction=Direction.RTL,
        script="Arab",
        fallbacks=("en",),
        date_format="dd/MM/yyyy",
        decimal_separator=".",
        group_separator=",",
    ),
}


def catalog_manager() -> CatalogManager:
    """Build a catalog manager containing the V3 catalogs."""
    catalogs = {
        locale: MessageCatalog(
            locale=locale, messages=dict(messages), description="V3 refinement catalog"
        )
        for locale, messages in ADDITIONAL_CATALOGS.items()
    }
    catalogs["en"] = MessageCatalog(
        locale="en", messages=dict(EN_MESSAGES), description="V3 refinement base catalog"
    )
    manager = CatalogManager()
    for locale, catalog in catalogs.items():
        existing = manager.catalog(locale)
        manager.register(existing.merge(catalog) if existing is not None else catalog)
    return manager


def locale_direction(locale: str) -> str:
    """Return the resolved direction for a V3 or V2 locale."""
    normalized = normalize_locale(locale)
    if normalized in V3_LOCALES:
        return V3_LOCALES[normalized].direction.value
    from redscribe.v2.a11y.i18n.locales import direction_for

    return direction_for(locale).value


def format_value(request: FormatRequest) -> FormatResult:
    """Format one value using locale-aware V2 primitives."""
    locale = normalize_locale(request.locale or "en")
    options = dict(request.options)
    value = request.value
    kind = request.kind
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError("Number value must be numeric")
        text = format_number(
            value,
            locale=locale,
            minimum_fraction_digits=int(options.get("min_digits", 0)),
            maximum_fraction_digits=int(options.get("max_digits", 3)),
            grouping=bool(options.get("grouping", True)),
        )
    elif kind == "percent":
        text = format_percent(float(value), locale=locale, digits=int(options.get("digits", 0)))
    elif kind == "currency":
        text = format_currency(float(value), str(options.get("currency", "USD")), locale=locale)
    elif kind == "bytes":
        text = format_bytes(int(value), locale=locale, binary=bool(options.get("binary", False)))
    elif kind == "date":
        text = format_date(str(value), locale=locale)
    elif kind == "time":
        text = format_time(str(value), locale=locale)
    elif kind == "datetime":
        text = format_datetime(str(value), locale=locale)
    elif kind == "relative":
        text = format_relative_time(str(value), locale=locale, now=datetime.now(timezone.utc))
    elif kind == "plural":
        key = str(value or options.get("key") or "v3.search.results")
        count = int(options.get("count", 0))
        forms = plural_options(
            str(options.get("singular", "one item")),
            str(options.get("plural", "many items")),
            locale=locale,
        )
        overrides = {f"{key}.{category}": text for category, text in forms.items()}
        text = pluralize(key, count, locale=locale, overrides=overrides)
    elif kind == "ordinal":
        text = format_ordinal(int(value), locale=locale)
    elif kind == "duration":
        text = format_duration(int(value), locale=locale)
    elif kind == "range":
        text = format_range(int(value), int(options.get("end", 0)), locale=locale)
    elif kind == "list":
        items = value if isinstance(value, Sequence) and not isinstance(value, str) else []
        text = format_list([str(item) for item in items], locale=locale)
    else:
        raise ValueError(f"Unsupported format kind: {kind}")
    direction = locale_direction(locale)
    fallback = ""
    if locale not in V3_LOCALES and language_of(locale) not in {
        "en",
        "es",
        "fr",
        "de",
        "ar",
        "he",
        "ja",
        "zh",
    }:
        fallback = "en"
    return FormatResult(
        locale=locale,
        kind=kind,
        text=text,
        direction=direction,
        bidi_isolated=direction == "rtl",
        fallback=fallback,
    )


def format_batch(requests: Sequence[FormatRequest]) -> tuple[FormatResult, ...]:
    """Format a sequence of requests, keeping failures as visible text."""
    results: list[FormatResult] = []
    for request in requests:
        try:
            results.append(format_value(request))
        except (TypeError, ValueError) as error:
            results.append(
                FormatResult(
                    locale=normalize_locale(request.locale),
                    kind=request.kind,
                    text=f"invalid: {error}",
                    direction=locale_direction(request.locale),
                )
            )
    return tuple(results)


def round_trip(value: int | float, locale: str, *, digits: int = 2) -> dict[str, Any]:
    """Verify that a localized number can be parsed back to its source value."""
    formatted = format_number(
        value,
        locale=normalize_locale(locale),
        minimum_fraction_digits=digits,
        maximum_fraction_digits=digits,
    )
    parsed = normalize_number_string(formatted, locale=normalize_locale(locale))
    number = float(parsed.replace("−", "-"))
    return {
        "locale": normalize_locale(locale),
        "formatted": formatted,
        "parsed": parsed,
        "value": number,
        "exact": abs(number - float(value)) < 1e-9,
    }


def translate(
    locale: str,
    key: str,
    params: Mapping[str, Any] | None = None,
    *,
    manager: CatalogManager | None = None,
) -> dict[str, Any]:
    """Translate a V3 key with explicit fallback reporting."""
    catalogs = manager or catalog_manager()
    normalized = normalize_locale(locale)
    resolved = ""
    used = ""
    for candidate in fallback_chain(normalized):
        catalog = catalogs.catalog(candidate)
        if catalog is not None and catalog.has(key):
            resolved = catalog.get(key, **dict(params or {}))
            used = candidate
            break
    if not resolved:
        resolved = key
        english = catalogs.catalog("en")
        used = "en" if english is not None and english.has(key) else ""
    return {
        "locale": normalized,
        "key": key,
        "message": resolved,
        "used_locale": used,
        "missing": resolved == key,
        "direction": locale_direction(used or normalized),
    }


def catalog_report(manager: CatalogManager | None = None) -> dict[str, Any]:
    """Return translation coverage for the V3 message keys."""
    catalogs = manager or catalog_manager()
    per_locale: dict[str, dict[str, Any]] = {}
    for locale in catalogs.locales:
        catalog = catalogs.catalog(locale)
        if catalog is None:
            continue
        present = sum(1 for key in V3_MESSAGE_KEYS if catalog.has(key))
        per_locale[locale] = {
            "count": len(catalog.keys),
            "v3_keys": present,
            "total_v3_keys": len(V3_MESSAGE_KEYS),
            "coverage": round(present / len(V3_MESSAGE_KEYS) * 100.0, 1),
        }
    return {
        "locales": sorted(per_locale),
        "keys": list(V3_MESSAGE_KEYS),
        "per_locale": per_locale,
        "additional_locales": [info.as_dict() for info in V3_LOCALES.values()],
    }


def locale_profiles() -> tuple[dict[str, Any], ...]:
    """Return all locale options, including the V3-only catalogs."""
    base = locale_options()
    for info in sorted(V3_LOCALES.values(), key=lambda item: item.code):
        base.append(
            {
                "value": info.code,
                "label": info.label,
                "native_name": info.native_name,
                "direction": info.direction.value,
                "script": info.script,
            }
        )
    return tuple(sorted(base, key=lambda item: item["value"]))


def isolate(text: str, *, locale: str = "") -> str:
    """Isolate formatted text when it will be embedded in opposite direction."""
    return isolate_text(text) if locale_direction(locale) == "rtl" else text


__all__ = [
    "ADDITIONAL_CATALOGS",
    "EN_MESSAGES",
    "FORMAT_KINDS",
    "V3_LOCALES",
    "V3_MESSAGE_KEYS",
    "catalog_manager",
    "catalog_report",
    "format_batch",
    "format_value",
    "isolate",
    "locale_direction",
    "locale_profiles",
    "round_trip",
    "translate",
]
