from __future__ import annotations

from datetime import datetime

import pytest

from redscribe.v2.a11y.i18n.catalogs import (
    BUILTIN_CATALOGS,
    CatalogManager,
    MessageCatalog,
    builtin_catalog,
    placeholders_of,
)
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
    formatting_options,
    localize_digits,
    normalize_number_string,
    plural_options,
    pluralize,
    rounding_step,
)
from redscribe.v2.a11y.i18n.locales import (
    Direction,
    all_locales,
    best_match_header,
    direction_for,
    direction_label,
    fallback_chain,
    is_rtl,
    is_valid_locale,
    language_of,
    locale_options,
    locale_summary,
    normalize_locale,
    parse_accept_language,
    plural_category,
    region_of,
)
from redscribe.v2.a11y.i18n.rtl import (
    analyze_rtl_tree,
    bidi_warnings,
    direction_class,
    direction_css_vars,
    document_direction,
    has_rtl_characters,
    infer_direction,
    isolate_embedded,
    isolate_text,
    logical_border,
    logical_side,
    mirror_text,
    physical_side,
    rtl_css_class_map,
    side_summary,
    strip_bidi_controls,
)
from redscribe.v2.a11y.models import ElementNode
from redscribe.v2.a11y.preferences import (
    MemoryPreferenceStore,
    PreferenceRecord,
    PreferenceService,
    default_preferences,
    effective_direction,
    export_preferences,
    import_preferences,
    merge_preferences,
    migrate_payload,
    preference_diff,
    preference_fallbacks,
    preference_schema,
    snapshot_signature,
    validate_preferences,
)
from redscribe.v2.a11y.theme_contrast import (
    accessible_status_colors,
    apply_theme_fixes,
    contrast_checks_from_payload,
    contrast_grid,
    invalid_colors,
    relative_color_distance,
    suggest_theme_fixes,
    theme_contrast_score,
    theme_issue_summary,
    validate_theme,
    validate_themes,
)
from redscribe.v2.a11y.themes import (
    BUILTIN_THEMES,
    ThemeRegistry,
    create_theme,
    css_to_token,
    generate_accent_palette,
    missing_tokens,
    normalize_theme_name,
    resolve_theme,
    theme_css,
    theme_diff,
    theme_from_payload,
    theme_options,
    theme_summary,
    themes_css,
    token_catalog,
    token_to_css,
    token_values,
    validate_token_name,
)


def test_locale_normalization_and_lookup() -> None:
    assert normalize_locale("en_US") == "en-US"
    assert is_valid_locale("en-US") is True
    assert is_valid_locale("bad!") is False
    assert language_of("fr-CA") == "fr"
    assert region_of("fr-CA") == "CA"
    assert direction_for("ar") is Direction.RTL
    assert direction_for("en") is Direction.LTR
    assert is_rtl("he") is True
    assert is_rtl("ja") is False
    assert len(all_locales()) >= 10
    assert len(locale_options()) == len(all_locales())


def test_fallback_chains_and_accept_language_matching() -> None:
    assert fallback_chain("en-GB") == ("en-GB", "en")
    assert "ar" in fallback_chain("ar-EG")
    assert parse_accept_language("fr-FR,fr;q=0.9,en;q=0.5") == ("fr-FR", "fr", "en")
    assert best_match_header("fr-FR,fr;q=0.9", ["en", "fr", "de"]) == "fr"
    assert best_match_header("zz", ["en", "fr"]) == "en"


def test_plural_categories_and_locale_summary() -> None:
    assert plural_category("en", 1) == "one"
    assert plural_category("en", 4) == "other"
    assert plural_category("ar", 0) == "zero"
    summary = locale_summary("ar")
    assert summary["supported"] is True
    assert summary["direction"] == "rtl"
    assert direction_label(Direction.RTL) == "Right to left"


def test_message_catalog_interpolates_and_subsets() -> None:
    catalog = builtin_catalog("en")
    assert placeholders_of("Hi {name}, {count}") == ("name", "count")
    assert catalog.get("action.save") == "Save"
    assert catalog.get("a11y.audit.score", score=91) == "Accessibility score: 91"
    assert catalog.get("missing.key") == "missing.key"
    assert catalog.missing_placeholders("a11y.audit.score") == ("score",)
    assert catalog.has("action.save") is True
    assert catalog.raw("action.save") == "Save"
    subset = catalog.subset(["action."])
    assert len(subset.keys) > 0
    assert all(key.startswith("action.") for key in subset.keys)
    assert len(catalog.entries()) == len(catalog.keys)


