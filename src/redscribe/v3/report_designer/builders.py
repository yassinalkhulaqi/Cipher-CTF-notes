"""Builders for cover pages, tables of contents, and appendices.

Generated sections are ordinary :class:`LayoutSection` objects: they carry
stable keys and anchors and are fed back through the same pagination engine as
authored content. That is what guarantees the printed table of contents points
at the same page the renderer actually places each section on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.report_designer.identifiers import page_label
from redscribe.v3.report_designer.model import LayoutDocument, LayoutSection, SectionKind
from redscribe.v3.report_designer.pagination import PaginationPlan, ordered_sections
from redscribe.v3.report_designer.themes import ReportTheme


@dataclass(frozen=True, slots=True)
class TocEntry:
    """One resolved row in the table of contents."""

    title: str
    anchor: str
    page: int
    level: int
    kind: str

    @property
    def label(self) -> str:
        """Human-readable page label."""
        return f"{self.title}  {self.page}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "title": self.title,
            "anchor": self.anchor,
            "page": self.page,
            "level": self.level,
            "kind": self.kind,
        }


class CoverBuilder:
    """Build the document cover section."""

    def build(self, document: LayoutDocument, theme: ReportTheme) -> LayoutSection:
        """Return a cover section populated from document metadata."""
        lines = [document.title]
        if document.subtitle:
            lines.append(document.subtitle)
        if document.client:
            lines.append(f"Prepared for {document.client}")
        if document.author:
            lines.append(f"Prepared by {document.author}")
        lines.append(f"Classification: {document.classification}")
        if document.generated_at:
            lines.append(f"Generated: {document.generated_at}")
        return LayoutSection(
            key="cover",
            title=document.title,
            kind=SectionKind.COVER,
            level=1,
            order=-100,
            body="\n".join(lines),
            summary=document.subtitle,
            metadata={
                "client": document.client,
                "author": document.author,
                "classification": document.classification,
                "generated_at": document.generated_at,
                "glyph": theme.glyph,
            },
        )


class TocBuilder:
    """Resolve section anchors into a table of contents section."""

    def entries(
        self,
        document: LayoutDocument,
        plan: PaginationPlan,
        *,
        include_kinds: tuple[str, ...] = (),
    ) -> tuple[TocEntry, ...]:
        """Resolve TOC rows from a pagination plan."""
        result: list[TocEntry] = []
        for section in ordered_sections(document.sections):
            if not section.visible:
                continue
            if section.kind in (SectionKind.COVER, SectionKind.TOC):
                continue
            if not section.include_toc:
                continue
            if include_kinds and section.kind.value not in include_kinds:
                continue
            page = plan.page_for_anchor(section.anchor)
            if page is None:
                continue
            result.append(
                TocEntry(
                    title=section.title,
                    anchor=section.anchor,
                    page=page,
                    level=section.level,
                    kind=section.kind.value,
                )
            )
        return tuple(result)

    def build(
        self,
        document: LayoutDocument,
        plan: PaginationPlan,
        theme: ReportTheme,
    ) -> tuple[LayoutSection, tuple[TocEntry, ...]]:
        """Return the TOC section and its resolved rows."""
        entries = self.entries(document, plan)
        body_lines: list[str] = []
        for entry in entries:
            indent = "  " * max(0, entry.level - 1)
            body_lines.append(f"{indent}{entry.title} — {page_label(entry.page, plan.total_pages)}")
        section = LayoutSection(
            key="toc",
            title="Table of Contents",
            kind=SectionKind.TOC,
            level=1,
            order=-99,
            body="\n".join(body_lines),
            summary=f"{len(entries)} sections",
            metadata={
                "leaders": str(theme.tokens.toc_leaders),
                "count": str(len(entries)),
            },
        )
        return section, entries


class AppendixBuilder:
    """Build generated appendix sections from finding and evidence data."""

    def finding_index(self, document: LayoutDocument, *, limit: int = 0) -> LayoutSection:
        """Build a compact index of every finding."""
        findings = tuple(
            sorted(document.all_findings, key=lambda item: (-item.severity_level.rank, item.key))
        )
        if limit > 0:
            findings = findings[:limit]
        lines = [
            f"{index}. [{finding.severity_level.label}] {finding.title} ({finding.status})"
            for index, finding in enumerate(findings, start=1)
        ]
        return LayoutSection(
            key="appendix-finding-index",
            title="Appendix A — Finding Index",
            kind=SectionKind.APPENDIX,
            level=1,
            order=900,
            body="\n".join(lines) or "No findings included.",
            summary=f"{len(findings)} findings",
        )

    def evidence_index(self, document: LayoutDocument) -> LayoutSection:
        """Build a citation index of all attached evidence."""
        evidence = tuple(
            sorted(
                (item for finding in document.all_findings for item in finding.evidence),
                key=lambda item: (item.title.casefold(), str(item.ref)),
            )
        )
        lines = [
            f"{item.citation} [{item.kind}] {'SENSITIVE' if item.sensitive else 'clear'}"
            for item in evidence
        ]
        return LayoutSection(
            key="appendix-evidence-index",
            title="Appendix B — Evidence Index",
            kind=SectionKind.APPENDIX,
            level=1,
            order=901,
            body="\n".join(lines) or "No evidence included.",
            summary=f"{len(evidence)} evidence items",
        )

    def methodology(self, document: LayoutDocument, theme: ReportTheme) -> LayoutSection:
        """Build a short, deterministic methodology note."""
        body = "\n".join(
            [
                "Findings were selected using the report's stable inclusion rules.",
                "Evidence was redacted before render according to the active policy.",
                f"Classification: {document.classification}.",
                f"Page master: {theme.tokens.page_size} {theme.tokens.orientation}.",
            ]
        )
        return LayoutSection(
            key="appendix-methodology",
            title="Appendix C — Methodology",
            kind=SectionKind.APPENDIX,
            level=1,
            order=902,
            body=body,
        )

    def build_all(self, document: LayoutDocument, theme: ReportTheme) -> tuple[LayoutSection, ...]:
        """Return every appendix section in stable order."""
        return (
            self.finding_index(document),
            self.evidence_index(document),
            self.methodology(document, theme),
        )


def build_front_matter(
    document: LayoutDocument, plan: PaginationPlan, theme: ReportTheme
) -> tuple[LayoutSection, LayoutSection, tuple[TocEntry, ...]]:
    """Build cover and TOC sections for a document."""
    cover = CoverBuilder().build(document, theme)
    toc, entries = TocBuilder().build(document, plan, theme)
    return cover, toc, entries


def build_back_matter(document: LayoutDocument, theme: ReportTheme) -> tuple[LayoutSection, ...]:
    """Build all appendix sections for a document."""
    return AppendixBuilder().build_all(document, theme)
