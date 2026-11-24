"""Accessible, deterministic HTML renderer for report designs."""

from __future__ import annotations

from redscribe.v3.report_designer.model import EvidenceItem, FindingItem, LayoutSection
from redscribe.v3.report_designer.renderers.base import (
    HTML,
    RenderContext,
    RenderOutput,
    html_escape,
    make_output,
)


def _lines(text: str, css_class: str = "rd-lines") -> str:
    """Render newline-separated text as escaped lines."""
    if not text.strip():
        return ""
    body = "<br/>".join(html_escape(line) for line in text.splitlines())
    return f'<div class="{css_class}">{body}</div>'


def _finding_html(finding: FindingItem) -> str:
    """Render one finding as a self-contained article."""
    parts = [
        f'<article class="rd-finding" data-finding="{html_escape(finding.key)}" '
        f'data-severity="{finding.severity}">',
        f'<h4 class="rd-finding__title">{html_escape(finding.title)}</h4>',
        f'<p class="rd-finding__meta">{finding.severity_level.label} · '
        f"{html_escape(finding.status)} · {finding.confidence:.2f}</p>",
    ]
    if finding.summary:
        parts.append(_lines(finding.summary, "rd-finding__summary"))
    if finding.impact:
        parts.append('<h5 class="rd-finding__subhead">Impact</h5>')
        parts.append(_lines(finding.impact))
    if finding.recommendation:
        parts.append('<h5 class="rd-finding__subhead">Recommendation</h5>')
        parts.append(_lines(finding.recommendation))
    for evidence in finding.evidence:
        parts.append(_evidence_html(evidence))
    parts.append("</article>")
    return "\n".join(parts)


def _evidence_html(evidence: EvidenceItem) -> str:
    """Render one evidence citation."""
    sensitive = ' data-sensitive="true"' if evidence.sensitive else ""
    return (
        f'<blockquote class="rd-evidence" data-kind="{evidence.kind}"{sensitive}>\n'
        f'<cite class="rd-evidence__cite">{html_escape(evidence.citation)}</cite>\n'
        f"{_lines(evidence.excerpt or evidence.content, 'rd-evidence__body')}\n"
        "</blockquote>"
    )


def _section_html(section: LayoutSection) -> str:
    """Render a section and its descendants."""
    heading_level = min(6, max(2, section.level + 1))
    parts = [
        f'<section class="rd-section" data-kind="{section.kind.value}" '
        f'data-section="{html_escape(section.key)}" id="{html_escape(section.anchor)}">',
        f'<h{heading_level} class="rd-section__title">'
        f"{html_escape(section.title)}</h{heading_level}>",
    ]
    if section.summary:
        parts.append(f'<p class="rd-section__summary">{html_escape(section.summary)}</p>')
    parts.append(_lines(section.body))
    for finding in section.findings:
        parts.append(_finding_html(finding))
    for child in section.children:
        parts.append(_section_html(child))
    parts.append("</section>")
    return "\n".join(parts)


class HtmlRenderer:
    """Render a complete standalone HTML document."""

    @property
    def format(self) -> str:
        """Format discriminator."""
        return HTML

    def render(self, context: RenderContext) -> RenderOutput:
        """Render the report to a UTF-8 HTML string."""
        document = context.document
        theme = context.theme
        parts = [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8"/>',
            '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
            f"<title>{html_escape(document.title)}</title>",
            f'<meta name="classification" content="{html_escape(document.classification)}"/>',
            '<link rel="stylesheet" href="report.css"/>',
            "</head>",
            f'<body class="rd-body" data-theme="{html_escape(theme.key)}">',
            '<main class="rd-report">',
        ]
        if context.option("cover", True):
            parts.append(
                '<header class="rd-cover" id="cover" data-classification="'
                f'{html_escape(document.classification)}">'
            )
            parts.append(f'<div class="rd-cover__glyph">{html_escape(theme.glyph)}</div>')
            parts.append(f'<h1 class="rd-cover__title">{html_escape(document.title)}</h1>')
            if document.subtitle:
                parts.append(f'<p class="rd-cover__subtitle">{html_escape(document.subtitle)}</p>')
            if document.client:
                parts.append(f'<p class="rd-cover__client">{html_escape(document.client)}</p>')
            parts.append(
                f'<p class="rd-cover__meta">{html_escape(document.author)} · '
                f"{html_escape(document.generated_at)}</p>"
            )
            parts.append("</header>")
        if context.option("toc", True) and context.entries:
            parts.append('<nav class="rd-toc" id="toc" aria-label="Table of contents">')
            parts.append('<h2 class="rd-toc__title">Table of Contents</h2>')
            parts.append('<ol class="rd-toc__list">')
            for entry in context.entries:
                parts.append(
                    f'<li class="rd-toc__item" data-level="{entry.level}">'
                    f'<a href="#{html_escape(entry.anchor)}">{html_escape(entry.title)}</a>'
                    f'<span class="rd-toc__page">{context.plan.label_for(entry.page)}</span>'
                    "</li>"
                )
            parts.append("</ol></nav>")
        for section in document.sections:
            if section.kind.value in ("cover", "toc") or not section.visible:
                continue
            parts.append(_section_html(section))
        counts = document.severity
        parts.append(
            '<footer class="rd-footer">'
            f"<span>{html_escape(document.classification)}</span>"
            f"<span>{counts.total()} findings</span>"
            "</footer>"
        )
        parts.append("</main></body></html>")
        return make_output(HTML, "\n".join(parts), document)
