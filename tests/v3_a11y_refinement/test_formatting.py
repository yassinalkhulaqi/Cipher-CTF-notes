"""Locale-aware formatting, catalog, and translation tests."""

from __future__ import annotations

import pytest

from redscribe.v3.a11y_refinement.formatting import (
    ADDITIONAL_CATALOGS,
    FORMAT_KINDS,
    V3_LOCALES,
    V3_MESSAGE_KEYS,
    catalog_manager,
    catalog_report,
    format_batch,
    format_value,
    isolate,
    locale_direction,
    locale_profiles,
    round_trip,
    translate,
)
from redscribe.v3.a11y_refinement.models import FormatRequest


def request(kind: str, value: object, *, locale: str = "en", **options: object) -> FormatRequest:
    return FormatRequest(locale=locale, kind=kind, value=value, options=dict(options))


def test_format_number_uses_locale_separators() -> None:
    german = format_value(request("number", 12345.678, locale="de-DE", min_digits=2, max_digits=2))
    assert german.text == "12.345,68"
    assert german.locale == "de-DE"
    assert german.direction == "ltr"
    english = format_value(request("number", 12345.678, min_digits=2, max_digits=2))
    assert english.text == "12,345.68"


def test_format_scalar_kinds() -> None:
    assert format_value(request("percent", 0.125, digits=1)).text == "12.5%"
    assert format_value(request("currency", 12.5, currency="USD")).text == "$12.5"
    assert format_value(request("bytes", 2048, binary=True)).text.startswith("2 KiB")
    assert format_value(request("ordinal", 22)).text == "22nd"
    duration = format_value(request("duration", 3661)).text
    assert "1 h" in duration
    assert "1 min" in duration
    assert "1 s" in duration
    assert format_value(request("range", 3, end=7)).text == "3-7"
    assert format_value(request("list", ["a", "b", "c"])).text == "a, b and c"


def test_format_temporal_kinds() -> None:
    date = format_value(request("date", "2026-03-04"))
    assert date.text == "2026-03-04"
    datetime = format_value(request("datetime", "2026-03-04T09:30:00Z"))
    assert "2026-03-04" in datetime.text
    relative = format_value(request("relative", "2020-01-01T00:00:00Z"))
    assert "ago" in relative.text


def test_format_plural_uses_category() -> None:
    one = format_value(request("plural", "note", count=1, singular="one note", plural="many notes"))
    many = format_value(
        request("plural", "note", count=5, singular="one note", plural="many notes")
    )
    assert one.text == "one note"
    assert many.text == "many notes"


def test_format_value_rejects_bad_kind_and_value() -> None:
    with pytest.raises(ValueError, match="Unsupported format kind"):
        format_value(request("mystery", 1))
    with pytest.raises(ValueError, match="must be numeric"):
        format_value(request("number", True))


def test_format_batch_keeps_failures_visible() -> None:
    results = format_batch(
        [
            request("number", 42),
            request("nonsense", 42),
        ]
    )
    assert results[0].text == "42"
    assert results[1].text.startswith("invalid:")
    assert len(results) == 2


def test_number_round_trip_for_multiple_locales() -> None:
    for locale in ("en", "de-DE", "fr", "fa"):
        report = round_trip(1234.56, locale)
        assert report["exact"] is True
        assert report["formatted"] != report["parsed"] or locale == "en"


def test_locale_direction_metadata() -> None:
    assert locale_direction("ar") == "rtl"
    assert locale_direction("fa") == "rtl"
    assert locale_direction("ur") == "rtl"
    assert locale_direction("de-DE") == "ltr"
    assert V3_LOCALES["fa"].direction.value == "rtl"


def test_bidi_isolation_flag_for_rtl_values() -> None:
    result = format_value(request("number", 7, locale="ar"))
    assert result.bidi_isolated is True
    assert isolate("abc", locale="ar") != "abc"


def test_additional_catalogs_and_report() -> None:
    assert set(ADDITIONAL_CATALOGS) == {"pt-BR", "it", "nl", "ko", "fa", "ur"}
    report = catalog_report()
    assert set(report["locales"]) >= set(ADDITIONAL_CATALOGS) | {"en"}
    assert report["keys"] == list(V3_MESSAGE_KEYS)
    assert report["per_locale"]["fa"]["v3_keys"] > 0
    assert report["per_locale"]["en"]["coverage"] == 100.0


def test_translate_uses_fallback_and_interpolation() -> None:
    manager = catalog_manager()
    english = translate("en", "v3.search.results", {"count": 7}, manager=manager)
    assert english["message"] == "7 results"
    assert english["missing"] is False
    portuguese = translate("pt-BR", "v3.search.results", {"count": 3}, manager=manager)
    assert portuguese["message"] == "3 resultados"
    assert portuguese["used_locale"] == "pt-br" or portuguese["used_locale"] == "pt-BR"
    missing = translate("it", "v3.not.a.key", manager=manager)
    assert missing["missing"] is True
    assert missing["message"] == "v3.not.a.key"
    persian = translate("fa", "v3.search.results", {"count": 2}, manager=manager)
    assert persian["direction"] == "rtl"


def test_locale_profiles_include_new_catalogs() -> None:
    profiles = locale_profiles()
    codes = {item["value"] for item in profiles}
    assert {"pt-BR", "it", "nl", "ko", "fa", "ur"} <= codes
    assert any(item["direction"] == "rtl" for item in profiles)
    assert "list" in FORMAT_KINDS
