"""Domain services for report themes, pagination, assembly and export.

All operations are deterministic and dependency-free. Themes are resolved
through a checked inheritance chain, sections are paginated into fixed-size
pages, and exporters render pure strings: no templates, files or network.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from redscribe.v4.report_designer.types import (
    ExportFormat,
    Orientation,
    PageSize,
    PaginatedPage,
    ReportEntry,
    ReportLayout,
    ReportSection,
    ReportTheme,
    ResolvedTheme,
    SectionKind,
    ThemeColors,
    ThemeFonts,
    ThemeMargins,
    clean_text,
    text_of,
)


class ThemeError(ValueError):
    """Raised for unknown themes, cycles or invalid inheritance chains."""


class PaginationError(ValueError):
    """Raised when pagination limits cannot be satisfied."""


BASE_THEME = ReportTheme(
    name="base",
    colors=ThemeColors(
        primary="#b4532a",
        secondary="#3a6ea5",
        accent="#a87b1e",
        text="#23211d",
        background="#ffffff",
        muted="#6d685e",
        border="#ddd7cb",
    ),
    fonts=ThemeFonts(
        heading="Georgia, serif",
        body="Inter, system-ui, sans-serif",
        mono="ui-monospace, monospace",
        body_size=11.0,
        line_height=1.5,
    ),
    margins=ThemeMargins(top=18, right=18, bottom=18, left=18),
)

BUILTIN_THEMES: tuple[ReportTheme, ...] = (
    BASE_THEME,
    ReportTheme(
        name="classic",
        parent="base",
        colors=ThemeColors(primary="#8c3f22"),
        header="CONFIDENTIAL — CLIENT REPORT",
        footer="Prepared with RedScribe",
        description="Warm, editorial layout for standard engagements.",
    ),
    ReportTheme(
        name="modern",
        parent="classic",
        colors=ThemeColors(primary="#2f5d8a", accent="#3f7d52", muted="#566274"),
        fonts=ThemeFonts(heading="Helvetica Neue, sans-serif", body="Inter, sans-serif"),
        description="Cool-toned layout for executive delivery.",
    ),
    ReportTheme(
        name="compact",
        parent="base",
        margins=ThemeMargins(top=12, right=14, bottom=12, left=14),
        fonts=ThemeFonts(body_size=9.5, line_height=1.35),
        description="Dense layout for long technical appendices.",
    ),
    ReportTheme(
        name="ink",
        parent="modern",
        colors=ThemeColors(
            primary="#111318",
            text="#101216",
            background="#fbfbf8",
            border="#b6b9bb",
        ),
        description="High-contrast monochrome print theme.",
    ),
    ReportTheme(
        name="client",
        parent="compact",
        colors=ThemeColors(primary="#1f5c4a", secondary="#7a4a86"),
        header="CLIENT DELIVERABLE",
        description="Branded variant of the compact theme.",
    ),
)


class ThemeResolver:
    """Resolve theme inheritance into fully materialized values."""

    def __init__(
        self,
        themes: Iterable[ReportTheme] = (),
        defaults: ReportTheme = BASE_THEME,
    ) -> None:
        self.defaults = defaults
        self._themes: dict[str, ReportTheme] = {}
        self._cache: dict[str, ResolvedTheme] = {}
        self.register(defaults)
        for theme in BUILTIN_THEMES:
            self.register(theme)
        for theme in themes:
            self.register(theme)

    def register(self, theme: ReportTheme) -> ReportTheme:
        """Add or replace a theme and invalidate cached resolutions."""
        self._themes[theme.name] = theme
        self._cache.clear()
        return theme

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._themes))

    def theme(self, name: str) -> ReportTheme:
        normalized = name.strip().casefold()
        theme = self._themes.get(normalized)
        if theme is None:
            raise ThemeError(f"unknown theme: {name}")
        return theme

    def chain(self, name: str) -> tuple[str, ...]:
        """Return root-to-leaf names in the inheritance chain of ``name``."""
        chain: list[str] = []
        seen: set[str] = set()
        current = name.strip().casefold()
        while current:
            if current in seen:
                raise ThemeError(f"theme cycle detected at {current}")
            seen.add(current)
            theme = self._themes.get(current)
            if theme is None:
                raise ThemeError(f"unknown theme parent: {current}")
            chain.append(current)
            current = theme.parent.casefold()
        chain.reverse()
        return tuple(chain)

    def resolve(self, name: str) -> ResolvedTheme:
        """Merge a theme with its ancestors and the built-in defaults."""
        normalized = name.strip().casefold() or self.defaults.name
        cached = self._cache.get(normalized)
        if cached is not None:
            return cached
        lineage = self.chain(normalized)
        colors = self.defaults.colors
        fonts = self.defaults.fonts
        margins = self.defaults.margins
        header = self.defaults.header
        footer = self.defaults.footer
        for entry in lineage:
            theme = self._themes[entry]
            colors = theme.colors.merged(colors)
            fonts = theme.fonts.merged(fonts)
            margins = theme.margins.merged(margins)
            header = theme.header or header
            footer = theme.footer or footer
        resolved = ResolvedTheme(
            name=normalized,
            colors=colors,
            fonts=fonts,
            margins=margins,
            header=header,
            footer=footer,
            lineage=lineage,
        )
        self._cache[normalized] = resolved
        return resolved

    def describe(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "name": theme.name,
                "parent": theme.parent,
                "lineage": self.chain(theme.name),
                "description": theme.description,
            }
            for theme in sorted(self._themes.values(), key=lambda item: item.name)
        )

    def clear_cache(self) -> None:
        self._cache.clear()


@dataclass(frozen=True, slots=True)
class PaginationConfig:
    """Fixed geometry used by the pagination engine."""

    lines_per_page: int = 32
    line_width: int = 78
    section_gap: int = 1

    def __post_init__(self) -> None:
        if not 4 <= self.lines_per_page <= 200:
            raise PaginationError("lines_per_page must be between 4 and 200")
        if not 20 <= self.line_width <= 160:
            raise PaginationError("line_width must be between 20 and 160")
        if not 0 <= self.section_gap <= 4:
            raise PaginationError("section_gap must be between 0 and 4")

    def to_dict(self) -> dict[str, int]:
        return {
            "lines_per_page": self.lines_per_page,
            "line_width": self.line_width,
            "section_gap": self.section_gap,
        }


@dataclass(slots=True)
class _PageBuffer:
    """Mutable accumulator converted to an immutable page on flush."""

    number: int
    section: SectionKind
    title: str
    lines: list[str] = field(default_factory=list)

    def freeze(self) -> PaginatedPage:
        return PaginatedPage(
            number=self.number,
            section=self.section,
            lines=tuple(self.lines),
            title=self.title,
        )


def wrap_line(text: str, width: int, prefix: str = "") -> tuple[str, ...]:
    """Wrap text into lines of at most ``width`` characters, prefix included."""
    if width < 1:
        raise PaginationError("width must be >= 1")
    available = max(1, width - len(prefix))
    words = text.split() or [""]
    chunks: list[str] = []
    current = ""
    for word in words:
        while len(word) > available:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:available])
            word = word[available:]
        candidate = f"{current} {word}".strip()
        if len(candidate) <= available:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return tuple(f"{prefix}{chunk}" for chunk in chunks) or (prefix,)


def section_lines(section: ReportSection, config: PaginationConfig) -> tuple[str, ...]:
    """Render a section into wrapped, page-ready text lines."""
    heading = section.title.upper()
    lines: list[str] = [heading[: config.line_width], "-" * min(len(heading), config.line_width)]
    for index, entry in enumerate(section.entries):
        if index == 0 and config.section_gap:
            lines.extend([""] * config.section_gap)
        prefix = "  " * (entry.level - 1) + "- "
        label = f"[{entry.ref}] {entry.title}" if entry.ref else entry.title
        lines.extend(wrap_line(label, config.line_width, prefix))
        if entry.detail:
            detail_prefix = "  " * (entry.level - 1) + "    "
            lines.extend(wrap_line(entry.detail, config.line_width, detail_prefix))
    return tuple(lines)


class PaginationEngine:
    """Split report sections into deterministic, fixed-size pages."""

    def __init__(self, config: PaginationConfig | None = None) -> None:
        self.config = config or PaginationConfig()

    def paginate_sections(self, sections: Sequence[ReportSection]) -> tuple[PaginatedPage, ...]:
        pages: list[PaginatedPage] = []
        buffer = _PageBuffer(number=1, section=SectionKind.COVER, title="")

        def flush() -> None:
            if buffer.lines:
                pages.append(buffer.freeze())
                buffer.number += 1
            buffer.lines.clear()
            buffer.section = SectionKind.COVER
            buffer.title = ""

        for section in sections:
            if section.page_break_before and buffer.lines:
                flush()
            lines = section_lines(section, self.config)
            for line in lines:
                if len(buffer.lines) >= self.config.lines_per_page:
                    flush()
                if not buffer.lines:
                    buffer.section = section.kind
                    buffer.title = section.title
                buffer.lines.append(line)
        flush()
        if not pages:
            pages.append(
                PaginatedPage(number=1, section=SectionKind.COVER, lines=(), title="Empty report")
            )
        return tuple(pages)

    def paginate(self, layout: ReportLayout) -> tuple[PaginatedPage, ...]:
        """Paginate a complete layout, preserving section order."""
        return self.paginate_sections(layout.sections)

    def estimate_pages(self, layout: ReportLayout) -> int:
        return len(self.paginate(layout))

    def pages_by_section(self, pages: Sequence[PaginatedPage]) -> dict[str, int]:
        """Count pages attributable to each section kind."""
        counts = {kind.value: 0 for kind in SectionKind}
        for page in pages:
            counts[page.section.value] += 1
        return counts


@dataclass(frozen=True, slots=True)
class ReportFinding:
    """A single finding supplied to the report builder."""

    ref: str
    title: str
    severity: str = "medium"
    detail: str = ""
    evidence: tuple[str, ...] = ()

    SEVERITIES = ("critical", "high", "medium", "low", "informational")

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", clean_text(self.ref, "finding ref", 40, False))
        object.__setattr__(self, "title", clean_text(self.title, "finding title", 160, False))
        object.__setattr__(self, "detail", clean_text(self.detail, "finding detail"))
        normalized = clean_text(self.severity, "finding severity", 20, False).casefold()
        if normalized not in self.SEVERITIES:
            raise ValueError(f"unknown severity: {self.severity}")
        object.__setattr__(self, "severity", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "title": self.title,
            "severity": self.severity,
            "detail": self.detail,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportFinding:
        return cls(
            ref=clean_text(data.get("ref", ""), "finding ref", 40, False),
            title=clean_text(data.get("title", ""), "finding title", 160, False),
            severity=text_of(data.get("severity")) or "medium",
            detail=text_of(data.get("detail")),
            evidence=tuple(str(item) for item in data.get("evidence", ())),
        )


@dataclass(frozen=True, slots=True)
class ReportEvidence:
    """A single evidence artifact referenced by findings."""

    ref: str
    label: str
    source: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", clean_text(self.ref, "evidence ref", 40, False))
        object.__setattr__(self, "label", clean_text(self.label, "evidence label", 160, False))
        object.__setattr__(self, "source", clean_text(self.source, "evidence source", 200))
        object.__setattr__(self, "summary", clean_text(self.summary, "evidence summary"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "label": self.label,
            "source": self.source,
            "summary": self.summary,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportEvidence:
        return cls(
            ref=clean_text(data.get("ref", ""), "evidence ref", 40, False),
            label=clean_text(data.get("label", ""), "evidence label", 160, False),
            source=text_of(data.get("source")),
            summary=text_of(data.get("summary")),
            tags=tuple(str(item) for item in data.get("tags", ())),
        )


@dataclass(frozen=True, slots=True)
class ReportSource:
    """Raw engagement data assembled into a report layout."""

    title: str
    subtitle: str = ""
    findings: tuple[ReportFinding, ...] = ()
    evidence: tuple[ReportEvidence, ...] = ()
    appendix: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", clean_text(self.title, "report title", 160, False))
        object.__setattr__(self, "subtitle", clean_text(self.subtitle, "report subtitle", 160))
        if len(self.findings) > 250 or len(self.evidence) > 250 or len(self.appendix) > 250:
            raise ValueError("report sources support at most 250 items per category")
        if len(self.metadata) > 40:
            raise ValueError("report sources support at most 40 metadata pairs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence": [item.to_dict() for item in self.evidence],
            "appendix": list(self.appendix),
            "metadata": [list(pair) for pair in self.metadata],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportSource:
        raw_findings = data.get("findings", ())
        raw_evidence = data.get("evidence", ())
        raw_metadata = data.get("metadata", ())
        if not isinstance(raw_findings, Sequence) or not isinstance(raw_evidence, Sequence):
            raise ValueError("findings and evidence must be sequences")
        if not isinstance(raw_metadata, Sequence):
            raise ValueError("metadata must be a sequence")
        findings = tuple(
            ReportFinding.from_dict(item)
            if isinstance(item, Mapping)
            else ReportFinding.from_dict({})
            for item in raw_findings
        )
        evidence = tuple(
            ReportEvidence.from_dict(item)
            if isinstance(item, Mapping)
            else ReportEvidence.from_dict({})
            for item in raw_evidence
        )
        metadata = tuple(
            (
                clean_text(str(pair[0]), "metadata key", 80),
                clean_text(str(pair[1]), "metadata value", 200),
            )
            for pair in raw_metadata
            if isinstance(pair, Sequence) and len(pair) == 2
        )
        return cls(
            title=clean_text(data.get("title", ""), "report title", 160, False),
            subtitle=text_of(data.get("subtitle")),
            findings=findings,
            evidence=evidence,
            appendix=tuple(str(item) for item in data.get("appendix", ())),
            metadata=metadata,
        )


class ReportBuilder:
    """Assemble canonical sections from engagement data."""

    def __init__(self, config: PaginationConfig | None = None) -> None:
        self.config = config or PaginationConfig()

    @staticmethod
    def cover_entries(source: ReportSource) -> tuple[ReportEntry, ...]:
        entries = [ReportEntry(title=source.title, detail=source.subtitle, level=1)]
        for key, value in source.metadata:
            entries.append(ReportEntry(title=key, detail=value, level=2))
        return tuple(entries)

    @staticmethod
    def toc_entries(sections: Sequence[ReportSection]) -> tuple[ReportEntry, ...]:
        entries: list[ReportEntry] = []
        for section in sections:
            if section.kind is SectionKind.COVER:
                continue
            entries.append(
                ReportEntry(
                    title=section.title, detail=section.kind.label, level=1, ref=section.kind.value
                )
            )
        return tuple(entries)

    @staticmethod
    def finding_entries(findings: Sequence[ReportFinding]) -> tuple[ReportEntry, ...]:
        return tuple(
            ReportEntry(
                title=finding.title,
                detail=finding.detail,
                level=1,
                ref=f"{finding.ref}:{finding.severity}",
            )
            for finding in findings
        )

    @staticmethod
    def evidence_entries(items: Sequence[ReportEvidence]) -> tuple[ReportEntry, ...]:
        return tuple(
            ReportEntry(
                title=item.label,
                detail=item.summary or item.source,
                level=1,
                ref=item.ref,
            )
            for item in items
        )

    @staticmethod
    def appendix_entries(notes: Sequence[str]) -> tuple[ReportEntry, ...]:
        return tuple(
            ReportEntry(title=f"Note {index:02d}", detail=note, level=1)
            for index, note in enumerate(notes, start=1)
        )

    def build(
        self,
        source: ReportSource,
        layout_id: str = "report-generated",
        theme: str = "classic",
        page_size: PageSize = PageSize.A4,
        orientation: Orientation = Orientation.PORTRAIT,
        created_at: str = "",
    ) -> ReportLayout:
        """Build a layout with the canonical section order."""
        cover = ReportSection(
            kind=SectionKind.COVER,
            title="Cover",
            entries=self.cover_entries(source),
            page_break_before=True,
        )
        toc = ReportSection(
            kind=SectionKind.TOC,
            title="Table of contents",
            entries=(),
            page_break_before=False,
        )
        sections = [
            cover,
            toc,
            ReportSection(
                kind=SectionKind.FINDINGS,
                title="Findings",
                entries=self.finding_entries(source.findings),
                page_break_before=True,
            ),
            ReportSection(
                kind=SectionKind.EVIDENCE,
                title="Evidence",
                entries=self.evidence_entries(source.evidence),
                page_break_before=True,
            ),
            ReportSection(
                kind=SectionKind.APPENDIX,
                title="Appendix",
                entries=self.appendix_entries(source.appendix),
                page_break_before=True,
            ),
        ]
        sections[1] = replace(toc, entries=self.toc_entries(sections))
        return ReportLayout(
            id=layout_id,
            title=source.title,
            subtitle=source.subtitle,
            theme=theme,
            page_size=page_size,
            orientation=orientation,
            sections=tuple(sections),
            created_at=created_at,
        )

    def build_and_paginate(
        self, source: ReportSource, layout_id: str = "report-generated", theme: str = "classic"
    ) -> tuple[ReportLayout, tuple[PaginatedPage, ...]]:
        layout = self.build(source, layout_id=layout_id, theme=theme)
        return layout, PaginationEngine(self.config).paginate(layout)


def escape_html(value: str) -> str:
    """Escape the five markup-significant ASCII characters."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


