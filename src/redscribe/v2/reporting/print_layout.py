"""Print layout profiles and stylesheet generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

PageSize = Literal["a4", "letter", "legal", "a5"]
Orientation = Literal["portrait", "landscape"]


@dataclass(frozen=True, slots=True)
class PrintProfile:
    """A named print layout used by HTML and PDF export pipelines."""

    name: str
    page_size: PageSize
    orientation: Orientation
    margin_top: str = "18mm"
    margin_right: str = "16mm"
    margin_bottom: str = "18mm"
    margin_left: str = "16mm"
    font_size: str = "10.5pt"
    line_height: float = 1.45
    show_cover: bool = True
    show_toc: bool = True
    show_headers: bool = True
    show_page_numbers: bool = True
    heading_color: str = "#111827"
    break_sections: bool = True

    def __post_init__(self) -> None:
        if self.page_size not in ("a4", "letter", "legal", "a5"):
            raise ValueError(f"Unknown page size: {self.page_size}")
        if self.orientation not in ("portrait", "landscape"):
            raise ValueError(f"Unknown orientation: {self.orientation}")
        if not 1.0 <= self.line_height <= 2.5:
            raise ValueError("line_height must be between 1.0 and 2.5")

    @property
    def dimensions(self) -> tuple[str, str]:
        values: dict[PageSize, tuple[str, str]] = {
            "a4": ("210mm", "297mm"),
            "letter": ("8.5in", "11in"),
            "legal": ("8.5in", "14in"),
            "a5": ("148mm", "210mm"),
        }
        width, height = values[self.page_size]
        return (height, width) if self.orientation == "landscape" else (width, height)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "page_size": self.page_size,
            "orientation": self.orientation,
            "dimensions": list(self.dimensions),
            "margin_top": self.margin_top,
            "margin_right": self.margin_right,
            "margin_bottom": self.margin_bottom,
            "margin_left": self.margin_left,
            "font_size": self.font_size,
            "line_height": self.line_height,
            "show_cover": self.show_cover,
            "show_toc": self.show_toc,
            "show_headers": self.show_headers,
            "show_page_numbers": self.show_page_numbers,
            "heading_color": self.heading_color,
            "break_sections": self.break_sections,
        }


STANDARD = PrintProfile("standard", "a4", "portrait")
TECHNICAL = PrintProfile(
    "technical",
    "a4",
    "portrait",
    font_size="9.5pt",
    line_height=1.35,
    break_sections=False,
)
COMPACT = PrintProfile(
    "compact",
    "a4",
    "portrait",
    margin_top="14mm",
    margin_bottom="14mm",
    font_size="9pt",
    show_cover=False,
    break_sections=False,
)
LANDSCAPE = PrintProfile("landscape", "a4", "landscape", margin_left="12mm", margin_right="12mm")
LETTER = PrintProfile("letter", "letter", "portrait")

PROFILES: dict[str, PrintProfile] = {
    profile.name: profile for profile in (STANDARD, TECHNICAL, COMPACT, LANDSCAPE, LETTER)
}


def get_profile(name: str) -> PrintProfile:
    """Return a print profile by name."""
    normalized = name.strip().casefold()
    profile = PROFILES.get(normalized)
    if profile is None:
        raise ValueError(f"Unknown print profile: {name}")
    return profile


def get_print_profile(name: str) -> PrintProfile:
    """Alias used by renderers."""
    return get_profile(name)


def profile_names() -> tuple[str, ...]:
    """Return all print profile names."""
    return tuple(sorted(PROFILES))


def override_profile(
    profile: PrintProfile,
    *,
    page_size: str | None = None,
    orientation: str | None = None,
    show_cover: bool | None = None,
    show_toc: bool | None = None,
) -> PrintProfile:
    """Return a profile with selected overrides applied."""
    changes: dict[str, Any] = {}
    if page_size is not None:
        if page_size not in ("a4", "letter", "legal", "a5"):
            raise ValueError(f"Unknown page size: {page_size}")
        changes["page_size"] = page_size
    if orientation is not None:
        if orientation not in ("portrait", "landscape"):
            raise ValueError(f"Unknown orientation: {orientation}")
        changes["orientation"] = orientation
    if show_cover is not None:
        changes["show_cover"] = show_cover
    if show_toc is not None:
        changes["show_toc"] = show_toc
    return replace(profile, **changes)


def build_print_css(profile: PrintProfile) -> str:
    """Build the print stylesheet for one profile."""
    width, height = profile.dimensions
    rules = [
        "@page {",
        f"  size: {width} {height};",
        "  margin: "
        f"{profile.margin_top} {profile.margin_right} "
        f"{profile.margin_bottom} {profile.margin_left};",
        "}",
        "@media print {",
        "  html, body { background: #fff; color: #000; }",
        f"  body {{ font-size: {profile.font_size}; line-height: {profile.line_height}; }}",
        f"  h1, h2, h3, h4 {{ color: {profile.heading_color}; }}",
        "  .report-page { max-width: none; margin: 0; padding: 0; }",
    ]
    if profile.show_headers:
        rules.append("  .report-header { break-after: page; }")
    elif profile.show_cover:
        rules.append("  .report-header { break-after: avoid; }")
    if profile.show_toc:
        rules.append("  .report-toc { break-after: page; }")
    if not profile.show_headers:
        rules.append("  .report-header, .report-footer { display: none; }")
    if not profile.show_page_numbers:
        rules.append("  @page { @bottom-center { content: none; } }")
    if profile.break_sections:
        rules.append("  .report-section > h2 { break-before: page; }")
        rules.append("  .report-section:first-of-type > h2 { break-before: auto; }")
    rules.extend(
        (
            "  .finding, .evidence-item, table, pre, blockquote { break-inside: avoid; }",
            "  a { color: inherit; text-decoration: none; }",
            "  .page-break { break-before: page; }",
            "}",
        )
    )
    return "\n".join(rules)


def build_screen_css(profile: PrintProfile) -> str:
    """Build a light screen companion stylesheet for preview panes."""
    return "\n".join(
        (
            ".print-preview { max-width: 900px; margin: 0 auto; padding: 32px; }",
            f".print-preview .paper {{ min-height: {profile.dimensions[1]}; background: #fff; }}",
            ".print-preview .paper { box-shadow: 0 8px 30px rgba(15, 23, 42, .12); }",
            ".print-preview .paper + .paper { margin-top: 24px; }",
        )
    )


def profile_digest(profile: PrintProfile) -> str:
    """Return a stable digest of a print profile."""
    from redscribe.v2.reporting.identifiers import digest

    return digest(profile.as_dict())


def profile_summary() -> tuple[dict[str, object], ...]:
    """Return print profiles as JSON-ready summaries."""
    return tuple(PROFILES[name].as_dict() for name in profile_names())


def paper_label(profile: PrintProfile) -> str:
    """Return a human-readable paper label."""
    width, height = profile.dimensions
    return f"{profile.page_size.upper()} {profile.orientation} · {width} × {height}"
