"""Tests for theme resolution, pagination, assembly and exporters."""

from __future__ import annotations

import pytest

from redscribe.v4.report_designer.service import (
    BASE_THEME,
    BUILTIN_THEMES,
    HtmlExporter,
    MarkdownExporter,
    PaginationConfig,
    PaginationEngine,
    PaginationError,
    RenderedReport,
    ReportBuilder,
    ReportEvidence,
    ReportFinding,
    ReportRenderer,
    ReportSource,
    ThemeError,
    ThemeResolver,
    escape_html,
    section_lines,
    wrap_line,
)
from redscribe.v4.report_designer.types import (
    ExportFormat,
    Orientation,
    PageSize,
    ReportEntry,
    ReportLayout,
    ReportSection,
    ReportTheme,
    SectionKind,
    ThemeColors,
    ThemeMargins,
)


def sample_layout(lines_per_section: int = 4) -> ReportLayout:
    entries = tuple(
        ReportEntry(title=f"Item {index}", detail=f"Detail {index}", ref=f"E-{index}")
        for index in range(lines_per_section)
    )
    return ReportLayout(
        id="sample.layout",
        title="Sample report",
        sections=(
            ReportSection(kind=SectionKind.COVER, title="Cover", entries=entries[:1]),
            ReportSection(
                kind=SectionKind.FINDINGS,
                title="Findings",
                entries=entries,
                page_break_before=True,
            ),
            ReportSection(
                kind=SectionKind.EVIDENCE,
                title="Evidence",
                entries=entries[:2],
                page_break_before=True,
            ),
        ),
    )


def test_builtin_themes_are_well_formed() -> None:
    names = [theme.name for theme in BUILTIN_THEMES]
    assert "base" in names
    assert "client" in names
    assert BASE_THEME.is_root is True
    assert all(theme.name == theme.name.strip() for theme in BUILTIN_THEMES)


def test_theme_resolver_merges_parent_values() -> None:
    resolver = ThemeResolver()
    modern = resolver.resolve("modern")
    assert modern.name == "modern"
    assert modern.lineage == ("base", "classic", "modern")
    assert modern.colors.text == "#23211d"
    assert modern.colors.primary == "#2f5d8a"
    assert modern.fonts.heading == "Helvetica Neue, sans-serif"
    assert modern.fonts.body_size == 11.0
    assert modern.margins.left == 18
    assert modern.header == "CONFIDENTIAL — CLIENT REPORT"


def test_theme_resolver_inherits_through_compact() -> None:
    resolver = ThemeResolver()
    client = resolver.resolve("client")
    assert client.lineage == ("base", "compact", "client")
    assert client.margins.top == 12
    assert client.fonts.body_size == 9.5
    assert client.colors.primary == "#1f5c4a"
    assert client.header == "CLIENT DELIVERABLE"
    assert client.footer == ""


def test_theme_resolver_registration_and_cache() -> None:
    resolver = ThemeResolver()
    custom = ReportTheme(
        name="custom",
        parent="ink",
        colors=ThemeColors(primary="#abcdef"),
        margins=ThemeMargins(top=8),
    )
    resolver.register(custom)
    assert "custom" in resolver.names()
    first = resolver.resolve("custom")
    assert first is resolver.resolve("custom")
    assert first.colors.text == "#101216"
    assert first.colors.primary == "#abcdef"
    assert first.margins.top == 8
    resolver.clear_cache()
    assert resolver.resolve("custom") is not first
    assert resolver.theme("custom") == custom


def test_theme_resolver_cycle_and_unknown_theme() -> None:
    resolver = ThemeResolver(
        themes=(
            ReportTheme(name="loop-a", parent="loop-b"),
            ReportTheme(name="loop-b", parent="loop-a"),
        )
    )
    with pytest.raises(ThemeError, match="cycle detected"):
        resolver.resolve("loop-a")
    with pytest.raises(ThemeError, match="unknown theme"):
        resolver.resolve("missing")
    with pytest.raises(ThemeError, match="unknown theme"):
        resolver.theme("missing")


def test_theme_resolver_describe_is_sorted_and_complete() -> None:
    described = ThemeResolver().describe()
    assert [item["name"] for item in described] == sorted(item["name"] for item in described)
    assert all("lineage" in item and "parent" in item for item in described)
    assert described[0]["lineage"] == ("base",)


def test_resolved_theme_css_and_printable_area() -> None:
    theme = ThemeResolver().resolve("client")
    variables = theme.css_variables()
    assert variables["--report-primary"] == "#1f5c4a"
    assert variables["--report-background"] == "#ffffff"
    area = theme.page_area_mm(PageSize.A4, Orientation.PORTRAIT)
    assert area == (210 - 14 - 14, 297 - 12 - 12)
    assert theme.to_dict()["name"] == "client"


