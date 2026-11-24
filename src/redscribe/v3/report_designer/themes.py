"""Reusable, isolated report themes.

A theme owns only presentation tokens. It never mutates a layout document and
two themes never share token objects, so selecting a theme in the designer has
no effect on any other theme in the registry. The print CSS renderer reads the
same tokens used by the HTML renderer, keeping screen and print output aligned.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from redscribe.v3.report_designer.identifiers import digest

PageSize = Literal["a4", "letter"]
Orientation = Literal["portrait", "landscape"]


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """All presentation values a renderer needs for one theme."""

    ink: str = "#1b2230"
    muted: str = "#5d687b"
    accent: str = "#2f6fed"
    rule: str = "#cbd3e1"
    surface: str = "#ffffff"
    cover_background: str = "#101a34"
    cover_ink: str = "#ffffff"
    body_font: str = "Georgia, 'Times New Roman', serif"
    heading_font: str = "'Helvetica Neue', Arial, sans-serif"
    mono_font: str = "'SFMono-Regular', Consolas, monospace"
    base_size_pt: float = 10.5
    heading_size_pt: float = 20.0
    line_height: float = 1.45
    space_unit_pt: float = 6.0
    border_radius_pt: float = 0.0
    page_size: PageSize = "a4"
    orientation: Orientation = "portrait"
    margin_mm: int = 18
    lines_per_page: int = 48
    chars_per_line: int = 92
    show_header: bool = True
    show_footer: bool = True
    show_watermark: bool = False
    toc_leaders: bool = True

    def __post_init__(self) -> None:
        if self.base_size_pt <= 0 or self.heading_size_pt <= 0:
            raise ValueError("Font sizes must be positive")
        if self.line_height <= 0 or self.space_unit_pt < 0:
            raise ValueError("Line height must be positive and spacing non-negative")
        if self.margin_mm < 0 or self.margin_mm > 60:
            raise ValueError("margin_mm must be between zero and sixty")
        if self.lines_per_page < 8:
            raise ValueError("lines_per_page must be at least eight")
        if self.chars_per_line < 20:
            raise ValueError("chars_per_line must be at least twenty")
        if self.page_size not in ("a4", "letter"):
            raise ValueError(f"Unknown page size: {self.page_size}")
        if self.orientation not in ("portrait", "landscape"):
            raise ValueError(f"Unknown orientation: {self.orientation}")

    @property
    def page_dimensions_mm(self) -> tuple[int, int]:
        """Physical page dimensions in millimetres."""
        base = (210, 297) if self.page_size == "a4" else (216, 279)
        return base if self.orientation == "portrait" else (base[1], base[0])

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ink": self.ink,
            "muted": self.muted,
            "accent": self.accent,
            "rule": self.rule,
            "surface": self.surface,
            "cover_background": self.cover_background,
            "cover_ink": self.cover_ink,
            "body_font": self.body_font,
            "heading_font": self.heading_font,
            "mono_font": self.mono_font,
            "base_size_pt": self.base_size_pt,
            "heading_size_pt": self.heading_size_pt,
            "line_height": self.line_height,
            "space_unit_pt": self.space_unit_pt,
            "border_radius_pt": self.border_radius_pt,
            "page_size": self.page_size,
            "orientation": self.orientation,
            "margin_mm": self.margin_mm,
            "lines_per_page": self.lines_per_page,
            "chars_per_line": self.chars_per_line,
            "show_header": self.show_header,
            "show_footer": self.show_footer,
            "show_watermark": self.show_watermark,
            "toc_leaders": self.toc_leaders,
        }


@dataclass(frozen=True, slots=True)
class ReportTheme:
    """A named, reusable bundle of presentation tokens."""

    key: str
    name: str
    description: str = ""
    tokens: ThemeTokens = field(default_factory=ThemeTokens)
    glyph: str = "◆"
    builtin: bool = True

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Theme key cannot be blank")
        if not self.name.strip():
            raise ValueError("Theme name cannot be blank")

    def with_tokens(self, tokens: ThemeTokens) -> ReportTheme:
        """Return a copy with a different token set."""
        return replace(self, tokens=tokens)

    def digest(self) -> str:
        """Return a digest of the theme's full definition."""
        return digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "tokens": self.tokens.as_dict(),
            "glyph": self.glyph,
            "builtin": self.builtin,
        }


