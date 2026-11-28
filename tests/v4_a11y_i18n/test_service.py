"""Service-level tests: audits, catalogs, formatting, motion, and tours."""

from __future__ import annotations

import pytest

from redscribe.v4.a11y_i18n.service import (
    A11yAuditor,
    AuditError,
    FormattingError,
    I18nCatalog,
    LocaleFormatter,
    MotionError,
    MotionPolicyResolver,
    TourEngine,
    TourError,
    TranslationError,
    default_rules,
    default_tour_steps,
    english_catalog,
    interpolate,
    plural_category,
)
from redscribe.v4.a11y_i18n.types import (
    AuditRule,
    AuditSeverity,
    Direction,
    LocaleCatalog,
    MessageId,
    MotionPreference,
    PluralCategory,
    PluralForms,
    RuleId,
    TourStatus,
    TourStep,
    UiDescriptor,
    placeholder_names,
)


def descriptor(**overrides: object) -> UiDescriptor:
    values: dict[str, object] = {
        "id": "save-button",
        "role": "button",
        "label": "Save",
        "focusable": True,
        "visible": True,
        "contrast_ratio": 7.5,
        "tab_index": 0,
    }
    values.update(overrides)
    return UiDescriptor(
        id=str(values["id"]),
        role=str(values["role"]),
        label=str(values["label"]),
        focusable=bool(values["focusable"]),
        visible=bool(values["visible"]),
        contrast_ratio=float(values["contrast_ratio"]),
        tab_index=int(values["tab_index"]),
    )


def french_catalog() -> LocaleCatalog:
    return LocaleCatalog(
        "fr",
        Direction.LTR,
        {
            MessageId.WELCOME: "Bienvenue dans RedScribe",
            MessageId.SAVE: "Enregistrer",
            MessageId.LOADING: "Chargement de {items} éléments",
            MessageId.AUDIT_SUMMARY: "{count} problèmes sur {targets} éléments",
            MessageId.ITEMS_COUNT: "{count} élément",
        },
    )


def arabic_catalog() -> LocaleCatalog:
    return LocaleCatalog(
        "ar",
        Direction.RTL,
        {MessageId.WELCOME: "مرحبا", MessageId.SAVE: "حفظ", MessageId.ITEMS_COUNT: "عنصر"},
    )


# -- audit rules --------------------------------------------------------


def test_default_rules_cover_five_stable_ids() -> None:
    rules = default_rules()
    assert [rule.id for rule in rules] == [
        RuleId.MISSING_LABEL,
        RuleId.UNFOCUSABLE_INTERACTIVE,
        RuleId.LOW_CONTRAST,
        RuleId.DUPLICATE_ID,
        RuleId.SKIPPED_HEADING_LEVEL,
    ]
    assert all(rule.enabled for rule in rules)


def test_missing_label_triggers_for_unlabeled_button() -> None:
    report = A11yAuditor().audit([descriptor(label="   ")])
    assert len(report.issues_for(RuleId.MISSING_LABEL)) == 1
    assert "accessible name" in report.issues_for(RuleId.MISSING_LABEL)[0].detail


def test_missing_label_does_not_trigger_for_labeled_button() -> None:
    assert not A11yAuditor().audit([descriptor()]).issues_for(RuleId.MISSING_LABEL)


def test_missing_label_ignores_decorative_role() -> None:
    item = descriptor(role="decoration", label="")
    assert not A11yAuditor().audit([item]).issues_for(RuleId.MISSING_LABEL)


def test_unfocusable_interactive_triggers() -> None:
    item = descriptor(role="link", focusable=False)
    issues = A11yAuditor().audit([item]).issues_for(RuleId.UNFOCUSABLE_INTERACTIVE)
    assert len(issues) == 1
    assert issues[0].target == "save-button"
    assert "Tab key" in issues[0].suggestion


def test_unfocusable_interactive_does_not_trigger_for_static_text() -> None:
    item = descriptor(role="paragraph", focusable=False)
    assert not A11yAuditor().audit([item]).issues_for(RuleId.UNFOCUSABLE_INTERACTIVE)


def test_low_contrast_triggers_below_threshold() -> None:
    issues = A11yAuditor().audit([descriptor(contrast_ratio=4.49)]).issues_for(RuleId.LOW_CONTRAST)
    assert len(issues) == 1
    assert "4.49:1" in issues[0].detail


