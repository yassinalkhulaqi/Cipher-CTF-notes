"""Tests for report themes and the theme registry."""

from __future__ import annotations

import pytest

from redscribe.v3.report_designer.themes import (
    DuplicateThemeError,
    ReportTheme,
    ThemeRegistry,
    ThemeTokens,
    builtin_themes,
    default_theme_registry,
)


def test_builtin_themes_are_distinct() -> None:
    themes = builtin_themes()
    assert tuple(theme.key for theme in themes) == ("client", "technical", "executive", "print")
    assert len({theme.digest() for theme in themes}) == 4
    assert themes[1].tokens.chars_per_line > themes[0].tokens.chars_per_line
    assert themes[2].tokens.heading_size_pt > themes[0].tokens.heading_size_pt
    assert themes[3].tokens.ink == "#000000"
    assert themes[3].tokens.cover_background == "#ffffff"
    assert all(theme.builtin for theme in themes)


def test_theme_tokens_validation_and_dimensions() -> None:
    tokens = ThemeTokens()
    assert tokens.page_dimensions_mm == (210, 297)
    landscape = ThemeTokens(orientation="landscape")
    assert landscape.page_dimensions_mm == (297, 210)
    letter = ThemeTokens(page_size="letter")
    assert letter.page_dimensions_mm == (216, 279)
    as_dict = tokens.as_dict()
    assert as_dict["lines_per_page"] == 48
    with pytest.raises(ValueError):
        ThemeTokens(base_size_pt=0)
    with pytest.raises(ValueError):
        ThemeTokens(margin_mm=100)
    with pytest.raises(ValueError):
        ThemeTokens(lines_per_page=2)
    with pytest.raises(ValueError):
        ThemeTokens(page_size="a3")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ThemeTokens(orientation="diagonal")  # type: ignore[arg-type]


def test_registry_lookup_and_fallback() -> None:
    registry = default_theme_registry()
    assert len(registry) == 4
    assert registry.keys() == ("client", "executive", "print", "technical")
    assert registry.get("technical").key == "technical"
    assert registry.get("unknown").key == "client"
    assert registry.has("print") is True
    assert registry.has("bogus") is False
    assert registry.default().key == "client"
    assert len(registry.summaries()) == 4
    assert registry.summaries()[0]["key"] == "client"
    assert registry.digest() == registry.digest()


def test_theme_isolation() -> None:
    registry = default_theme_registry()
    client = registry.get("client")
    technical = registry.get("technical")
    assert client.tokens is not technical.tokens
    assert client.with_tokens(ThemeTokens(accent="#ff0000")).tokens.accent == "#ff0000"
    assert client.tokens.accent == "#2f6fed"
    assert technical.tokens.accent == "#0f8f6a"
    custom = ReportTheme(
        key="custom",
        name="Custom",
        tokens=ThemeTokens(accent="#123456"),
        builtin=False,
    )
    registry.register(custom)
    assert registry.has("custom") is True
    assert registry.get("custom").tokens.accent == "#123456"
    assert registry.get("client").tokens.accent == "#2f6fed"
    assert custom.as_dict()["builtin"] is False


def test_registry_rejects_duplicates_and_empty_registry() -> None:
    registry = ThemeRegistry(builtin_themes())
    with pytest.raises(DuplicateThemeError):
        registry.register(registry.get("client"))
    empty = ThemeRegistry()
    assert len(empty) == 0
    assert empty.list() == ()
    with pytest.raises(KeyError):
        empty.default()
