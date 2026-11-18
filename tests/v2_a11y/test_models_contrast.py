from __future__ import annotations

import pytest

from redscribe.v2.a11y.contrast import (
    Color,
    build_report,
    check_pair,
    coerce_color,
    contrast_grade_label,
    contrast_ratio,
    distance_between_colors,
    grade_contrast,
    hue_rotate,
    is_large_text,
    palette_pairs,
    parse_color,
    relative_luminance,
    required_ratio,
    suggest_background,
    suggest_foreground,
    summarize_report,
)
from redscribe.v2.a11y.models import (
    Direction,
    ElementNode,
    FocusMode,
    Severity,
    WcagLevel,
    coerce_wcag_level,
    severity_rank,
    wcag_rank,
)


def test_color_parses_hex_rgb_named_and_short_forms() -> None:
    assert parse_color("#fff") == Color(255, 255, 255)
    assert parse_color("#123") == Color(17, 34, 51)
    assert parse_color("#112233") == Color(17, 34, 51)
    assert parse_color("#11223344").alpha == pytest.approx(68 / 255)
    assert parse_color("rgb(1, 2, 3)") == Color(1, 2, 3)
    assert parse_color("rgba(1, 2, 3, 0.5)") == Color(1, 2, 3, 0.5)
    assert parse_color("silver") == Color(192, 192, 192)


def test_color_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        parse_color("")
    with pytest.raises(ValueError, match="Unsupported color"):
        parse_color("not-a-color")
    with pytest.raises(ValueError, match="red must be"):
        Color(300, 0, 0)
    with pytest.raises(ValueError, match="alpha must be"):
        Color(0, 0, 0, 1.2)


def test_color_helpers_transform_channels() -> None:
    color = Color(100, 120, 140, 0.5)
    assert color.channels == (100, 120, 140)
    assert color.with_alpha(0.25).alpha == 0.25
    assert color.to_hex() == "#64788c"
    assert color.to_hex(include_alpha=True) == "#64788c80"
    assert "rgba(" in color.to_rgb()
    assert color.lightened(0.5).red > color.red
    assert color.darkened(0.5).red < color.red
    assert color.blended_over(Color(255, 255, 255)).alpha == 1.0
    assert color.as_dict()["luminance"] >= 0


def test_coerce_color_accepts_instances_and_strings() -> None:
    color = Color(1, 2, 3)
    assert coerce_color(color) is color
    assert coerce_color("#010203") == color


def test_contrast_ratio_is_symmetric_and_bounded() -> None:
    ratio = contrast_ratio("#000000", "#ffffff")
    assert ratio == pytest.approx(21.0, rel=0.01)
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(ratio)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
    assert 1.0 <= contrast_ratio("#123456", "#abcdef") <= 21.0


def test_translucent_foreground_is_blended_before_comparison() -> None:
    opaque = contrast_ratio("#000000", "#ffffff")
    translucent = contrast_ratio("rgba(0, 0, 0, 0.5)", "#ffffff")
    assert translucent < opaque
    assert translucent > 1.0


def test_relative_luminance_and_distance_are_deterministic() -> None:
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert distance_between_colors("#000000", "#000000") == pytest.approx(0.0)
    assert distance_between_colors("#000000", "#ffffff") > 0


def test_hue_rotate_preserves_format_and_changes_channels() -> None:
    rotated = hue_rotate("#ff0000", 120)
    assert rotated != parse_color("#ff0000")
    assert rotated.to_hex().startswith("#")


def test_large_text_detection_uses_size_and_weight() -> None:
    assert is_large_text(19, bold=True) is True
    assert is_large_text(24) is True
    assert is_large_text(18, bold=True) is False
    assert is_large_text(16) is False


def test_required_ratio_tracks_level_and_context() -> None:
    assert required_ratio("A", font_size=16) == 4.5
    assert required_ratio("A", font_size=24) == 3.0
    assert required_ratio("AA", font_size=16) == 4.5
    assert required_ratio("AAA", font_size=16) == 7.0
    assert required_ratio("AAA", font_size=24) == 4.5
    assert required_ratio("AA", graphical=True) == 3.0
    assert required_ratio(WcagLevel.AA, large_text=True) == 3.0


def test_grade_contrast_exposes_every_level() -> None:
    grade = grade_contrast(21.0)
    assert grade["ratio"] == 21.0
    assert grade["best"] == "AAA"
    assert grade["grades"]["AA"] is True
    low = grade_contrast(2.0)
    assert low["grades"]["A"] is False
    assert low["best"] in {"fail", "none", "F"} or low["best"] != "AAA"