def test_low_contrast_accepts_exact_threshold_and_invisible_elements() -> None:
    auditor = A11yAuditor()
    assert not auditor.audit([descriptor(contrast_ratio=4.5)]).issues_for(RuleId.LOW_CONTRAST)
    hidden = descriptor(contrast_ratio=1.0, visible=False)
    assert not auditor.audit([hidden]).issues_for(RuleId.LOW_CONTRAST)


def test_duplicate_id_triggers_once_per_repeated_id() -> None:
    items = [descriptor(), descriptor(), descriptor(id="other")]
    issues = A11yAuditor().audit(items).issues_for(RuleId.DUPLICATE_ID)
    assert len(issues) == 1
    assert issues[0].target == "save-button"
    assert "appears 2 times" in issues[0].detail


def test_duplicate_id_does_not_trigger_for_unique_ids() -> None:
    items = [descriptor(id="one"), descriptor(id="two")]
    assert not A11yAuditor().audit(items).issues_for(RuleId.DUPLICATE_ID)


def test_skipped_heading_level_triggers_on_jump() -> None:
    items = [descriptor(id="h1", role="h1"), descriptor(id="h3", role="h3")]
    issues = A11yAuditor().audit(items).issues_for(RuleId.SKIPPED_HEADING_LEVEL)
    assert len(issues) == 1
    assert issues[0].target == "h3"
    assert "from h1 to h3" in issues[0].detail


def test_skipped_heading_level_allows_sequential_levels() -> None:
    items = [
        descriptor(id="h1", role="h1"),
        descriptor(id="h2", role="h2"),
        descriptor(id="h2b", role="h2"),
        descriptor(id="h3", role="h3"),
    ]
    assert not A11yAuditor().audit(items).issues_for(RuleId.SKIPPED_HEADING_LEVEL)


def test_skipped_heading_level_resets_after_non_heading() -> None:
    items = [
        descriptor(id="h1", role="h1"),
        descriptor(id="text", role="paragraph"),
        descriptor(id="h1b", role="h1"),
    ]
    assert not A11yAuditor().audit(items).issues_for(RuleId.SKIPPED_HEADING_LEVEL)


def test_audit_report_orders_errors_before_info() -> None:
    items = [
        descriptor(id="h1", role="h1"),
        descriptor(id="h3", role="h3"),
        descriptor(id="muted", label="", contrast_ratio=2.0),
    ]
    report = A11yAuditor().audit(items)
    assert [issue.severity for issue in report.issues] == [
        AuditSeverity.ERROR,
        AuditSeverity.WARNING,
        AuditSeverity.INFO,
    ]
    assert report.error_count == 1
    assert report.warning_count == 1
    assert report.severity_counts() == {"info": 1, "warning": 1, "error": 1}


def test_audit_report_serializes_and_tracks_descriptors() -> None:
    report = A11yAuditor().audit([descriptor()])
    data = report.to_dict()
    assert data["passed"] is True
    assert data["descriptor_count"] == 1
    assert len(data["rules_run"]) == 5
    assert data["issues"] == []


def test_audit_issues_helper_returns_plain_list() -> None:
    issues = A11yAuditor().audit_issues([descriptor(label="")])
    assert isinstance(issues, list)
    assert len(issues) == 1


def test_disabled_rule_does_not_run() -> None:
    auditor = A11yAuditor()
    auditor.set_enabled(RuleId.MISSING_LABEL, False)
    report = auditor.audit([descriptor(label="")])
    assert RuleId.MISSING_LABEL not in report.rules_run
    assert not report.issues
    assert all(rule.id is not RuleId.MISSING_LABEL for rule in auditor.rules(enabled_only=True))


def test_auditor_rejects_duplicate_rules() -> None:
    rule = AuditRule(RuleId.LOW_CONTRAST, "check", AuditSeverity.WARNING)
    with pytest.raises(AuditError, match="duplicate rule"):
        A11yAuditor([rule, rule])


def test_auditor_rejects_unknown_rule_lookup() -> None:
    auditor = A11yAuditor([AuditRule(RuleId.LOW_CONTRAST, "check", AuditSeverity.WARNING)])
    with pytest.raises(AuditError, match="unknown rule"):
        auditor.severity_for(RuleId.DUPLICATE_ID)


def test_auditor_uses_custom_rule_severity() -> None:
    auditor = A11yAuditor(
        [
            AuditRule(
                RuleId.LOW_CONTRAST,
                "custom check",
                AuditSeverity.ERROR,
            )
        ]
    )
    issues = auditor.audit([descriptor(contrast_ratio=2.0)]).issues
    assert issues[0].severity is AuditSeverity.ERROR