def test_catalog_manager_translates_with_fallbacks() -> None:
    manager = CatalogManager()
    assert manager.translate("es", "action.save") == "Guardar"
    assert manager.translate("en-GB", "action.save") == "Save"
    assert manager.translate("en", "unknown.key") == "unknown.key"
    manager.register(MessageCatalog("en", {"custom.key": "Custom"}))
    assert manager.translate("en", "custom.key") == "Custom"
    assert "fr" in manager
    assert manager.coverage("en")["coverage"] == 100.0


def test_catalog_serialization_and_builtin_coverage() -> None:
    catalog = MessageCatalog("test", {"a": "A"}, "Demo")
    assert catalog.as_dict()["description"] == "Demo"
    assert len(catalog.merge(MessageCatalog("test", {"b": "B"})).keys) == 2
    assert set(BUILTIN_CATALOGS) >= {"en", "es", "fr", "de", "ar", "he", "ja", "zh"}
    manager = CatalogManager()
    report = manager.coverage_report()
    assert report["baseline"] == "en"
    assert report["locales"]["es"]["coverage"] == pytest.approx(100.0)


def test_number_and_percent_formatting() -> None:
    assert format_number(1234, locale="en") == "1,234"
    assert format_number(1234, locale="de") == "1.234"
    assert format_number(1234, locale="ar").endswith("٢٣٤")
    assert format_percent(0.25, locale="en", digits=0) == "25%"
    assert format_percent(25, locale="en", digits=0, already_scaled=True) == "25%"
    assert localize_digits("123", "ar") == "١٢٣"
    assert normalize_number_string("1,234.5", locale="en") == "1234.5"
    assert rounding_step(1.239, decimals=2) == pytest.approx(1.23)


def test_currency_bytes_and_list_formatting() -> None:
    assert "$" in format_currency(12.5, "USD", locale="en")
    assert format_currency(12.5, "USD", locale="en") == "$12.5"
    assert format_bytes(2048).endswith("KB")
    assert format_bytes(1024 * 1024, binary=True).endswith("MiB")
    assert format_list(["a", "b", "c"], locale="en") == "a, b and c"
    assert format_list(["a", "b"], locale="en") == "a and b"


def test_date_time_and_relative_formatting() -> None:
    assert format_date("2026-11-18", locale="en") == "2026-11-18"
    assert format_date("2026-11-18", locale="ja") == "2026/11/18"
    assert format_time("2026-11-18T13:05:00Z", locale="en") == "13:05"
    assert format_time("2026-11-18T13:05:00Z", locale="en", with_seconds=True) == "13:05:00"
    assert format_datetime("2026-11-18T13:05:00Z", locale="en").startswith("2026-11-18")
    now = datetime.fromisoformat("2026-11-18T12:00:00+00:00")
    relative = format_relative_time("2026-11-18T10:00:00+00:00", now=now)
    assert "ago" in relative


def test_pluralization_and_formatting_options() -> None:
    overrides = {
        "plural.note.one": "{count} note",
        "plural.note.other": "{count} notes",
    }
    assert pluralize("plural.note", 1, locale="en", overrides=overrides) == "1 note"
    assert pluralize("plural.note", 2, locale="en", overrides=overrides) == "2 notes"
    assert pluralize("plural.note", 2, locale="en") == "plural.note.other"
    options = plural_options("one item", "many items", locale="en")
    assert options["one"] == "one item"
    assert options["other"] == "many items"
    config = formatting_options("ar")
    assert config["digits"] == "٠١٢٣٤٥٦٧٨٩"
    assert format_ordinal(1, locale="en") == "1st"
    assert format_ordinal(2, locale="en") == "2nd"
    assert "h" in format_duration(3661, locale="en")
    assert format_range(1, 10, locale="en") == "1-10"


def test_rtl_helpers_map_logical_sides_and_classes() -> None:
    assert document_direction("ar") == "rtl"
    assert document_direction("en", override="rtl") == "rtl"
    assert physical_side("start", locale="ar") == "right"
    assert logical_side("right", locale="ar") == "start"
    assert direction_class("ar") == "a11y-dir-rtl"
    assert direction_css_vars("ar")["--a11y-text-align"] == "right"
    assert logical_border("1px solid", locale="ar", side="start") == "right-border: 1px solid"
    assert rtl_css_class_map()["rtl"] == "a11y-dir-rtl"
    assert side_summary("ar")["inline_start"] == "right"