class HtmlExporter:
    """Render layouts and pages to a self-contained HTML document."""

    def __init__(self, theme: ResolvedTheme | None = None, show_page_numbers: bool = True) -> None:
        self.theme = theme
        self.show_page_numbers = show_page_numbers

    def export(self, layout: ReportLayout, pages: Sequence[PaginatedPage]) -> str:
        variables = self.theme.css_variables() if self.theme is not None else {}
        style = "".join(f"{name}:{value};" for name, value in sorted(variables.items()))
        parts = [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>{escape_html(layout.title)}</title>",
            f"<style>:root{{{style}}}</style>",
            "</head>",
            "<body>",
            f'<header class="report-masthead"><h1>{escape_html(layout.title)}</h1>',
            f"<p>{escape_html(layout.subtitle)}</p></header>",
        ]
        if self.theme is not None and self.theme.header:
            parts.append(f'<div class="report-header">{escape_html(self.theme.header)}</div>')
        for page in pages:
            parts.append(
                f'<section class="report-page" data-section="{page.section.value}" '
                f'data-page="{page.number}">'
            )
            if page.title:
                parts.append(f"<h2>{escape_html(page.title)}</h2>")
            for line in page.lines:
                if line:
                    parts.append(f"<p>{escape_html(line)}</p>")
                else:
                    parts.append('<p class="report-gap">&nbsp;</p>')
            if self.show_page_numbers:
                parts.append(f"<footer>Page {page.number} of {len(pages)}</footer>")
            parts.append("</section>")
        if self.theme is not None and self.theme.footer:
            parts.append(f'<div class="report-footer">{escape_html(self.theme.footer)}</div>')
        parts.extend(["</body>", "</html>", ""])
        return "\n".join(parts)