def test_set_enabled_preserves_order() -> None:
    auditor = A11yAuditor()
    auditor.set_enabled(RuleId.SKIPPED_HEADING_LEVEL, False)
    assert [rule.id for rule in auditor.rules()] == [rule.id for rule in default_rules()]


# -- translation and catalogs -------------------------------------------


def test_interpolates_named_placeholders_and_reports_missing() -> None:
    text, missing = interpolate("Hello {name}, {count} left", {"name": "Ada"})
    assert text == "Hello Ada, {count} left"
    assert missing == ("count",)


def test_interpolate_rejects_non_scalar_values() -> None:
    with pytest.raises(TranslationError, match="placeholder name must be a scalar"):
        interpolate("Hi {name}", {"name": ["Ada"]})


def test_translate_interpolates_english_template() -> None:
    result = I18nCatalog().translate(MessageId.LOADING, "en", {"items": 5})
    assert result.text == "Loading 5 items"
    assert not result.fallback_used
    assert result.to_dict()["message"] == "loading"


def test_translate_uses_registered_catalog() -> None:
    catalog = I18nCatalog()
    catalog.register(french_catalog())
    result = catalog.translate(MessageId.SAVE, "fr")
    assert result.text == "Enregistrer"
    assert result.resolved_locale == "fr"
    assert catalog.direction_for("ar") is Direction.LTR


def test_translate_falls_back_to_language_then_english() -> None:
    catalog = I18nCatalog()
    catalog.register(french_catalog())
    regional = catalog.translate(MessageId.WELCOME, "fr-CA")
    assert regional.resolved_locale == "fr"
    assert regional.fallback_used is False
    unknown = catalog.translate(MessageId.WELCOME, "zz-ZZ")
    assert unknown.text == "Welcome to RedScribe"
    assert unknown.resolved_locale == "en"
    assert unknown.fallback_used is True


def test_translate_falls_back_per_message() -> None:
    catalog = I18nCatalog()
    catalog.register(french_catalog())
    result = catalog.translate(MessageId.RETRY, "fr")
    assert result.text == "Try again"
    assert result.resolved_locale == "en"


def test_catalog_register_rejects_duplicate_and_allows_overwrite() -> None:
    catalog = I18nCatalog()
    catalog.register(french_catalog())
    with pytest.raises(TranslationError, match="catalog already registered"):
        catalog.register(french_catalog())
    catalog.register(french_catalog(), overwrite=True)
    assert catalog.available_locales() == ("en", "fr")


def test_catalog_helpers_report_coverage() -> None:
    catalog = I18nCatalog()
    catalog.register(french_catalog())
    catalog.register(arabic_catalog())
    assert catalog.has("fr")
    assert catalog.has("zz") is False
    assert MessageId.SAVE in catalog.audit_messages()
    assert MessageId.SNAPSHOT_SAVED in catalog.missing_messages("fr")
    assert catalog.missing_messages("ar")


def test_catalog_rejects_english_override_fallback() -> None:
    with pytest.raises(TranslationError, match="fallback catalog must use the en locale"):
        I18nCatalog(french_catalog())


def test_catalog_rejects_unknown_locale() -> None:
    catalog = I18nCatalog()
    with pytest.raises(ValueError, match="must be a locale tag"):
        catalog.translate(MessageId.SAVE, "english")


def test_plural_category_rules() -> None:
    assert plural_category("en", 1) is PluralCategory.ONE
    assert plural_category("en", 2) is PluralCategory.OTHER
    assert plural_category("fr", 0) is PluralCategory.ONE
    assert plural_category("ar", 0) is PluralCategory.ZERO
    assert plural_category("ar", 2) is PluralCategory.TWO
    assert plural_category("ar", 7) is PluralCategory.FEW
    assert plural_category("ar", 20) is PluralCategory.MANY
    assert plural_category("ja", 3) is PluralCategory.OTHER


def test_plural_category_rejects_non_integer() -> None:
    with pytest.raises(TranslationError, match="count must be an integer"):
        plural_category("en", True)  # type: ignore[arg-type]


def test_register_plural_and_translate_plural() -> None:
    catalog = I18nCatalog()
    with pytest.raises(TranslationError, match="no plural forms"):
        catalog.translate_plural(MessageId.AUDIT_SUMMARY, 2)
    catalog.register_plural(
        MessageId.AUDIT_SUMMARY,
        PluralForms(
            one="{count} issue on {targets} element", other="{count} issues on {targets} elements"
        ),
    )
    one = catalog.translate_plural(MessageId.AUDIT_SUMMARY, 1, params={"targets": 3})
    many = catalog.translate_plural(MessageId.AUDIT_SUMMARY, 4, params={"targets": 9})
    assert one.text == "1 issue on 3 element"
    assert many.text == "4 issues on 9 elements"