class DuplicateThemeError(ValueError):
    """Raised when a theme key is registered twice."""


class ThemeRegistry:
    """Additive registry of report themes with deterministic ordering."""

    def __init__(self, themes: tuple[ReportTheme, ...] = ()) -> None:
        self._themes: dict[str, ReportTheme] = {}
        for theme in themes:
            self.register(theme)

    def register(self, theme: ReportTheme) -> None:
        """Add a theme, rejecting duplicate keys."""
        if theme.key in self._themes:
            raise DuplicateThemeError(f"Duplicate theme: {theme.key}")
        self._themes[theme.key] = theme

    def get(self, key: str) -> ReportTheme:
        """Return a theme by key, falling back to the default theme."""
        return self._themes.get(key, self.default())

    def has(self, key: str) -> bool:
        """Return whether a theme key is registered."""
        return key in self._themes

    def default(self) -> ReportTheme:
        """Return the default client theme."""
        return self._themes["client"]

    def list(self) -> tuple[ReportTheme, ...]:
        """Return all themes in stable key order."""
        return tuple(self._themes[key] for key in sorted(self._themes))

    def keys(self) -> tuple[str, ...]:
        """Return all theme keys in stable order."""
        return tuple(theme.key for theme in self.list())

    def summaries(self) -> tuple[dict[str, Any], ...]:
        """Return compact descriptors suitable for a theme picker."""
        return tuple(
            {
                "key": theme.key,
                "name": theme.name,
                "description": theme.description,
                "glyph": theme.glyph,
                "page_size": theme.tokens.page_size,
                "orientation": theme.tokens.orientation,
            }
            for theme in self.list()
        )

    def digest(self) -> str:
        """Return a digest of every theme in the registry."""
        return digest([theme.as_dict() for theme in self.list()])

    def __len__(self) -> int:
        """Number of registered themes."""
        return len(self._themes)


def builtin_themes() -> tuple[ReportTheme, ...]:
    """Return the four built-in, visually distinct themes."""
    client = ReportTheme(
        key="client",
        name="Client Ready",
        description="Polished cover, blue accent, and generous reading space.",
        tokens=ThemeTokens(
            accent="#2f6fed",
            cover_background="#101a34",
            body_font="Georgia, 'Times New Roman', serif",
            heading_font="'Helvetica Neue', Arial, sans-serif",
            lines_per_page=44,
        ),
        glyph="◆",
    )
    technical = ReportTheme(
        key="technical",
        name="Technical",
        description="Dense monospace layout for engineering deliverables.",
        tokens=ThemeTokens(
            accent="#0f8f6a",
            rule="#9aa6b8",
            body_font="'SFMono-Regular', Consolas, monospace",
            heading_font="'SFMono-Regular', Consolas, monospace",
            base_size_pt=9.0,
            heading_size_pt=16.0,
            lines_per_page=54,
            chars_per_line=104,
            border_radius_pt=2.0,
        ),
        glyph="⌘",
    )
    executive = ReportTheme(
        key="executive",
        name="Executive",
        description="Large type, minimal ornament, high-level reading.",
        tokens=ThemeTokens(
            accent="#7a3fd1",
            muted="#6b6478",
            rule="#ded7ea",
            cover_background="#241638",
            base_size_pt=12.0,
            heading_size_pt=26.0,
            line_height=1.6,
            lines_per_page=34,
            chars_per_line=76,
            show_watermark=False,
        ),
        glyph="★",
    )
    print_theme = ReportTheme(
        key="print",
        name="Print Safe",
        description="Greyscale, high-contrast layout optimized for paper.",
        tokens=ThemeTokens(
            ink="#000000",
            muted="#333333",
            accent="#000000",
            rule="#777777",
            surface="#ffffff",
            cover_background="#ffffff",
            cover_ink="#000000",
            base_size_pt=10.0,
            lines_per_page=46,
            toc_leaders=True,
        ),
        glyph="▤",
    )
    return (client, technical, executive, print_theme)


def default_theme_registry() -> ThemeRegistry:
    """Return a registry populated with all built-in themes."""
    return ThemeRegistry(builtin_themes())


default_themes = default_theme_registry()
