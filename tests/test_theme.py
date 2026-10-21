from __future__ import annotations

from redscribe.ui.theme import DARK, LIGHT, Theme, difficulty_color, status_color

THEME = Theme(palette=DARK, ui_family="Inter", mono_family="Cascadia Code", base_size=11)


def test_dark_palette_uses_the_design_tokens() -> None:
    assert DARK.bg == "#0b0d12"
    assert DARK.surface == "#10131a"
    assert DARK.surface_alt == "#161a24"
    assert DARK.border == "#252c39"
    assert DARK.accent == "#ff4d6d"


def test_semantic_colors_are_shared_between_app_themes() -> None:
    assert (DARK.green, DARK.amber, DARK.blue, DARK.red) == (
        "#22c55e",
        "#f59e0b",
        "#3b82f6",
        "#ef4444",
    )
    assert DARK.purple == "#a855f7"
    assert (LIGHT.green, LIGHT.amber, LIGHT.blue, LIGHT.red, LIGHT.purple) == (
        "#15803d",
        "#a16207",
        "#1d4ed8",
        "#b91c1c",
        "#7e22ce",
    )


def test_status_colors_follow_semantic_meaning() -> None:
    assert status_color(THEME, "todo") == DARK.muted
    assert status_color(THEME, "active") == DARK.blue
    assert status_color(THEME, "done") == DARK.green
    assert status_color(THEME, "blocked") == DARK.red
    assert status_color(THEME, "unknown") == DARK.text


def test_difficulty_colors_include_purple_for_insane() -> None:
    assert difficulty_color(THEME, "") == DARK.muted
    assert difficulty_color(THEME, "easy") == DARK.green
    assert difficulty_color(THEME, "medium") == DARK.amber
    assert difficulty_color(THEME, "hard") == DARK.red
    assert difficulty_color(THEME, "insane") == DARK.purple


def test_font_helpers_clamp_and_compose_styles() -> None:
    assert THEME.font() == ("Inter", 11, "normal")
    assert THEME.font(2, "bold", mono=True, italic=True) == (
        "Cascadia Code",
        13,
        "bold italic",
    )
    assert THEME.font(-20) == ("Inter", 7, "normal")