def test_pagination_config_validation() -> None:
    assert PaginationConfig().to_dict() == {
        "lines_per_page": 32,
        "line_width": 78,
        "section_gap": 1,
    }
    with pytest.raises(PaginationError, match="lines_per_page must be between"):
        PaginationConfig(lines_per_page=2)
    with pytest.raises(PaginationError, match="line_width must be between"):
        PaginationConfig(line_width=12)
    with pytest.raises(PaginationError, match="section_gap must be between"):
        PaginationConfig(section_gap=9)


def test_wrap_line_respects_width_and_long_words() -> None:
    assert wrap_line("alpha beta", 10, "> ") == ("> alpha", "> beta")
    assert wrap_line("supercalifragilistic", 7) == ("superca", "lifragi", "listic")
    assert wrap_line("one two three", 12) == ("one two", "three")
    with pytest.raises(PaginationError, match="width must be >= 1"):
        wrap_line("x", 0)


def test_section_lines_include_heading_entries_and_levels() -> None:
    section = ReportSection(
        kind=SectionKind.FINDINGS,
        title="Findings",
        entries=(
            ReportEntry(title="SQL injection", detail="Login form", level=1, ref="F-1"),
            ReportEntry(title="Nested", level=2),
        ),
    )
    lines = section_lines(section, PaginationConfig(line_width=40, section_gap=1))
    assert lines[0] == "FINDINGS"
    assert lines[1] == "-" * 8
    assert lines[2] == ""
    assert lines[3].startswith("- [F-1] SQL injection")
    assert "Login form" in lines[4]
    assert lines[5].startswith("  - Nested")


def test_pagination_engine_splits_at_fixed_boundary() -> None:
    config = PaginationConfig(lines_per_page=5, line_width=60, section_gap=0)
    engine = PaginationEngine(config)
    layout = sample_layout(lines_per_section=6)
    pages = engine.paginate(layout)
    assert len(pages) >= 3
    assert [page.number for page in pages] == list(range(1, len(pages) + 1))
    assert all(page.line_count <= 5 for page in pages)
    assert pages == engine.paginate(layout)
    assert engine.estimate_pages(layout) == len(pages)


def test_pagination_engine_honors_explicit_page_breaks() -> None:
    engine = PaginationEngine(PaginationConfig(lines_per_page=20, line_width=60, section_gap=0))
    layout = sample_layout(lines_per_section=2)
    pages = engine.paginate(layout)
    assert [page.section for page in pages] == [
        SectionKind.COVER,
        SectionKind.FINDINGS,
        SectionKind.EVIDENCE,
    ]
    assert [page.title for page in pages] == ["Cover", "Findings", "Evidence"]
    assert engine.pages_by_section(pages) == {
        "cover": 1,
        "toc": 0,
        "findings": 1,
        "evidence": 1,
        "appendix": 0,
    }


def test_pagination_engine_empty_layout_yields_one_page() -> None:
    layout = ReportLayout(id="empty.layout", title="Empty")
    pages = PaginationEngine().paginate(layout)
    assert len(pages) == 1
    assert pages[0].title == "Empty report"
    assert pages[0].lines == ()


def test_report_source_validation_and_round_trip() -> None:
    source = ReportSource(
        title="Assessment",
        subtitle="Final",
        findings=(ReportFinding(ref="F-1", title="SQLi", severity="High", detail="Login"),),
        evidence=(ReportEvidence(ref="E-1", label="Screenshot", source="shot.png"),),
        appendix=("Scope notes",),
        metadata=(("client", "Acme"),),
    )
    assert ReportSource.from_dict(source.to_dict()) == source
    assert source.findings[0].severity == "high"
    with pytest.raises(ValueError, match="unknown severity"):
        ReportFinding(ref="F-2", title="Bad", severity="catastrophic")
    with pytest.raises(ValueError, match="finding title must not be empty"):
        ReportFinding(ref="F-2", title="")
    with pytest.raises(ValueError, match="evidence label must not be empty"):
        ReportEvidence(ref="E-2", label="")
    with pytest.raises(ValueError, match="report title must not be empty"):
        ReportSource(title="   ")
    with pytest.raises(ValueError, match="findings and evidence must be sequences"):
        ReportSource.from_dict({"title": "x", "findings": 3})


