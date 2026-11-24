"""Automated contrast check and repair tests."""

from __future__ import annotations

from redscribe.v2.a11y.contrast import contrast_ratio
from redscribe.v2.a11y.models import WcagLevel
from redscribe.v2.a11y.themes import create_theme
from redscribe.v3.a11y_refinement.contrast_automation import (
    DARK_TOKENS,
    LIGHT_TOKENS,
    auto_fix,
    automate,
    dual_theme_report,
    evaluate_target,
    parse_target_color,
    standard_targets,
    targets_from_payload,
    targets_from_theme,
)
from redscribe.v3.a11y_refinement.models import ContrastTarget


def test_standard_targets_cover_both_themes() -> None:
    targets = standard_targets()
    names = {item.name for item in targets}
    assert len(targets) == 12
    assert any(name.startswith("light.") for name in names)
    assert any(name.startswith("dark.") for name in names)
    assert "light.body.text" in names
    assert all(item.level == WcagLevel.AA for item in targets)


def test_standard_targets_pass_automation() -> None:
    report = automate(standard_targets(), repair=False)
    assert report.passed is True
    assert report.failures == ()
    assert report.score == 100.0
    assert all(item["passed"] for item in report.pairs)


def test_targets_from_theme_derive_pairs() -> None:
    theme = create_theme("paper", "Paper", mode="light", tokens=dict(LIGHT_TOKENS))
    targets = targets_from_theme(theme, prefix="v3")
    assert len(targets) == 6
    assert targets[0].name == "v3.paper.body.text"
    assert targets[0].foreground == LIGHT_TOKENS["text"]


def test_targets_from_payload_explicit_list() -> None:
    payload = {
        "targets": [
            {"name": "custom", "foreground": "#000", "background": "#fff"},
            {"name": "graph", "fg": "#777", "bg": "#fff", "graphical": True},
            {"name": "invalid"},
        ]
    }
    targets = targets_from_payload(payload)
    assert [item.name for item in targets] == ["custom", "graph"]
    assert targets[1].graphical is True


def test_targets_from_payload_palette_and_defaults() -> None:
    palette_payload = {
        "palette": {
            "muted": {"foreground": "#777777", "background": "#ffffff"},
            "ignored": {"foreground": 42},
        }
    }
    targets = targets_from_payload(palette_payload)
    assert len(targets) == 1
    assert targets[0].name == "muted"
    assert targets_from_payload({}) == standard_targets()


def test_evaluate_target_reports_required_ratio() -> None:
    normal = evaluate_target(ContrastTarget("normal", "#000000", "#ffffff"))
    assert normal["passed"] is True
    assert normal["required"] == 4.5
    graphic = evaluate_target(ContrastTarget("graphic", "#777777", "#ffffff", graphical=True))
    assert graphic["required"] == 3.0
    large = evaluate_target(ContrastTarget("large", "#777777", "#ffffff", font_size=24))
    assert large["required"] == 3.0
    aaa = evaluate_target(ContrastTarget("aaa", "#777777", "#ffffff", level=WcagLevel.AAA))
    assert aaa["required"] == 7.0


def test_auto_fix_produces_passing_color() -> None:
    target = ContrastTarget("faint", "#cccccc", "#ffffff")
    fix = auto_fix(target)
    assert fix.before_ratio < fix.required
    assert fix.after_ratio >= fix.required
    assert fix.direction in {"foreground", "background"}
    assert contrast_ratio(fix.foreground, fix.background) >= fix.required


def test_automate_generates_minimal_fixes_and_suggestions() -> None:
    targets = (
        ContrastTarget("good", "#111111", "#ffffff"),
        ContrastTarget("bad", "#eeeeee", "#ffffff"),
    )
    report = automate(targets)
    assert report.passed is False
    assert report.score == 50.0
    assert len(report.fixes) == 1
    assert report.fixes[0].name == "bad"
    assert report.suggestions[0].startswith("bad:")
    no_repair = automate(targets, repair=False)
    assert no_repair.fixes == ()


def test_dual_theme_report_compares_light_and_dark() -> None:
    report = dual_theme_report()
    assert report["passed"] is True
    assert report["equivalent"] is True
    assert report["shared_failures"] == []
    assert report["score"] == 100.0
    assert report["light"]["pairs"]


def test_dual_theme_report_detects_shared_failures() -> None:
    light = create_theme(
        "bad-light", "Bad light", mode="light", tokens={**LIGHT_TOKENS, "text": "#ffffff"}
    )
    dark = create_theme(
        "bad-dark", "Bad dark", mode="dark", tokens={**DARK_TOKENS, "text": "#141419"}
    )
    report = dual_theme_report(light=light, dark=dark)
    assert report["passed"] is False
    assert report["shared_failures"]
    assert "body.text" in report["shared_failures"]


def test_parse_target_color_normalizes_short_hex() -> None:
    assert parse_target_color("#fff") == "#ffffff"
    assert parse_target_color("rgb(0, 0, 0)") == "#000000"