def test_register_plural_rejects_duplicate() -> None:
    catalog = I18nCatalog()
    with pytest.raises(TranslationError, match="plural already registered"):
        catalog.register_plural(MessageId.ITEMS_COUNT, PluralForms("a", "b"))


def test_built_in_items_count_plural() -> None:
    catalog = I18nCatalog()
    assert catalog.translate_plural(MessageId.ITEMS_COUNT, 1).text == "1 item"
    assert catalog.translate_plural(MessageId.ITEMS_COUNT, 3).text == "3 items"


def test_translate_plural_requires_integer_count() -> None:
    catalog = I18nCatalog()
    with pytest.raises(ValueError, match="count must be an integer"):
        catalog.translate_plural(MessageId.ITEMS_COUNT, "two")  # type: ignore[arg-type]


def test_english_catalog_is_complete_and_immutable() -> None:
    catalog = english_catalog()
    assert catalog.locale == "en"
    assert len(catalog.messages) >= 20
    assert all("{" not in value or placeholder_names(value) for value in catalog.messages.values())


# -- locale formatting --------------------------------------------------


def test_format_number_groups_by_locale() -> None:
    assert LocaleFormatter("en").format_number(1234567) == "1,234,567"
    assert LocaleFormatter("de").format_number(1234567) == "1.234.567"
    assert LocaleFormatter("fr").format_number(1234567) == "1 234 567"
    assert LocaleFormatter("en").format_number(-1234.5, 2) == "-1,234.50"
    assert LocaleFormatter("de").format_number(1234.5, 1) == "1.234,5"


def test_format_number_handles_small_values() -> None:
    assert LocaleFormatter("en").format_number(0) == "0"
    assert LocaleFormatter("ja").format_number(999) == "999"


def test_format_number_rejects_bad_arguments() -> None:
    formatter = LocaleFormatter("en")
    with pytest.raises(FormattingError, match="value must be a number"):
        formatter.format_number("123")  # type: ignore[arg-type]
    with pytest.raises(FormattingError, match="decimals must be between"):
        formatter.format_number(1, 9)


def test_format_date_uses_profile_order() -> None:
    assert LocaleFormatter("en").format_date(2026, 11, 28) == "11/28/2026"
    assert LocaleFormatter("en-GB").format_date(2026, 11, 28) == "28/11/2026"
    assert LocaleFormatter("fr").format_date(2026, 11, 28) == "28/11/2026"
    assert LocaleFormatter("ja").format_date(2026, 11, 28) == "2026/11/28"


def test_format_date_uses_custom_separator() -> None:
    assert LocaleFormatter("en").format_date(2026, 1, 2, "-") == "01-02-2026"


def test_format_date_validation() -> None:
    formatter = LocaleFormatter("en")
    with pytest.raises(FormattingError, match="month out of range"):
        formatter.format_date(2026, 13, 1)
    with pytest.raises(FormattingError, match="day out of range"):
        formatter.format_date(2026, 1, 32)
    with pytest.raises(FormattingError, match="year out of range"):
        formatter.format_date(0, 1, 1)
    with pytest.raises(FormattingError, match="date fields must be integers"):
        formatter.format_date(2026, 1.5, 1)  # type: ignore[arg-type]


def test_format_percent_and_duration() -> None:
    assert LocaleFormatter("en").format_percent(42.35) == "42.4%"
    assert LocaleFormatter("de").format_percent(42.35) == "42,4%"
    assert LocaleFormatter("en").format_duration(125) == "2:05"
    with pytest.raises(FormattingError, match="seconds must be a non-negative integer"):
        LocaleFormatter("en").format_duration(-1)


def test_formatter_rejects_unknown_locale() -> None:
    with pytest.raises(ValueError, match="must be a locale tag"):
        LocaleFormatter("not-a-locale")
    with pytest.raises(FormattingError, match="no format profile"):
        LocaleFormatter("pt")


# -- motion policy ------------------------------------------------------


def test_resolve_full_policy() -> None:
    policy = MotionPolicyResolver().resolve(MotionPreference.FULL)
    assert policy.preference is MotionPreference.FULL
    assert policy.duration_for("slow") == 380
    assert policy.animated


def test_resolve_subtle_policy_from_string() -> None:
    policy = MotionPolicyResolver().resolve("subtle")
    assert policy.duration_for("normal") == 100
    assert policy.duration_for("pulse") == 0


