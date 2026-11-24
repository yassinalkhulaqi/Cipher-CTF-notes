"""Tests for cover, table of contents, and appendix builders."""

from __future__ import annotations

from redscribe.v3.report_designer.builders import (
    AppendixBuilder,
    CoverBuilder,
    TocBuilder,
    build_back_matter,
    build_front_matter,
)
from redscribe.v3.report_designer.model import LayoutDocument, LayoutSection, SectionKind
from redscribe.v3.report_designer.pagination import PaginationEngine
from redscribe.v3.report_designer.themes import default_theme_registry


def test_cover_builder(section: LayoutSection) -> None:
    document = LayoutDocument(
        key="doc",
        title="Acme Report",
        subtitle="Confidential",
        client="Acme",
        author="RedScribe",
        classification="internal",
        generated_at="2026-01-01",
        sections=(section,),
    )
    theme = default_theme_registry().default()
    cover = CoverBuilder().build(document, theme)
    assert cover.kind is SectionKind.COVER
    assert cover.key == "cover"
    assert cover.anchor == "sec-cover"
    assert "Acme" in cover.body
    assert cover.metadata["glyph"] == theme.glyph
    assert cover.order < section.order


def test_toc_entries_follow_reading_order(section: LayoutSection, finding) -> None:
    document = LayoutDocument(
        key="doc",
        title="Report",
        sections=(section, LayoutSection(key="z", title="Zeta", order=5)),
    )
    theme = default_theme_registry().default()
    plan = PaginationEngine().paginate(document, theme)
    entries = TocBuilder().entries(document, plan)
    assert tuple(entry.title for entry in entries) == ("Overview", "Scope", "Zeta")
    assert all(entry.page >= 1 for entry in entries)
    assert all(entry.anchor.startswith("sec-") for entry in entries)
    assert entries[0].label.startswith("Overview")
    assert entries[0].as_dict()["page"] == entries[0].page


def test_toc_excludes_hidden_and_opted_out(section: LayoutSection) -> None:
    hidden = LayoutSection(key="hidden", title="Hidden", visible=False)
    no_toc = LayoutSection(key="no-toc", title="No toc", include_toc=False)
    document = LayoutDocument(key="doc", title="Doc", sections=(section, hidden, no_toc))
    theme = default_theme_registry().default()
    plan = PaginationEngine().paginate(document, theme)
    titles = [entry.title for entry in TocBuilder().entries(document, plan)]
    assert "Hidden" not in titles
    assert "No toc" not in titles
    assert "Overview" in titles
    toc, resolved = TocBuilder().build(document, plan, theme)
    assert toc.kind is SectionKind.TOC
    assert len(resolved) == 2
    assert toc.title == "Table of Contents"


def test_appendix_builders(finding) -> None:
    document = LayoutDocument(
        key="doc",
        title="Doc",
        sections=(LayoutSection(key="f", title="Findings", findings=(finding,)),),
    )
    theme = default_theme_registry().default()
    builder = AppendixBuilder()
    finding_index = builder.finding_index(document)
    evidence_index = builder.evidence_index(document)
    methodology = builder.methodology(document, theme)
    assert finding_index.key == "appendix-finding-index"
    assert finding.title in finding_index.body
    assert evidence_index.key == "appendix-evidence-index"
    assert "Auth log" in evidence_index.body
    assert methodology.kind is SectionKind.APPENDIX
    assert "a4 portrait" in methodology.body
    assert len(builder.build_all(document, theme)) == 3
    assert len(build_back_matter(document, theme)) == 3


def test_empty_appendices() -> None:
    document = LayoutDocument(key="doc", title="Doc")
    default_theme_registry().default()
    builder = AppendixBuilder()
    assert "No findings" in builder.finding_index(document, limit=2).body
    assert "No evidence" in builder.evidence_index(document).body


def test_front_matter(section: LayoutSection) -> None:
    document = LayoutDocument(key="doc", title="Doc", sections=(section,))
    theme = default_theme_registry().default()
    plan = PaginationEngine().paginate(document, theme)
    cover, toc, entries = build_front_matter(document, plan, theme)
    assert cover.kind is SectionKind.COVER
    assert toc.kind is SectionKind.TOC
    assert len(entries) == 2
