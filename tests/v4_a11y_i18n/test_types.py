"""Deterministic unit tests for the accessibility/i18n contracts."""

from __future__ import annotations

import pytest

from redscribe.v4.a11y_i18n.types import (
    AuditIssue,
    AuditRule,
    AuditSeverity,
    Direction,
    EmptyStateSpec,
    LocaleCatalog,
    MessageId,
    MotionPolicy,
    MotionPreference,
    PluralCategory,
    PluralForms,
    RuleId,
    TourStatus,
    TourStep,
    UiDescriptor,
    placeholder_names,
    require_id,
    require_locale,
    require_ratio,
    require_text,
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


def test_audit_severity_parse_is_case_insensitive() -> None:
    assert AuditSeverity.parse(" ERROR ") is AuditSeverity.ERROR
    assert AuditSeverity.parse("warning") is AuditSeverity.WARNING
    assert AuditSeverity.parse("info") is AuditSeverity.INFO
    with pytest.raises(ValueError, match="unknown audit severity"):
        AuditSeverity.parse("critical")


def test_audit_severity_ranks() -> None:
    assert AuditSeverity.INFO.rank < AuditSeverity.WARNING.rank
    assert AuditSeverity.WARNING.rank < AuditSeverity.ERROR.rank


def test_rule_id_parse_accepts_canonical_values() -> None:
    for rule in RuleId:
        assert RuleId.parse(rule.value) is rule
    assert RuleId.parse("LOW-CONTRAST") is RuleId.LOW_CONTRAST
    with pytest.raises(ValueError, match="unknown audit rule"):
        RuleId.parse("no-such-rule")


def test_message_id_parse_and_round_trip() -> None:
    for message in MessageId:
        assert MessageId.parse(message.value) is message
        assert MessageId.parse(message.value.upper()) is message
    with pytest.raises(ValueError, match="unknown message id"):
        MessageId.parse("missing.key")


def test_motion_preference_parse_and_strictness() -> None:
    assert MotionPreference.parse("FULL") is MotionPreference.FULL
    assert MotionPreference.parse("subtle") is MotionPreference.SUBTLE
    assert MotionPreference.parse("off") is MotionPreference.OFF
    assert MotionPreference.FULL.strictness < MotionPreference.SUBTLE.strictness
    assert MotionPreference.SUBTLE.strictness < MotionPreference.OFF.strictness
    with pytest.raises(ValueError, match="unknown motion preference"):
        MotionPreference.parse("fast")


def test_direction_parse() -> None:
    assert Direction.parse("rtl") is Direction.RTL
    assert Direction.parse(" LTR ") is Direction.LTR
    with pytest.raises(ValueError, match="unknown text direction"):
        Direction.parse("vertical")


def test_tour_status_values_are_stable() -> None:
    assert [status.value for status in TourStatus] == [
        "not_started",
        "in_progress",
        "completed",
        "skipped",
    ]


def test_plural_category_values() -> None:
    assert [category.value for category in PluralCategory] == [
        "zero",
        "one",
        "two",
        "few",
        "many",
        "other",
    ]


def test_require_text_rejects_non_string_and_empty() -> None:
    assert require_text("  hello  ", "value") == "hello"
    assert require_text("   ", "value", allow_empty=True) == ""
    with pytest.raises(ValueError, match="value must be a string"):
        require_text(12, "value")
    with pytest.raises(ValueError, match="value must not be empty"):
        require_text("  ", "value")
    with pytest.raises(ValueError, match="exceeds 3 characters"):
        require_text("abcd", "value", max_length=3)


def test_require_id_normalizes_and_validates() -> None:
    assert require_id("Save-Button", "id") == "save-button"
    with pytest.raises(ValueError, match="lowercase slug"):
        require_id("99 bad id", "id")
    with pytest.raises(ValueError, match="must not be empty"):
        require_id("", "id")


def test_require_locale_accepts_language_and_region() -> None:
    assert require_locale("en") == "en"
    assert require_locale("en-GB") == "en-GB"
    with pytest.raises(ValueError, match="must be a locale tag"):
        require_locale("english")
    with pytest.raises(ValueError, match="must be a locale tag"):
        require_locale("en-gb")


def test_require_ratio_bounds() -> None:
    assert require_ratio(4.5) == 4.5
    assert require_ratio(21) == 21.0
    with pytest.raises(ValueError, match="must be a number"):
        require_ratio("4.5")
    with pytest.raises(ValueError, match="out of range"):
        require_ratio(22.0)
    with pytest.raises(ValueError, match="out of range"):
        require_ratio(0.5)


def test_placeholder_names_are_ordered_and_unique() -> None:
    assert placeholder_names("Hi {name}, {count} left, {name}!") == ("name", "count")
    assert placeholder_names("no tokens") == ()
    assert placeholder_names("{a}{B}{a}") == ("a",)


def test_audit_rule_round_trip() -> None:
    rule = AuditRule(RuleId.LOW_CONTRAST, "  Text must contrast.  ", AuditSeverity.WARNING)
    assert rule.description == "Text must contrast."
    data = rule.to_dict()
    assert data == {
        "id": "low-contrast",
        "description": "Text must contrast.",
        "severity": "warning",
        "enabled": True,
    }
    assert AuditRule.from_dict(data) == rule


def test_audit_rule_rejects_empty_description() -> None:
    with pytest.raises(ValueError, match="description must not be empty"):
        AuditRule(RuleId.DUPLICATE_ID, "   ", AuditSeverity.INFO)


def test_audit_issue_round_trip_and_fingerprint() -> None:
    issue = AuditIssue(
        RuleId.MISSING_LABEL,
        "save",
        "No accessible name",
        "Add aria-label",
        AuditSeverity.ERROR,
    )
    assert issue.fingerprint == "missing-label:save"
    assert AuditIssue.from_dict(issue.to_dict()) == issue
    with pytest.raises(ValueError, match="suggestion must not be empty"):
        AuditIssue(RuleId.MISSING_LABEL, "save", "detail", " ")


def test_ui_descriptor_properties_and_round_trip() -> None:
    item = descriptor(role="h3", label="Section")
    assert item.heading_level == 3
    assert not item.interactive
    assert descriptor(role="link").interactive
    assert descriptor(role="img").heading_level is None
    assert UiDescriptor.from_dict(item.to_dict()) == item


def test_ui_descriptor_validation() -> None:
    with pytest.raises(ValueError, match="must be a lowercase slug"):
        descriptor(id="Bad ID")
    with pytest.raises(ValueError, match="contrast_ratio out of range"):
        descriptor(contrast_ratio=30.0)
    with pytest.raises(ValueError, match="tab_index must be >= -1"):
        descriptor(tab_index=-2)
    with pytest.raises(ValueError, match="tab_index must be an integer"):
        UiDescriptor(
            "x",
            "button",
            "x",
            True,
            True,
            4.5,
            True,  # type: ignore[arg-type]
        )
    assert descriptor(tab_index=-1).tab_index == -1


def test_plural_forms_fall_back_to_other() -> None:
    forms = PluralForms(one="one item", other="many items", zero="none")
    assert forms.form_for(PluralCategory.ONE) == "one item"
    assert forms.form_for(PluralCategory.OTHER) == "many items"
    assert forms.form_for(PluralCategory.ZERO) == "none"
    assert forms.form_for(PluralCategory.TWO) == "many items"
    assert PluralForms.from_dict(forms.to_dict()) == forms


def test_plural_forms_require_one_and_other() -> None:
    with pytest.raises(ValueError, match="one must not be empty"):
        PluralForms(one="", other="many")
    with pytest.raises(ValueError, match="other must not be empty"):
        PluralForms(one="one", other="")


def test_locale_catalog_round_trip_and_helpers() -> None:
    catalog = LocaleCatalog(
        "en-GB", Direction.LTR, {MessageId.SAVE: "Save", MessageId.CANCEL: "Cancel"}
    )
    assert catalog.language == "en"
    assert catalog.has(MessageId.SAVE)
    assert catalog.get(MessageId.CANCEL) == "Cancel"
    assert not catalog.has(MessageId.RETRY)
    assert catalog.with_message(MessageId.RETRY, "Again").has(MessageId.RETRY)
    data = catalog.to_dict()
    assert data["messages"] == {"save": "Save", "cancel": "Cancel"}
    assert LocaleCatalog.from_dict(data) == catalog


def test_locale_catalog_rejects_unknown_message_keys() -> None:
    with pytest.raises(ValueError, match="unknown message id"):
        LocaleCatalog("en", Direction.LTR, {"unknown.key": "text"})  # type: ignore[dict-item]


def test_locale_catalog_rejects_empty_translation() -> None:
    with pytest.raises(ValueError, match="messages\\[save\\] must not be empty"):
        LocaleCatalog("en", Direction.LTR, {MessageId.SAVE: "  "})


def test_motion_policy_round_trip_and_duration_lookup() -> None:
    policy = MotionPolicy(MotionPreference.SUBTLE, {"fast": 60, "slow": 160})
    assert policy.duration_for("fast") == 60
    assert policy.duration_for("pulse") == 0
    assert policy.animated
    assert MotionPolicy.from_dict(policy.to_dict()) == policy
    assert not MotionPolicy(MotionPreference.OFF, {"fast": 0}).animated


def test_motion_policy_validation() -> None:
    with pytest.raises(ValueError, match="duration fast must be a non-negative integer"):
        MotionPolicy(MotionPreference.FULL, {"fast": -1})
    with pytest.raises(ValueError, match="duration key must be a lowercase slug"):
        MotionPolicy(MotionPreference.FULL, {"Bad Key": 10})
    with pytest.raises(ValueError, match="must be a non-negative integer"):
        MotionPolicy(MotionPreference.FULL, {"fast": True})  # type: ignore[dict-item]


def test_tour_step_round_trip() -> None:
    step = TourStep("welcome", "control-grid", "Welcome", "Start here")
    assert step.to_dict() == {
        "id": "welcome",
        "target": "control-grid",
        "title": "Welcome",
        "body": "Start here",
    }
    assert TourStep.from_dict(step.to_dict()) == step
    with pytest.raises(ValueError, match="target must be a lowercase slug"):
        TourStep("welcome", "Bad Target", "Welcome", "Start here")


def test_empty_state_round_trip() -> None:
    spec = EmptyStateSpec("Nothing yet", "Try again later", "Refresh")
    assert spec.to_dict() == {
        "title": "Nothing yet",
        "body": "Try again later",
        "action_label": "Refresh",
    }
    assert EmptyStateSpec.from_dict(spec.to_dict()) == spec
    with pytest.raises(ValueError, match="action_label must not be empty"):
        EmptyStateSpec("Title", "Body", "")