def test_rtl_text_helpers_isolate_mirror_and_warn() -> None:
    isolated = isolate_text("hello")
    assert isolated.startswith("\u2068")
    assert strip_bidi_controls(isolated) == "hello"
    assert mirror_text("hello (world)", locale="ar") == "hello )world("
    assert "hello" in isolate_embedded("hello", fragments=["hello"], locale="ar")
    assert bidi_warnings("hello (world)", locale="ar") == ["isolate_latin_fragments"]
    assert has_rtl_characters("שלום") is True
    assert infer_direction("שלום").value == "rtl"


def test_rtl_tree_analysis_reports_finds_per_node() -> None:
    nodes = [ElementNode("p", {}, "hello (world)", path="/0")]
    result = analyze_rtl_tree(nodes, locale="ar")
    assert result["direction"] == "rtl"
    assert result["count"] == 1
    assert result["findings"][0]["warnings"] == ["isolate_latin_fragments"]


def test_theme_tokens_and_names_normalize() -> None:
    assert token_to_css("surface_alt") == "--a11y-surface-alt"
    assert css_to_token("--a11y-surface-alt") == "surface_alt"
    assert normalize_theme_name("My Theme") == "my-theme"
    assert validate_token_name("text_muted") == "text_muted"
    assert missing_tokens(BUILTIN_THEMES["graphite"]) == ()
    catalog = token_catalog(BUILTIN_THEMES["paper"])
    assert any(token.category == "text" for token in catalog)
    assert token_values(BUILTIN_THEMES["paper"], ["surface"])


def test_theme_creation_resolution_and_css() -> None:
    theme = create_theme("custom", "Custom", tokens={"accent": "#123456"})
    assert theme.tokens["accent"] == "#123456"
    resolved = resolve_theme("paper", overrides={"accent": "#010203"})
    assert resolved.tokens["accent"] == "#010203"
    css = theme_css(theme, selector="[data-theme='custom']")
    assert css.startswith("[data-theme='custom'] {")
    assert "--a11y-accent: #123456;" in css
    assert "data-a11y-theme" in themes_css() or "--a11y-" in themes_css()
    assert generate_accent_palette(210)["accent"]


def test_theme_from_payload_and_diff() -> None:
    theme = theme_from_payload(
        {"name": "My Theme", "label": "Mine", "mode": "light", "tokens": {"text": "#111111"}}
    )
    assert theme.name == "my-theme"
    assert theme.tokens["text"] == "#111111"
    diff = theme_diff(theme, BUILTIN_THEMES["paper"])
    assert diff["first"] == "my-theme"
    assert diff["count"] >= 0
    summary = theme_summary(theme)
    assert summary["label"] == "Mine"
    assert any(option["value"] == "graphite" for option in theme_options())


def test_theme_registry_registers_resolves_and_validates() -> None:
    registry = ThemeRegistry()
    assert "graphite" in registry
    assert registry.get("missing") is None
    with pytest.raises(ValueError, match="Unknown theme"):
        registry.require("missing")
    custom = create_theme("reg theme", "Registered")
    registry.register(custom)
    assert "reg-theme" in registry
    assert registry.resolve("reg-theme").name == "reg-theme"
    assert registry.remove("reg-theme") is not None
    validation = registry.validate()
    assert "valid" in validation or "themes" in validation


def test_theme_contrast_validation_and_fixes() -> None:
    theme = BUILTIN_THEMES["high-contrast-dark"]
    result = validate_theme(theme)
    assert result.passed is True
    assert result.report.score == pytest.approx(100.0)
    summary = theme_issue_summary(result)
    assert summary["passed"] is True
    assert summary["checked"] == len(result.report.pairs)
    assert theme_contrast_score(theme) == pytest.approx(100.0)
    assert suggest_theme_fixes(theme) == {}
    assert apply_theme_fixes(theme) == theme
    assert invalid_colors(theme) == {}


def test_theme_contrast_grid_and_custom_combinations() -> None:
    grid = contrast_grid(BUILTIN_THEMES["paper"])
    assert grid
    combinations = contrast_checks_from_payload(
        {
            "combinations": [
                "text_on_surface",
                {"foreground": "#000", "background": "#fff", "graphical": True},
            ]
        }
    )
    assert combinations[0] == ("text", "surface", False)
    assert combinations[1][2] is True
    result = validate_theme(
        BUILTIN_THEMES["paper"],
        combinations=[("text", "surface", False)],
    )
    assert len(result.report.pairs) == 1


