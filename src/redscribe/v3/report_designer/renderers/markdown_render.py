"""Deterministic Markdown renderer for report designs."""

from __future__ import annotations

from redscribe.v3.report_designer.model import EvidenceItem, FindingItem, LayoutSection
from redscribe.v3.report_designer.renderers.base import (
    MARKDOWN,
    RenderContext,
    RenderOutput,
    make_output,
    markdown_escape,
)


def _finding_md(finding: FindingItem) -> list[str]:
    """Render one finding as Markdown lines."""
    lines = [
        f"#### Finding: {markdown_escape(finding.title)}",
        "",
        f"- Severity: {finding.severity_level.label}",
        f"- Status: {finding.status}",
        f"- Confidence: {finding.confidence:.2f}",
    ]
    if finding.summary:
        lines.extend(["", markdown_escape(finding.summary)])
    if finding.impact:
        lines.extend(["", "**Impact**", "", markdown_escape(finding.impact)])
    if finding.recommendation:
        lines.extend(["", "**Recommendation**", "", markdown_escape(finding.recommendation)])
    for evidence in finding.evidence:
        lines.extend(_evidence_md(evidence))
    lines.append("")
    return lines


def _evidence_md(evidence: EvidenceItem) -> list[str]:
    """Render one evidence citation as Markdown lines."""
    return [
        "",
        f"> **{markdown_escape(evidence.citation)}** [{evidence.kind}]",
        f"> {markdown_escape(evidence.excerpt or evidence.content)}",
    ]


def _section_md(section: LayoutSection) -> list[str]:
    """Render a section and its descendants as Markdown lines."""
    heading = "#" * min(6, max(2, section.level + 1))
    lines = ["", f"{heading} {markdown_escape(section.title)}", ""]
    if section.summary:
        lines.extend([markdown_escape(section.summary), ""])
    if section.body:
        for line in section.body.splitlines():
            lines.append(markdown_escape(line))
        lines.append("")
    for finding in section.findings:
        lines.extend(_finding_md(finding))
    for child in section.children:
        lines.extend(_section_md(child))
    return lines


class MarkdownRenderer:
    """Render a report to a portable Markdown string."""

    @property
    def format(self) -> str:
        """Format discriminator."""
        return MARKDOWN

    def render(self, context: RenderContext) -> RenderOutput:
        """Render the report to Markdown."""
        document = context.document
        counts = document.severity
        lines = [
            f"# {markdown_escape(document.title)}",
            "",
        ]
        if document.subtitle:
            lines.extend([f"*{markdown_escape(document.subtitle)}*", ""])
        meta = [
            f"- Client: {markdown_escape(document.client)}",
            f"- Author: {markdown_escape(document.author)}",
            f"- Classification: {markdown_escape(document.classification)}",
            f"- Generated: {markdown_escape(document.generated_at)}",
            f"- Findings: {counts.total()}",
        ]
        lines.extend(meta)
        if context.option("toc", True) and context.entries:
            lines.extend(["", "## Table of Contents", ""])
            for entry in context.entries:
                indent = "  " * max(0, entry.level - 1)
                lines.append(
                    f"{indent}- [{markdown_escape(entry.title)}](#{entry.anchor}) "
                    f"— {context.plan.label_for(entry.page)}"
                )
        for section in document.sections:
            if section.kind.value in ("cover", "toc") or not section.visible:
                continue
            lines.extend(_section_md(section))
        lines.extend(
            [
                "",
                "---",
                "",
                f"*{markdown_escape(document.classification)} report · {context.theme.name} theme*",
            ]
        )
        return make_output(MARKDOWN, "\n".join(lines), document)