class MarkdownExporter:
    """Render layouts and pages to portable Markdown."""

    def __init__(self, include_metadata: bool = True) -> None:
        self.include_metadata = include_metadata

    def export(self, layout: ReportLayout, pages: Sequence[PaginatedPage]) -> str:
        parts = [f"# {layout.title}", ""]
        if layout.subtitle:
            parts.extend([f"> {layout.subtitle}", ""])
        if self.include_metadata:
            parts.extend(
                [
                    f"- Theme: {layout.theme}",
                    f"- Page size: {layout.page_size.label}",
                    f"- Orientation: {layout.orientation.value}",
                    f"- Pages: {len(pages)}",
                    "",
                ]
            )
        for page in pages:
            parts.append(f"## {page.title or page.section.label}")
            parts.append("")
            parts.extend(page.lines)
            parts.extend(["", f"*Page {page.number} of {len(pages)}*", "", "---", ""])
        return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class RenderedReport:
    """The immutable result of rendering a layout to one export format."""

    layout_id: str
    format: ExportFormat
    text: str
    pages: tuple[PaginatedPage, ...]
    checksum: str

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def extension(self) -> str:
        return self.format.extension

    @property
    def mime_type(self) -> str:
        return self.format.mime_type

    @property
    def preview(self) -> str:
        return self.text[:240]

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_id": self.layout_id,
            "format": self.format.value,
            "extension": self.format.extension,
            "mime_type": self.format.mime_type,
            "page_count": self.page_count,
            "checksum": self.checksum,
            "preview": self.preview,
            "text": self.text,
            "pages": [page.to_dict() for page in self.pages],
        }


