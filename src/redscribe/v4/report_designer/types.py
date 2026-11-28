"""Immutable data contracts for v4 client-ready report layouts.

The report designer is a data-only feature: layouts, themes, sections and
paginated pages are plain dataclasses with strict validation and lossless dict
round-trips. Nothing in this module reads files, executes commands or touches
the network, so payloads can cross the v4 API boundary safely.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

MAX_TEXT_LENGTH = 400
MAX_TITLE_LENGTH = 160
MAX_ENTRIES_PER_SECTION = 250
MAX_SECTIONS = 32
MAX_LINE_WIDTH = 160
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


def clean_text(
    value: object,
    label: str,
    limit: int = MAX_TEXT_LENGTH,
    allow_empty: bool = True,
) -> str:
    """Normalize a wire string, rejecting non-strings and oversized values."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > limit:
        raise ValueError(f"{label} exceeds {limit} characters")
    return normalized


def text_of(value: object) -> str:
    """Return a trimmed string or an empty string for any other value."""
    return value.strip() if isinstance(value, str) else ""


def string_tuple(
    value: object, label: str, limit: int = MAX_ENTRIES_PER_SECTION
) -> tuple[str, ...]:
    """Normalize a sequence of strings with deterministic validation errors."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be a sequence of strings")
    items = tuple(clean_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(items) > limit:
        raise ValueError(f"{label} exceeds {limit} items")
    return items


def int_field(value: object, label: str, minimum: int, maximum: int, default: int) -> int:
    """Validate an optional bounded integer from untyped input."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def float_field(value: object, label: str, minimum: float, maximum: float, default: float) -> float:
    """Validate an optional bounded float from untyped input."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result


def bool_field(value: object, label: str, default: bool = False) -> bool:
    """Validate an optional boolean without accepting integers as booleans."""
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def hex_color(value: object, label: str) -> str:
    """Validate and normalize a six-digit hex color."""
    candidate = clean_text(value, label, 16, allow_empty=False)
    if not HEX_COLOR_PATTERN.match(candidate):
        raise ValueError(f"{label} must be a #RRGGBB color")
    return candidate.lower()


class PageSize(str, Enum):
    """Supported physical page sizes."""

    A4 = "a4"
    LETTER = "letter"
    A5 = "a5"

    @classmethod
    def parse(cls, value: str) -> PageSize:
        normalized = value.strip().casefold()
        for size in cls:
            if size.value == normalized:
                return size
        raise ValueError(f"unknown page size: {value}")

    @property
    def dimensions_mm(self) -> tuple[int, int]:
        return {
            PageSize.A4: (210, 297),
            PageSize.LETTER: (216, 279),
            PageSize.A5: (148, 210),
        }[self]

    @property
    def label(self) -> str:
        return self.value.upper()


class Orientation(str, Enum):
    """Page orientation used by pagination and preview dimensions."""

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"

    @classmethod
    def parse(cls, value: str) -> Orientation:
        normalized = value.strip().casefold()
        for orientation in cls:
            if orientation.value == normalized:
                return orientation
        raise ValueError(f"unknown orientation: {value}")

    @property
    def is_landscape(self) -> bool:
        return self is Orientation.LANDSCAPE

    def apply(self, size: PageSize) -> tuple[int, int]:
        """Return width/height in millimetres after applying orientation."""
        width, height = size.dimensions_mm
        return (height, width) if self.is_landscape else (width, height)


class SectionKind(str, Enum):
    """Canonical sections of a client-ready report."""

    COVER = "cover"
    TOC = "toc"
    FINDINGS = "findings"
    EVIDENCE = "evidence"
    APPENDIX = "appendix"

    @classmethod
    def parse(cls, value: str) -> SectionKind:
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"unknown section kind: {value}")

    @property
    def label(self) -> str:
        return {
            SectionKind.COVER: "Cover",
            SectionKind.TOC: "Table of contents",
            SectionKind.FINDINGS: "Findings",
            SectionKind.EVIDENCE: "Evidence",
            SectionKind.APPENDIX: "Appendix",
        }[self]

    @property
    def order(self) -> int:
        return tuple(SectionKind).index(self)


class ExportFormat(str, Enum):
    """Supported pure-text export targets."""

    HTML = "html"
    MARKDOWN = "markdown"

    @classmethod
    def parse(cls, value: str) -> ExportFormat:
        normalized = value.strip().casefold()
        if normalized in {"md", "markdown"}:
            return cls.MARKDOWN
        for fmt in cls:
            if fmt.value == normalized:
                return fmt
        raise ValueError(f"unknown export format: {value}")

    @property
    def extension(self) -> str:
        return ".html" if self is ExportFormat.HTML else ".md"

    @property
    def mime_type(self) -> str:
        return "text/html" if self is ExportFormat.HTML else "text/markdown"


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """A partial or complete palette; unset fields inherit from a parent."""

    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    text: str | None = None
    background: str | None = None
    muted: str | None = None
    border: str | None = None

    def __post_init__(self) -> None:
        for name, value in self.overrides().items():
            hex_color(value, f"colors.{name}")

    def overrides(self) -> dict[str, str]:
        return {
            name: value
            for name in (
                "primary",
                "secondary",
                "accent",
                "text",
                "background",
                "muted",
                "border",
            )
            if (value := getattr(self, name)) is not None
        }

    def merged(self, parent: ThemeColors) -> ThemeColors:
        values = {**parent.overrides(), **self.overrides()}
        return ThemeColors(**values)

    def to_dict(self) -> dict[str, str]:
        return self.overrides()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ThemeColors:
        return cls(**{key: value for key, value in data.items() if hasattr(cls, key)})


@dataclass(frozen=True, slots=True)
class ThemeFonts:
    """Typography settings; unset fields inherit from a parent theme."""

    heading: str | None = None
    body: str | None = None
    mono: str | None = None
    body_size: float | None = None
    line_height: float | None = None

    def __post_init__(self) -> None:
        for name in ("heading", "body", "mono"):
            value = getattr(self, name)
            if value is not None:
                clean_text(value, f"fonts.{name}", 120, allow_empty=False)
        if self.body_size is not None:
            float_field(self.body_size, "fonts.body_size", 7.0, 24.0, 11.0)
        if self.line_height is not None:
            float_field(self.line_height, "fonts.line_height", 1.0, 2.2, 1.5)

    def overrides(self) -> dict[str, str | float]:
        result: dict[str, str | float] = {}
        for name in ("heading", "body", "mono", "body_size", "line_height"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        return result

    def merged(self, parent: ThemeFonts) -> ThemeFonts:
        values = {**parent.overrides(), **self.overrides()}
        heading = values.get("heading")
        body = values.get("body")
        mono = values.get("mono")
        body_size = values.get("body_size")
        line_height = values.get("line_height")
        return ThemeFonts(
            heading=heading if isinstance(heading, str) else None,
            body=body if isinstance(body, str) else None,
            mono=mono if isinstance(mono, str) else None,
            body_size=float(body_size) if body_size is not None else None,
            line_height=float(line_height) if line_height is not None else None,
        )

    def to_dict(self) -> dict[str, str | float]:
        return self.overrides()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ThemeFonts:
        return cls(**{key: value for key, value in data.items() if hasattr(cls, key)})


@dataclass(frozen=True, slots=True)
class ThemeMargins:
    """Page margins in millimetres; unset fields inherit from a parent."""

    top: int | None = None
    right: int | None = None
    bottom: int | None = None
    left: int | None = None

    def __post_init__(self) -> None:
        for name in ("top", "right", "bottom", "left"):
            value = getattr(self, name)
            if value is not None:
                int_field(value, f"margins.{name}", 0, 60, 18)

    def overrides(self) -> dict[str, int]:
        return {
            name: value
            for name in ("top", "right", "bottom", "left")
            if (value := getattr(self, name)) is not None
        }

    def merged(self, parent: ThemeMargins) -> ThemeMargins:
        return ThemeMargins(**{**parent.overrides(), **self.overrides()})

    def to_dict(self) -> dict[str, int]:
        return self.overrides()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ThemeMargins:
        return cls(**{key: value for key, value in data.items() if hasattr(cls, key)})


@dataclass(frozen=True, slots=True)
class ReportTheme:
    """A named theme with optional parent inheritance."""

    name: str
    parent: str = ""
    colors: ThemeColors = field(default_factory=ThemeColors)
    fonts: ThemeFonts = field(default_factory=ThemeFonts)
    margins: ThemeMargins = field(default_factory=ThemeMargins)
    header: str = ""
    footer: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", clean_text(self.name, "theme name", 64, False))
        object.__setattr__(self, "parent", clean_text(self.parent, "theme parent", 64))
        object.__setattr__(self, "header", clean_text(self.header, "theme header", 120))
        object.__setattr__(self, "footer", clean_text(self.footer, "theme footer", 120))
        object.__setattr__(
            self, "description", clean_text(self.description, "theme description", 200)
        )
        if self.name == self.parent:
            raise ValueError("a theme cannot inherit from itself")

    @property
    def is_root(self) -> bool:
        return not self.parent

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent,
            "colors": self.colors.to_dict(),
            "fonts": self.fonts.to_dict(),
            "margins": self.margins.to_dict(),
            "header": self.header,
            "footer": self.footer,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportTheme:
        raw_colors = data.get("colors", {})
        raw_fonts = data.get("fonts", {})
        raw_margins = data.get("margins", {})
        if not isinstance(raw_colors, Mapping):
            raise ValueError("colors must be an object")
        if not isinstance(raw_fonts, Mapping):
            raise ValueError("fonts must be an object")
        if not isinstance(raw_margins, Mapping):
            raise ValueError("margins must be an object")
        return cls(
            name=clean_text(data.get("name", ""), "theme name", 64, False),
            parent=text_of(data.get("parent")),
            colors=ThemeColors.from_dict(dict(raw_colors)),
            fonts=ThemeFonts.from_dict(dict(raw_fonts)),
            margins=ThemeMargins.from_dict(dict(raw_margins)),
            header=text_of(data.get("header")),
            footer=text_of(data.get("footer")),
            description=text_of(data.get("description")),
        )


@dataclass(frozen=True, slots=True)
class ResolvedTheme:
    """A theme with every inherited value materialized."""

    name: str
    colors: ThemeColors
    fonts: ThemeFonts
    margins: ThemeMargins
    header: str = ""
    footer: str = ""
    lineage: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "colors": self.colors.to_dict(),
            "fonts": self.fonts.to_dict(),
            "margins": self.margins.to_dict(),
            "header": self.header,
            "footer": self.footer,
            "lineage": list(self.lineage),
        }

    def css_variables(self) -> dict[str, str]:
        """Map the palette to CSS custom properties for HTML export."""
        palette = self.colors.overrides()
        return {f"--report-{name}": value for name, value in sorted(palette.items())}

    def page_area_mm(self, size: PageSize, orientation: Orientation) -> tuple[int, int]:
        """Compute the printable area after margins and orientation."""
        width, height = orientation.apply(size)
        margins = self.margins.overrides()
        return (
            width - margins.get("left", 18) - margins.get("right", 18),
            height - margins.get("top", 18) - margins.get("bottom", 18),
        )


@dataclass(frozen=True, slots=True)
class ReportEntry:
    """One line-level item inside a report section."""

    title: str
    detail: str = ""
    level: int = 1
    ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "title", clean_text(self.title, "entry title", MAX_TITLE_LENGTH, False)
        )
        object.__setattr__(self, "detail", clean_text(self.detail, "entry detail"))
        object.__setattr__(self, "ref", clean_text(self.ref, "entry ref", 80))
        object.__setattr__(self, "level", int_field(self.level, "entry level", 1, 4, 1))

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "detail": self.detail, "level": self.level, "ref": self.ref}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportEntry:
        return cls(
            title=clean_text(data.get("title", ""), "entry title", MAX_TITLE_LENGTH, False),
            detail=text_of(data.get("detail")),
            level=int_field(data.get("level"), "entry level", 1, 4, 1),
            ref=text_of(data.get("ref")),
        )


@dataclass(frozen=True, slots=True)
class ReportSection:
    """A titled group of entries, optionally starting on a fresh page."""

    kind: SectionKind
    title: str = ""
    entries: tuple[ReportEntry, ...] = ()
    page_break_before: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "title",
            clean_text(self.title, "section title", MAX_TITLE_LENGTH) or self.kind.label,
        )
        if len(self.entries) > MAX_ENTRIES_PER_SECTION:
            raise ValueError(f"sections support at most {MAX_ENTRIES_PER_SECTION} entries")
        if not all(isinstance(item, ReportEntry) for item in self.entries):
            raise ValueError("entries must contain ReportEntry values")
        if not isinstance(self.page_break_before, bool):
            raise ValueError("page_break_before must be a boolean")

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "title": self.title,
            "entries": [entry.to_dict() for entry in self.entries],
            "page_break_before": self.page_break_before,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportSection:
        raw_entries = data.get("entries", ())
        if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes)):
            raise ValueError("entries must be a sequence")
        entries = tuple(
            ReportEntry.from_dict(item) if isinstance(item, Mapping) else ReportEntry.from_dict({})
            for item in raw_entries
        )
        return cls(
            kind=SectionKind.parse(text_of(data.get("kind"))),
            title=text_of(data.get("title")),
            entries=entries,
            page_break_before=bool_field(data.get("page_break_before"), "page_break_before"),
        )


@dataclass(frozen=True, slots=True)
class ReportLayout:
    """A complete paginated report definition owned by the layout store."""

    id: str
    title: str
    theme: str = "classic"
    page_size: PageSize = PageSize.A4
    orientation: Orientation = Orientation.PORTRAIT
    sections: tuple[ReportSection, ...] = ()
    subtitle: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", clean_text(self.id, "layout id", 80, False))
        if not IDENTIFIER_PATTERN.match(self.id):
            raise ValueError(f"invalid layout id: {self.id}")
        object.__setattr__(
            self, "title", clean_text(self.title, "layout title", MAX_TITLE_LENGTH, False)
        )
        object.__setattr__(self, "theme", clean_text(self.theme, "layout theme", 64, False))
        object.__setattr__(
            self, "subtitle", clean_text(self.subtitle, "layout subtitle", MAX_TITLE_LENGTH)
        )
        object.__setattr__(self, "created_at", clean_text(self.created_at, "created_at", 40))
        if len(self.sections) > MAX_SECTIONS:
            raise ValueError(f"layouts support at most {MAX_SECTIONS} sections")
        if not all(isinstance(section, ReportSection) for section in self.sections):
            raise ValueError("sections must contain ReportSection values")

    @property
    def section_kinds(self) -> tuple[SectionKind, ...]:
        return tuple(section.kind for section in self.sections)

    @property
    def entry_count(self) -> int:
        return sum(section.entry_count for section in self.sections)

    @property
    def page_dimensions_mm(self) -> tuple[int, int]:
        return self.orientation.apply(self.page_size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "theme": self.theme,
            "page_size": self.page_size.value,
            "orientation": self.orientation.value,
            "sections": [section.to_dict() for section in self.sections],
            "subtitle": self.subtitle,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportLayout:
        raw_sections = data.get("sections", ())
        if not isinstance(raw_sections, Sequence) or isinstance(raw_sections, (str, bytes)):
            raise ValueError("sections must be a sequence")
        sections = tuple(
            ReportSection.from_dict(section)
            if isinstance(section, Mapping)
            else ReportSection.from_dict({})
            for section in raw_sections
        )
        return cls(
            id=clean_text(data.get("id", ""), "layout id", 80, False),
            title=clean_text(data.get("title", ""), "layout title", MAX_TITLE_LENGTH, False),
            theme=clean_text(data.get("theme", "classic"), "layout theme", 64, False),
            page_size=PageSize.parse(text_of(data.get("page_size")) or PageSize.A4.value),
            orientation=Orientation.parse(
                text_of(data.get("orientation")) or Orientation.PORTRAIT.value
            ),
            sections=sections,
            subtitle=text_of(data.get("subtitle")),
            created_at=text_of(data.get("created_at")),
        )


@dataclass(frozen=True, slots=True)
class PaginatedPage:
    """One physical page produced by the pagination engine."""

    number: int
    section: SectionKind
    lines: tuple[str, ...]
    title: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", int_field(self.number, "page number", 1, 100000, 1))
        object.__setattr__(self, "title", clean_text(self.title, "page title", MAX_TITLE_LENGTH))
        if len(self.lines) > 500:
            raise ValueError("a page cannot exceed 500 lines")
        if not all(isinstance(line, str) for line in self.lines):
            raise ValueError("page lines must be strings")

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "section": self.section.value,
            "lines": list(self.lines),
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PaginatedPage:
        lines = string_tuple(data.get("lines", ()), "page lines", 500)
        return cls(
            number=int_field(data.get("number"), "page number", 1, 100000, 1),
            section=SectionKind.parse(text_of(data.get("section"))),
            lines=lines,
            title=text_of(data.get("title")),
        )


__all__ = [
    "HEX_COLOR_PATTERN",
    "IDENTIFIER_PATTERN",
    "MAX_ENTRIES_PER_SECTION",
    "MAX_LINE_WIDTH",
    "MAX_SECTIONS",
    "ExportFormat",
    "Orientation",
    "PageSize",
    "PaginatedPage",
    "ReportEntry",
    "ReportLayout",
    "ReportSection",
    "ReportTheme",
    "ResolvedTheme",
    "SectionKind",
    "ThemeColors",
    "ThemeFonts",
    "ThemeMargins",
    "bool_field",
    "clean_text",
    "float_field",
    "hex_color",
    "int_field",
    "string_tuple",
    "text_of",
]