def test_check_pair_captures_context_and_pass_state() -> None:
    passed = check_pair("body", "#000000", "#ffffff")
    failed = check_pair("muted", "#777777", "#ffffff", font_size=14)
    assert passed.name == "body"
    assert passed.passed is True
    assert passed.required == 4.5
    assert failed.passed is False
    assert failed.level == WcagLevel.AA
    assert failed.as_dict()["ratio"] == pytest.approx(4.48, abs=0.02)


def test_check_pair_supports_graphical_and_large_text_overrides() -> None:
    pair = check_pair(
        "border",
        "#777777",
        "#ffffff",
        graphical=True,
        level="AAA",
    )
    assert pair.required == 3.0
    assert pair.passed is True
    large = check_pair(
        "heading",
        "#777777",
        "#ffffff",
        font_size=30,
        large_text=True,
        level="AAA",
    )
    assert large.required == 4.5


def test_suggestions_find_accessible_colors() -> None:
    foreground = suggest_foreground("#ffffff", minimum=4.5)
    background = suggest_background("#777777", minimum=4.5)
    assert contrast_ratio(foreground, "#ffffff") >= 4.5
    assert contrast_ratio("#777777", background) >= 4.5
    dark = suggest_foreground("#ffffff", minimum=4.5, prefer_light=False)
    assert contrast_ratio(dark, "#ffffff") >= 4.5


def test_build_report_accepts_mapping_definitions() -> None:
    report = build_report(
        {
            "body": {"foreground": "#000000", "background": "#ffffff"},
            "muted": {"foreground": "#999999", "background": "#ffffff"},
        },
        level="AA",
    )
    assert len(report.pairs) == 2
    assert len(report.failures) == 1
    assert report.score == pytest.approx(50.0)
    assert report.passed is False
    assert report.suggestions


def test_build_report_accepts_contrast_pairs_and_empty_input() -> None:
    pair = check_pair("body", "#000000", "#ffffff")
    report = build_report([pair])
    assert report.pairs == (pair,)
    assert report.failures == ()
    assert build_report().score == 100.0
    assert summarize_report(report)["passed"] is True
    assert contrast_grade_label(pair) in {"AAA", "AA", "A", "fail"}


def test_build_report_rejects_non_object_entries() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        build_report({"bad": "black"})


def test_palette_pairs_uses_expected_combinations() -> None:
    palette = {
        "text": "#000000",
        "text_muted": "#555555",
        "surface": "#ffffff",
        "surface_alt": "#f0f0f0",
        "accent": "#003366",
        "on_accent": "#ffffff",
        "border": "#888888",
    }
    pairs = palette_pairs(palette)
    names = {pair.name for pair in pairs}
    assert "text_on_surface" in names
    assert "on_accent_on_accent" in names
    assert any(pair.required == 3.0 for pair in pairs if "border" in pair.name)
    custom = palette_pairs(palette, combinations=[("text", "surface")])
    assert len(custom) == 1


def test_palette_pairs_skips_missing_tokens() -> None:
    assert palette_pairs({"text": "#000000"}) == []


def test_severity_and_wcag_ranks_are_ordered() -> None:
    assert severity_rank(Severity.INFO) < severity_rank(Severity.CRITICAL)
    assert severity_rank("unknown") == 0
    assert wcag_rank("A") < wcag_rank("AAA")
    assert wcag_rank("nonsense") == 0
    assert coerce_wcag_level("aaa") is WcagLevel.AAA
    assert coerce_wcag_level(WcagLevel.A) is WcagLevel.A
    with pytest.raises(ValueError):
        coerce_wcag_level("nope")


def test_element_node_serializes_and_walks_children() -> None:
    child = ElementNode("button", {"type": "button"}, "Save", path="/0/0")
    root = ElementNode("div", {}, "", (child,), path="/0")
    assert root.normalized_tag == "div"
    assert root.descendants() == [child]
    assert root.as_dict()["children"][0]["text"] == "Save"
    assert child.has_attr("type") is True
    assert child.has_attr("disabled") is False
    assert child.attr("missing", "fallback") == "fallback"


def test_enums_cover_expected_vocabulary() -> None:
    assert [level.value for level in WcagLevel] == ["A", "AA", "AAA"]
    assert Direction.RTL.value == "rtl"
    assert FocusMode.EDITOR.value == "editor"
    assert "critical" in {severity.value for severity in Severity}