def test_reduce_motion_forces_off() -> None:
    policy = MotionPolicyResolver().resolve(MotionPreference.FULL, reduce_motion=True)
    assert policy.preference is MotionPreference.OFF
    assert not policy.animated
    assert all(value == 0 for value in policy.durations.values())


def test_resolve_transparency_flag() -> None:
    policy = MotionPolicyResolver().resolve("off", reduce_transparency=True)
    assert policy.reduce_transparency
    assert policy.to_dict()["preference"] == "off"


def test_strictest_preference() -> None:
    resolver = MotionPolicyResolver()
    assert (
        resolver.strictest(MotionPreference.FULL, MotionPreference.SUBTLE)
        is MotionPreference.SUBTLE
    )
    assert resolver.strictest(MotionPreference.OFF, MotionPreference.FULL) is MotionPreference.OFF


def test_css_variables_are_deterministic() -> None:
    resolver = MotionPolicyResolver()
    variables = resolver.css_variables(resolver.resolve("subtle"))
    assert variables == {
        "--v4-duration-fast": "60ms",
        "--v4-duration-normal": "100ms",
        "--v4-duration-slow": "160ms",
        "--v4-duration-pulse": "0ms",
    }


def test_resolver_rejects_incomplete_table() -> None:
    resolver = MotionPolicyResolver({MotionPreference.FULL: {"fast": 10}})
    with pytest.raises(MotionError, match="duration table missing keys"):
        resolver.resolve("full")


# -- tours --------------------------------------------------------------


def tour() -> TourEngine:
    return TourEngine.from_steps(default_tour_steps())


def test_tour_starts_not_started_and_previews_first_step() -> None:
    engine = tour()
    assert engine.snapshot().status is TourStatus.NOT_STARTED
    assert engine.current().id == "tour-controls"
    assert engine.snapshot().progress == 0.333


def test_tour_next_advances_and_visits() -> None:
    engine = tour()
    assert engine.start().status is TourStatus.IN_PROGRESS
    second = engine.next()
    assert second.index == 1
    assert second.visited_ids == ("tour-controls", "tour-audit")
    assert second.can_advance
    assert second.can_go_back


def test_tour_previous_does_not_go_below_zero() -> None:
    engine = tour()
    engine.start()
    state = engine.previous()
    assert state.index == 0
    assert not state.can_go_back


def test_tour_next_at_end_completes() -> None:
    engine = tour()
    engine.start()
    engine.next()
    engine.next()
    final = engine.next()
    assert final.status is TourStatus.COMPLETED
    assert final.index == 2
    assert not final.can_advance
    assert final.progress == 1.0


def test_tour_completion_records_step() -> None:
    engine = tour()
    engine.start()
    state = engine.complete()
    assert state.status is TourStatus.COMPLETED
    assert state.completed_ids == ("tour-controls",)


def test_tour_skip_marks_skipped() -> None:
    engine = tour()
    engine.start()
    state = engine.skip()
    assert state.status is TourStatus.SKIPPED
    assert state.can_advance is False


def test_tour_go_to_jumps_and_marks_progress() -> None:
    engine = tour()
    state = engine.go_to(2)
    assert state.index == 2
    assert state.visited_ids == ("tour-preview",)
    assert state.status is TourStatus.IN_PROGRESS


def test_tour_reset_clears_history() -> None:
    engine = tour()
    engine.start()
    engine.next()
    state = engine.reset()
    assert state.status is TourStatus.NOT_STARTED
    assert state.visited_ids == ()
    assert state.index == 0


def test_tour_finished_cannot_advance() -> None:
    engine = tour()
    engine.skip()
    with pytest.raises(TourError, match="already finished"):
        engine.next()


def test_tour_rejects_bad_indices() -> None:
    with pytest.raises(TourError, match="index out of range"):
        TourEngine.from_steps(default_tour_steps()).go_to(9)
    with pytest.raises(TourError, match="index out of range"):
        TourEngine.from_steps(default_tour_steps()).go_to(-1)


def test_tour_requires_unique_steps() -> None:
    step = TourStep("dup", "target", "Title", "Body")
    with pytest.raises(TourError, match="must be unique"):
        TourEngine.from_steps([step, step])


def test_tour_requires_at_least_one_step() -> None:
    with pytest.raises(TourError, match="requires at least one step"):
        TourEngine.from_steps([])


def test_tour_state_serialization() -> None:
    state = tour().start().to_dict()
    assert state["status"] == "in_progress"
    assert state["total"] == 3
    assert state["can_advance"] is True