def test_report_builder_uses_canonical_section_order() -> None:
    source = ReportSource(
        title="Assessment",
        findings=(ReportFinding(ref="F-1", title="SQLi", detail="Login"),),
        evidence=(ReportEvidence(ref="E-1", label="Screenshot"),),
        appendix=("Scope", "Method"),
        metadata=(("client", "Acme"),),
    )
    builder = ReportBuilder()
    layout = builder.build(source, layout_id="built.layout", created_at="2026-01-01T00:00:00Z")
    assert layout.section_kinds == (
        SectionKind.COVER,
        SectionKind.TOC,
        SectionKind.FINDINGS,
        SectionKind.EVIDENCE,
        SectionKind.APPENDIX,
    )
    assert [section.page_break_before for section in layout.sections] == [
        True,
        False,
        True,
        True,
        True,
    ]
    assert "Acme" in layout.sections[0].entries[1].detail
    assert [entry.ref for entry in layout.sections[1].entries] == [
        "toc",
        "findings",
        "evidence",
        "appendix",
    ]
    assert layout.sections[2].entries[0].title == "SQLi"
    assert layout.sections[3].entries[0].ref == "E-1"
    assert layout.sections[4].entries[1].detail == "Method"
    assert layout.created_at == "2026-01-01T00:00:00Z"


def test_report_builder_helpers_are_pure() -> None:
    assert ReportBuilder.appendix_entries(["first", "second"])[1].title == "Note 02"
    assert ReportBuilder.cover_entries(ReportSource(title="T"))[0].title == "T"
    assert ReportBuilder.toc_entries(()) == ()
    assert ReportBuilder.finding_entries(()) == ()
    assert (
        ReportBuilder.evidence_entries((ReportEvidence(ref="E", label="L", source="a.png"),))[
            0
        ].detail
        == "a.png"
    )


def test_report_builder_and_pagination_integration() -> None:
    source = ReportSource(
        title="Integration",
        findings=tuple(
            ReportFinding(ref=f"F-{index}", title=f"Finding {index}") for index in range(8)
        ),
    )
    builder = ReportBuilder(PaginationConfig(lines_per_page=6, line_width=50, section_gap=0))
    layout, pages = builder.build_and_paginate(source, layout_id="integration.layout")
    assert layout.title == "Integration"
    assert len(pages) > 1
    assert sum(page.line_count for page in pages) >= 6


def test_escape_html_covers_all_significant_characters() -> None:
    assert escape_html("<a href=\"x\">&'y'</a>") == (
        "&lt;a href=&quot;x&quot;&gt;&amp;&#39;y&#39;&lt;/a&gt;"
    )


def test_html_exporter_renders_theme_and_pages() -> None:
    resolver = ThemeResolver()
    engine = PaginationEngine(PaginationConfig(lines_per_page=6, line_width=50, section_gap=0))
    layout = sample_layout()
    pages = engine.paginate(layout)
    html = HtmlExporter(resolver.resolve("client")).export(layout, pages)
    assert html.startswith("<!doctype html>")
    assert "<title>Sample report</title>" in html
    assert "--report-primary:#1f5c4a;" in html
    assert 'data-section="evidence"' in html
    assert 'class="report-masthead"' in html
    assert "CLIENT DELIVERABLE" in html
    assert f"Page {len(pages)} of {len(pages)}" in html
    assert "&lt;" not in html


def test_markdown_exporter_renders_metadata_and_page_markers() -> None:
    layout = sample_layout()
    pages = PaginationEngine(PaginationConfig(lines_per_page=8, section_gap=0)).paginate(layout)
    markdown = MarkdownExporter().export(layout, pages)
    assert markdown.startswith("# Sample report")
    assert "- Theme: classic" in markdown
    assert "- Page size: A4" in markdown
    assert "## Findings" in markdown
    assert "*Page 1 of" in markdown
    assert markdown.count("\n---\n") == len(pages)
    assert "- Theme:" not in MarkdownExporter(include_metadata=False).export(layout, pages)


def test_renderer_is_deterministic_and_selects_format() -> None:
    renderer = ReportRenderer()
    layout = sample_layout()
    html = renderer.render(layout, ExportFormat.HTML)
    markdown = renderer.render(layout, ExportFormat.MARKDOWN)
    assert isinstance(html, RenderedReport)
    assert html.format is ExportFormat.HTML
    assert html.extension == ".html"
    assert html.mime_type == "text/html"
    assert html.page_count == markdown.page_count
    assert html.checksum != markdown.checksum
    assert renderer.render(layout, ExportFormat.HTML) == html
    assert html.preview == html.text[:240]
    assert html.to_dict()["checksum"] == html.checksum
    assert len(renderer.render_both(layout)) == 2