class ReportRenderer:
    """Coordinate theme resolution, pagination and export selection."""

    def __init__(
        self,
        resolver: ThemeResolver | None = None,
        engine: PaginationEngine | None = None,
    ) -> None:
        self.resolver = resolver or ThemeResolver()
        self.engine = engine or PaginationEngine()

    def render(self, layout: ReportLayout, fmt: ExportFormat) -> RenderedReport:
        theme = self.resolver.resolve(layout.theme)
        pages = self.engine.paginate(layout)
        if fmt is ExportFormat.HTML:
            text = HtmlExporter(theme).export(layout, pages)
        else:
            text = MarkdownExporter().export(layout, pages)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return RenderedReport(
            layout_id=layout.id,
            format=fmt,
            text=text,
            pages=pages,
            checksum=checksum,
        )

    def render_both(self, layout: ReportLayout) -> tuple[RenderedReport, RenderedReport]:
        return (
            self.render(layout, ExportFormat.HTML),
            self.render(layout, ExportFormat.MARKDOWN),
        )


__all__ = [
    "BASE_THEME",
    "BUILTIN_THEMES",
    "HtmlExporter",
    "MarkdownExporter",
    "PaginationConfig",
    "PaginationEngine",
    "PaginationError",
    "RenderedReport",
    "ReportBuilder",
    "ReportEvidence",
    "ReportFinding",
    "ReportRenderer",
    "ReportSource",
    "ThemeError",
    "ThemeResolver",
    "escape_html",
    "section_lines",
    "wrap_line",
]
