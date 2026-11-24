"""WCAG 2.2 rule catalog and audit behavior tests."""

from __future__ import annotations

from redscribe.v2.a11y.models import WcagLevel
from redscribe.v3.a11y_refinement.models import SurfaceSpec
from redscribe.v3.a11y_refinement.wcag22_rules import (
    ENHANCED_TARGET_SIZE,
    MIN_TARGET_SIZE,
    WCAG22_RULES,
    audit_surface,
    audit_surfaces,
    rule_by_id,
    rules_for_level,
    summarize_runs,
)


def test_rule_catalog_contains_wcag22_criteria() -> None:
    criteria = {rule.criterion for rule in WCAG22_RULES}
    expected = {"2.4.11", "2.4.12", "2.4.13", "2.5.7", "2.5.8", "3.2.6", "3.3.7", "3.3.8"}
    assert expected <= criteria
    assert all(rule.automated for rule in WCAG22_RULES)
    assert len({rule.rule_id for rule in WCAG22_RULES}) == len(WCAG22_RULES)


def test_rule_level_filtering() -> None:
    level_a = rules_for_level("A")
    level_aa = rules_for_level(WcagLevel.AA)
    level_aaa = rules_for_level("AAA")
    assert len(level_a) < len(level_aa) < len(level_aaa)
    assert "help.consistent" in {rule.rule_id for rule in level_a}
    assert "focus.not_obscured" in {rule.rule_id for rule in level_aa}
    assert "focus.not_obscured.enhanced" in {rule.rule_id for rule in level_aaa}


def test_rule_lookup() -> None:
    rule = rule_by_id("pointer.target_size")
    assert rule is not None
    assert rule.criterion == "2.5.8"
    assert rule.remediation
    assert rule_by_id("does.not.exist") is None


def test_clean_surface_has_no_findings() -> None:
    spec = SurfaceSpec(name="clean", label="Clean")
    run = audit_surface(spec)
    assert run.passed is True
    assert run.findings == ()
    assert run.score == 100.0
    assert run.checked == len(rules_for_level(WcagLevel.AA))
    assert len(run.passed_rules) == run.checked


def test_focus_rules_detect_obscured_focus() -> None:
    spec = SurfaceSpec(name="sticky", label="Sticky", focus_obscured="full")
    run = audit_surface(spec, level="AAA")
    rules = {item.rule_id for item in run.findings}
    assert "focus.not_obscured" in rules
    assert "focus.not_obscured.enhanced" in rules
    assert run.passed is False
    assert any(item.criterion == "2.4.12" for item in run.findings)


def test_focus_appearance_checks_width_and_contrast() -> None:
    thin = audit_surface(
        SurfaceSpec(name="thin", label="Thin", focus_indicator_width=1), level="AAA"
    )
    assert any(item.rule_id == "focus.appearance" for item in thin.findings)
    pale = audit_surface(
        SurfaceSpec(name="pale", label="Pale", focus_indicator_contrast=1.2), level="AAA"
    )
    assert any(item.rule_id == "focus.appearance" for item in pale.findings)
    assert "width" in thin.findings[0].details


def test_pointer_rules_check_drag_and_target_size() -> None:
    spec = SurfaceSpec(
        name="graph",
        label="Graph",
        drag_only=True,
        target_size=MIN_TARGET_SIZE - 1,
    )
    run = audit_surface(spec)
    rules = {item.rule_id for item in run.findings}
    assert "pointer.dragging" in rules
    assert "pointer.target_size" in rules
    assert any(item.severity == "serious" for item in run.findings)


def test_enhanced_target_size_warning() -> None:
    spec = SurfaceSpec(
        name="aaa",
        label="AAA surface",
        level=WcagLevel.AAA,
        target_size=ENHANCED_TARGET_SIZE - 4,
    )
    run = audit_surface(spec)
    assert any(item.rule_id == "pointer.target_size" for item in run.findings)
    assert any(item.severity == "minor" for item in run.findings)


def test_form_rules_detect_help_entry_and_auth() -> None:
    spec = SurfaceSpec(
        name="sync",
        label="Sync",
        has_help=False,
        repeated_entry=True,
        auth_captcha="puzzle",
    )
    run = audit_surface(spec)
    rules = {item.rule_id for item in run.findings}
    assert {"help.consistent", "form.redundant_entry", "auth.accessible"} <= rules


def test_enhanced_auth_rule_is_scoped_to_aaa() -> None:
    spec = SurfaceSpec(name="login", label="Login", auth_captcha="cognitive")
    aa = audit_surface(spec, level=WcagLevel.AA)
    aaa = audit_surface(spec, level=WcagLevel.AAA)
    assert "auth.accessible.enhanced" not in {item.rule_id for item in aa.findings}
    assert "auth.accessible.enhanced" in {item.rule_id for item in aaa.findings}


def test_content_and_keyboard_rules() -> None:
    spec = SurfaceSpec(
        name="weak",
        label="Weak",
        hover_content=True,
        non_text_contrast=1.9,
        screen_reader_labels=False,
        keyboard_reachable=False,
    )
    run = audit_surface(spec)
    rules = {item.rule_id for item in run.findings}
    assert {
        "content.hoverable",
        "contrast.non_text",
        "labels.screen_reader",
        "keyboard.reachable",
    } <= rules
    assert run.score < 100
    assert run.score <= 80


def test_locale_rule_detects_invalid_tag() -> None:
    run = audit_surface(SurfaceSpec(name="bad-locale", label="Bad", locale="english"))
    assert any(item.rule_id == "locale.direction" for item in run.findings)


def test_audit_batch_and_summary() -> None:
    specs = (
        SurfaceSpec(name="clean", label="Clean"),
        SurfaceSpec(name="bad", label="Bad", target_size=8, drag_only=True),
    )
    runs = audit_surfaces(specs)
    assert [run.surface for run in runs] == ["clean", "bad"]
    summary = summarize_runs(runs)
    assert summary["surfaces"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["findings"] == 2
    assert "2.5.8" in summary["criteria"]
    assert summarize_runs(())["score"] == 100.0