def test_validate_themes_reports_each_theme() -> None:
    report = validate_themes(
        {"paper": BUILTIN_THEMES["paper"], "graphite": BUILTIN_THEMES["graphite"]}
    )
    assert report["target"] == "AA"
    assert "paper" in report["themes"]
    assert "graphite" in report["themes"]
    assert relative_color_distance(BUILTIN_THEMES["paper"], BUILTIN_THEMES["graphite"]) > 0
    colors = accessible_status_colors("#ffffff")
    assert set(colors) == {"success", "warning", "danger", "info"}


def test_default_preferences_and_validation() -> None:
    defaults = default_preferences()
    assert defaults.locale == "en"
    assert defaults.theme == "graphite"
    assert defaults.font_scale == 1.0
    assert snapshot_signature(defaults) == snapshot_signature(default_preferences())
    snapshot, issues = validate_preferences({"locale": "fr", "font_scale": 1.2})
    assert issues == ()
    assert snapshot.locale == "fr"
    assert snapshot.font_scale == 1.2


def test_preferences_validation_clamps_out_of_range_values() -> None:
    snapshot, issues = validate_preferences(
        {
            "font_scale": 3.0,
            "direction": "sideways",
            "shortcuts": {"save": "ctrl+s", "empty": []},
            "reduce_motion": "yes",
        }
    )
    fields = {issue.field for issue in issues}
    assert {"font_scale", "direction", "shortcuts.save", "reduce_motion"} <= fields
    assert snapshot.font_scale == 1.75
    assert snapshot.direction is Direction.AUTO
    assert snapshot.reduce_motion is False


def test_preference_migration_handles_legacy_fields() -> None:
    migrated = migrate_payload({"version": 1, "rtl": True, "fontScale": 1.3, "reduceMotion": True})
    assert migrated["direction"] == "rtl"
    assert migrated["font_scale"] == 1.3
    assert migrated["reduce_motion"] is True
    snapshot, issues = validate_preferences(migrated)
    assert issues == ()
    assert effective_direction(snapshot) is Direction.RTL
    assert "en" in preference_fallbacks(snapshot)


def test_preference_merge_and_diff() -> None:
    current = default_preferences()
    merged = merge_preferences(current, {"locale": "de", "reduce_motion": True}, now="now")
    assert merged.locale == "de"
    assert merged.reduce_motion is True
    assert merged.revision == current.revision + 1
    assert merged.updated_at == "now"
    diff = preference_diff(current, merged)
    assert diff["count"] == 2
    assert "locale" in diff["changed"]


def test_preference_export_import_roundtrip() -> None:
    snapshot = default_preferences(locale="es", theme="paper")
    record = PreferenceRecord(snapshot=snapshot)
    exported = export_preferences(record)
    assert exported["schema"] == "redscribe.a11y.preferences"
    restored = import_preferences(exported)
    assert restored.snapshot.locale == "es"
    assert restored.snapshot.theme == "paper"


def test_preference_schema_describes_all_fields() -> None:
    schema = preference_schema()
    assert schema["version"] == 2
    assert set(schema["fields"]) >= {
        "locale",
        "theme",
        "direction",
        "font_scale",
        "reduce_motion",
        "high_contrast",
        "screen_reader_hints",
        "focus_ring_boost",
        "shortcuts",
    }
    assert schema["fields"]["font_scale"]["max"] == 1.75


def test_memory_preference_store_and_service_crud() -> None:
    service = PreferenceService(MemoryPreferenceStore())
    assert service.current().locale == "en"
    updated = service.update({"locale": "fr", "theme": "paper"}, profile="study")
    assert updated.profile == "study"
    assert service.current("study").locale == "fr"
    assert service.effective("study")["direction"] == "ltr"
    assert service.profiles() == ("study",)
    exported = service.export("study")
    assert exported["preferences"]["theme"] == "paper"
    service.import_record(exported, profile="restored")
    assert service.current("restored").locale == "fr"
    reset = service.reset(profile="restored")
    assert reset.snapshot.locale == "en"
    assert isinstance(service.shortcut_bindings("restored"), dict)
