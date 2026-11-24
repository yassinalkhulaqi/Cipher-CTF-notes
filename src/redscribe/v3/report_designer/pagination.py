"""Deterministic pagination engine for report designs.

Pagination is a pure function of a layout document and a theme. Line estimates
are computed from text length and the theme's character width, sections are
packed into pages in stable reading order, and every section anchor maps to a
page number. The TOC builder and all renderers consume the resulting plan, so
page numbers can never drift between HTML, Markdown, and print preview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

from redscribe.v3.report_designer.identifiers import page_anchor, page_label
from redscribe.v3.report_designer.model import FindingItem, LayoutDocument, LayoutSection
from redscribe.v3.report_designer.themes import ReportTheme

FORCED_PAGE_KINDS = frozenset({"cover", "toc", "appendix"})


def wrapped_lines(text: str, width: int) -> int:
    """Estimate how many rendered lines a block of text occupies."""
    if width < 1:
        raise ValueError("Line width must be positive")
    if not text.strip():
        return 0
    total = 0
    for paragraph in text.splitlines() or [""]:
        total += max(1, ceil(len(paragraph) / width))
    return total


def estimate_finding_lines(finding: FindingItem, width: int) -> int:
    """Estimate the rendered height of one finding."""
    lines = 2
    lines += wrapped_lines(finding.summary, width)
    lines += wrapped_lines(finding.impact, width)
    lines += wrapped_lines(finding.recommendation, width)
    for evidence in finding.evidence:
        lines += 1 + wrapped_lines(evidence.excerpt or evidence.content, width)
    return lines


def estimate_section_lines(section: LayoutSection, width: int) -> int:
    """Estimate the rendered height of a section block, excluding children."""
    lines = 1
    lines += wrapped_lines(section.summary, width)
    lines += wrapped_lines(section.body, width)
    for finding in section.findings:
        lines += estimate_finding_lines(finding, width)
        lines += 1
    return max(1, lines)


def ordered_sections(sections: tuple[LayoutSection, ...]) -> tuple[LayoutSection, ...]:
    """Sort a section tree into deterministic reading order."""
    result: list[LayoutSection] = []
    for section in sorted(sections, key=lambda item: (item.order, item.key)):
        result.append(section)
        if section.children:
            result.extend(ordered_sections(section.children))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class PageItem:
    """One section fragment placed on a page."""

    section_key: str
    title: str
    anchor: str
    kind: str
    lines: int
    offset: int
    continued: bool
    page_index: int
    finding_keys: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "section_key": self.section_key,
            "title": self.title,
            "anchor": self.anchor,
            "kind": self.kind,
            "lines": self.lines,
            "offset": self.offset,
            "continued": self.continued,
            "page_index": self.page_index,
            "finding_keys": list(self.finding_keys),
        }


@dataclass(frozen=True, slots=True)
class Page:
    """One physical page in the generated plan."""

    index: int
    items: tuple[PageItem, ...] = ()
    used_lines: int = 0
    capacity: int = 0
    forced_break: bool = False

    @property
    def anchor(self) -> str:
        """Stable anchor for deep-linking to this page."""
        return page_anchor(self.index)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "index": self.index,
            "anchor": self.anchor,
            "items": [item.as_dict() for item in self.items],
            "used_lines": self.used_lines,
            "capacity": self.capacity,
            "forced_break": self.forced_break,
        }


@dataclass(frozen=True, slots=True)
class PaginationPlan:
    """Complete, reproducible page layout for one document."""

    document_key: str
    theme: str
    pages: tuple[Page, ...]
    anchors: dict[str, int] = field(default_factory=dict)
    finding_pages: dict[str, int] = field(default_factory=dict)
    lines_per_page: int = 0

    @property
    def total_pages(self) -> int:
        """Number of pages in the plan."""
        return len(self.pages)

    def page_for_anchor(self, anchor: str) -> int | None:
        """Return the page containing an anchor, if present."""
        return self.anchors.get(anchor)

    def page_for_finding(self, key: str) -> int | None:
        """Return the page containing a finding, if present."""
        return self.finding_pages.get(key)

    def label_for(self, page_index: int) -> str:
        """Return a human-readable page label."""
        return page_label(page_index, self.total_pages)

    def digest(self) -> str:
        """Return a digest of the entire plan."""
        from redscribe.v3.report_designer.identifiers import digest

        return digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "document_key": self.document_key,
            "theme": self.theme,
            "total_pages": self.total_pages,
            "lines_per_page": self.lines_per_page,
            "pages": [page.as_dict() for page in self.pages],
            "anchors": dict(sorted(self.anchors.items())),
            "finding_pages": dict(sorted(self.finding_pages.items())),
        }


class PaginationEngine:
    """Pack a document's visible sections into deterministic pages."""

    def estimate(self, section: LayoutSection, theme: ReportTheme) -> int:
        """Return the estimated line height of one section."""
        return estimate_section_lines(section, theme.tokens.chars_per_line)

    def paginate(self, document: LayoutDocument, theme: ReportTheme) -> PaginationPlan:
        """Build a page plan for ``document`` under ``theme``."""
        capacity = theme.tokens.lines_per_page
        width = theme.tokens.chars_per_line
        ordered = tuple(
            section for section in ordered_sections(document.sections) if section.visible
        )
        pages: list[Page] = []
        items: list[PageItem] = []
        anchors: dict[str, int] = {}
        finding_pages: dict[str, int] = {}
        used = 0
        page_index = 1
        forced = False

        def flush() -> None:
            nonlocal items, used, page_index, forced
            pages.append(
                Page(
                    index=page_index,
                    items=tuple(items),
                    used_lines=used,
                    capacity=capacity,
                    forced_break=forced,
                )
            )
            page_index += 1
            items = []
            used = 0
            forced = False

        for section in ordered:
            needs_break = section.page_break_before or section.kind.value in FORCED_PAGE_KINDS
            if needs_break and items:
                flush()
            forced = forced or needs_break
            lines = estimate_section_lines(section, width)
            remaining = capacity - used
            chunks: list[tuple[int, int, bool]] = []
            if lines <= remaining:
                chunks.append((lines, 0, False))
            else:
                consumed = 0
                if remaining > 0:
                    chunks.append((remaining, 0, False))
                    consumed = remaining
                while consumed < lines:
                    chunk = min(capacity, lines - consumed)
                    chunks.append((chunk, consumed, True))
                    consumed += chunk
            for chunk_lines, offset, continued in chunks:
                if chunk_lines < 1:
                    continue
                if chunk_lines > capacity - used and items:
                    flush()
                item = PageItem(
                    section_key=section.key,
                    title=section.title,
                    anchor=section.anchor,
                    kind=section.kind.value,
                    lines=chunk_lines,
                    offset=offset,
                    continued=continued,
                    page_index=page_index,
                    finding_keys=tuple(finding.key for finding in section.findings),
                )
                items.append(item)
                used += chunk_lines
                anchors.setdefault(section.anchor, page_index)
                for finding in section.findings:
                    finding_pages.setdefault(finding.key, page_index)

        if items or not pages:
            flush()

        return PaginationPlan(
            document_key=document.key,
            theme=theme.key,
            pages=tuple(pages),
            anchors=anchors,
            finding_pages=finding_pages,
            lines_per_page=capacity,
        )


default_paginator = PaginationEngine()
