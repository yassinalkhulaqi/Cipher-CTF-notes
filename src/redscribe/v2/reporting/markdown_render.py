"""Markdown renderer for assembled reports."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from redscribe.v2.reporting.evidence import evidence_citations
from redscribe.v2.reporting.models import (
    EvidenceRef,
    Finding,
    ReportDocument,
    ReportSection,
    Severity,
)
from redscribe.v2.reporting.severity import severity_table


def escape_cell(value: object) -> str:
    """Escape a value for use inside a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def heading(text: str, level: int = 2) -> str:
    """Render a Markdown heading clamped to levels one through six."""
    return f"{'#' * min(6, max(1, level))} {text.strip()}"


def bullet_lines(values: Iterable[str], *, prefix: str = "- ") -> tuple[str, ...]:
    """Render a compact bullet list."""
    return tuple(f"{prefix}{value}" for value in values if value.strip())


def metadata_table(values: Sequence[tuple[str, object]]) -> str:
    """Render a two-column metadata table, omitting empty values."""
    rows = ["| Field | Value |", "| --- | --- |"]
    for label, value in values:
        if str(value).strip():
            rows.append(f"| {escape_cell(label)} | {escape_cell(value)} |")
    return "\n".join(rows)


def render_evidence_markdown(
    evidence: Sequence[EvidenceRef], *, include_content: bool = True
) -> str:
    """Render an evidence list with optional fenced content."""
    parts: list[str] = []
    for index, item in enumerate(evidence, start=1):
        parts.append(f"{index}. **{item.title}** — {item.citation}")
        if item.excerpt.strip():
            parts.append(f"   > {item.excerpt.strip()}")
        if include_content and item.content.strip():
            language = "bash" if item.kind == "command" else "text"
            parts.append(f"   ```{language}\n   {item.content.strip()}\n   ```")
    return "\n".join(parts)


def render_finding_markdown(
    finding: Finding,
    *,
    level: int = 3,
    include_evidence: bool = True,
) -> str:
    """Render one finding as Markdown."""
    parts = [
        heading(f"{finding.identifier}: {finding.title}", level),
        "",
        f"**Severity:** {Severity.parse(finding.severity).label}  ",
        f"**Status:** {finding.status.title()}  ",
        f"**Confidence:** {finding.confidence:.0%}",
    ]
    if finding.category:
        parts.append(f"**Category:** {finding.category}")
    if finding.cvss:
        parts.append(f"**CVSS:** {finding.cvss}")
    if finding.cwe:
        parts.append(f"**CWE:** {finding.cwe}")
    if finding.affected:
        parts.append(f"**Affected:** {finding.affected}")
    parts.append("")
    if finding.summary:
        parts.extend(("### Summary", finding.summary, ""))
    if finding.impact:
        parts.extend(("### Impact", finding.impact, ""))
    if finding.recommendation:
        parts.extend(("### Recommendation", finding.recommendation, ""))
    if include_evidence and finding.evidence:
        parts.extend(("### Evidence", render_evidence_markdown(finding.evidence), ""))
    if finding.references:
        parts.extend(("### References", *bullet_lines(finding.references), ""))
    return "\n".join(parts).rstrip()


def render_section_markdown(
    section: ReportSection,
    *,
    level: int = 2,
    include_evidence: bool = True,
    include_empty: bool = False,
) -> str:
    """Render a section and its descendants as Markdown."""
    parts = [heading(section.title, min(6, section.level or level))]
    if section.summary:
        parts.extend(("", section.summary))
    if section.body.strip():
        parts.extend(("", section.body.strip()))
    for finding in section.findings:
        parts.extend(("", render_finding_markdown(finding, include_evidence=include_evidence)))
    for child in section.children:
        rendered = render_section_markdown(
            child,
            level=min(6, section.level + 1),
            include_evidence=include_evidence,
            include_empty=include_empty,
        )
        if rendered or include_empty:
            parts.extend(("", rendered))
    if not parts[1:] and not include_empty:
        return ""
    return "\n".join(parts).rstrip()


def render_toc_markdown(document: ReportDocument) -> str:
    """Render a Markdown table of contents."""
    rows = ["## Contents", ""]
    for section in document.all_sections():
        if not section.include_toc:
            continue
        indent = "  " * max(0, min(4, section.level - 1))
        rows.append(f"{indent}- {section.title}")
    return "\n".join(rows)


def render_markdown(document: ReportDocument, *, include_manifest: bool = False) -> str:
    """Render a report as a complete Markdown document."""
    config = document.config
    parts = [
        f"# {document.title}",
        "",
        metadata_table(
            (
                ("Client", config.client),
                ("Author", config.author),
                ("Template", document.template),
                ("Classification", config.classification),
                ("Generated", document.generated_at),
                ("Findings", document.finding_count),
                ("Scope", ", ".join(config.scope)),
            )
        ),
    ]
    if config.introduction.strip():
        parts.extend(("", "## Introduction", "", config.introduction.strip()))
    if config.print_toc:
        parts.extend(("", render_toc_markdown(document)))
    parts.extend(("", "## Severity Summary", "", severity_table(document.severity)))
    for section in document.sections:
        rendered = render_section_markdown(
            section,
            include_evidence=config.include_evidence,
            include_empty=config.include_empty_sections,
        )
        if rendered or config.include_empty_sections:
            parts.extend(("", rendered))
    if document.findings:
        parts.extend(("", "## Finding Register", ""))
        for finding in document.findings:
            rendered = render_finding_markdown(finding, include_evidence=config.include_evidence)
            parts.extend(("", rendered))
    if config.conclusion.strip():
        parts.extend(("", "## Conclusion", "", config.conclusion.strip()))
    if config.include_appendices:
        parts.extend(("", render_appendices(document)))
    if include_manifest:
        parts.extend(("", "## Reproducibility", "", f"Source digest: `{document.source_digest}`"))
    if config.notes.strip():
        parts.extend(("", "## Notes", "", config.notes.strip()))
    return "\n".join(part for part in parts if part is not None).rstrip() + "\n"


def render_appendices(document: ReportDocument) -> str:
    """Render the evidence and severity appendices."""
    parts = ["## Appendices"]
    if document.config.include_evidence:
        all_evidence = [item for finding in document.findings for item in finding.evidence]
        parts.extend(("", "### Evidence Index", ""))
        if all_evidence:
            parts.extend(bullet_lines(evidence_citations(all_evidence)))
        else:
            parts.append("No evidence was included in this report.")
    parts.extend(("", "### Severity Summary", "", severity_table(document.severity)))
    if document.warnings:
        parts.extend(("", "### Build Warnings", "", *bullet_lines(document.warnings)))
    return "\n".join(parts)


def render_finding_index(findings: Sequence[Finding]) -> str:
    """Render a compact finding index table."""
    rows = ["| ID | Finding | Severity | Status |", "| --- | --- | --- | --- |"]
    rows.extend(
        f"| {escape_cell(finding.identifier)} | {escape_cell(finding.title)} | "
        f"{Severity.parse(finding.severity).label} | {finding.status} |"
        for finding in findings
    )
    return "\n".join(rows)
