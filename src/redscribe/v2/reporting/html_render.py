"""HTML and print-layout renderer for assembled reports."""

from __future__ import annotations

import html
from collections.abc import Iterable, Sequence

from redscribe.v2.reporting.models import (
    EvidenceRef,
    Finding,
    ReportDocument,
    ReportSection,
    Severity,
)
from redscribe.v2.reporting.print_layout import (
    PrintProfile,
    build_print_css,
    get_print_profile,
)


def esc(value: object) -> str:
    """Escape text for safe HTML interpolation."""
    return html.escape(str(value), quote=True)


def render_meta_html(document: ReportDocument) -> str:
    """Render the report metadata strip."""
    config = document.config
    values = (
        ("Client", config.client),
        ("Author", config.author),
        ("Classification", config.classification),
        ("Generated", document.generated_at),
        ("Template", document.template),
    )
    return "".join(
        f'<div class="meta-item"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'
        for label, value in values
        if str(value).strip()
    )


def render_toc_html(document: ReportDocument) -> str:
    """Render a nested table of contents from report sections."""
    rows = ['<nav class="report-toc" aria-label="Report contents">', "<h2>Contents</h2>", "<ol>"]
    for section in document.all_sections():
        if not section.include_toc:
            continue
        rows.append(
            f'<li class="toc-level-{min(6, section.level)}">'
            f'<a href="#section-{esc(section.identifier)}">{esc(section.title)}</a></li>'
        )
    rows.extend(("</ol>", "</nav>"))
    return "\n".join(rows)


def render_severity_html(document: ReportDocument) -> str:
    """Render the severity summary table."""
    values = document.severity.as_dict()
    rows = [
        '<table class="severity-table">',
        "<thead><tr><th>Severity</th><th>Count</th></tr></thead>",
        "<tbody>",
    ]
    for name, count in values.items():
        rows.append(
            f'<tr class="severity-{esc(name)}"><td>{esc(Severity.parse(name).label)}</td>'
            f"<td>{count}</td></tr>"
        )
    rows.extend(("</tbody>", "</table>"))
    return "\n".join(rows)


def render_evidence_html(evidence: Sequence[EvidenceRef], *, include_content: bool = True) -> str:
    """Render an ordered evidence list."""
    if not evidence:
        return '<p class="empty-note">No evidence recorded.</p>'
    rows = ['<ol class="evidence-list">']
    for item in evidence:
        sensitive = ' <span class="badge sensitive">sensitive</span>' if item.sensitive else ""
        rows.append(
            f'<li id="evidence-{esc(item.identifier)}" class="evidence-item">'
            f'<div class="evidence-title">{esc(item.title)}{sensitive}</div>'
            f'<div class="evidence-citation">{esc(item.citation)}</div>'
        )
        if item.excerpt.strip():
            rows.append(f"<blockquote>{esc(item.excerpt)}</blockquote>")
        if include_content and item.content.strip():
            rows.append(f"<pre><code>{esc(item.content)}</code></pre>")
        rows.append("</li>")
    rows.append("</ol>")
    return "\n".join(rows)


def render_finding_html(finding: Finding, *, include_evidence: bool = True) -> str:
    """Render one finding as an article element."""
    article_class = f"finding severity-{esc(finding.severity)}"
    article_id = f"finding-{esc(finding.identifier)}"
    parts = [
        f'<article class="{article_class}" id="{article_id}">',
        "<header>",
        f'<span class="badge severity">{esc(Severity.parse(finding.severity).label)}</span>',
        f'<span class="badge status">{esc(finding.status)}</span>',
        f"<h3>{esc(finding.title)}</h3>",
        f'<div class="finding-id">{esc(finding.identifier)}</div>',
        "</header>",
    ]
    paragraphs = (
        ("Summary", finding.summary),
        ("Impact", finding.impact),
        ("Recommendation", finding.recommendation),
        ("Affected", finding.affected),
    )
    for label, value in paragraphs:
        if value.strip():
            parts.append(
                f'<section class="finding-block"><h4>{esc(label)}</h4><p>{esc(value)}</p></section>'
            )
    details = (
        ("Confidence", f"{finding.confidence:.0%}"),
        ("CVSS", finding.cvss),
        ("CWE", finding.cwe),
        ("Category", finding.category),
    )
    rendered = "".join(
        f'<div class="meta-item"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'
        for label, value in details
        if str(value).strip()
    )
    if rendered:
        parts.append(f'<div class="finding-meta">{rendered}</div>')
    if finding.references:
        parts.append('<section class="finding-block"><h4>References</h4><ul>')
        parts.extend(f"<li>{esc(value)}</li>" for value in finding.references)
        parts.append("</ul></section>")
    if include_evidence and finding.evidence:
        parts.append("<section><h4>Evidence</h4>")
        parts.append(render_evidence_html(finding.evidence))
        parts.append("</section>")
    parts.append("</article>")
    return "\n".join(parts)


def render_section_html(section: ReportSection, *, include_evidence: bool = True) -> str:
    """Render one section and its descendants."""
    classes = ["report-section", f"section-{esc(section.kind)}"]
    if section.page_break_before:
        classes.append("page-break")
    parts = [
        f'<section class="{" ".join(classes)}" id="section-{esc(section.identifier)}">',
        f"<h{min(6, section.level)}>{esc(section.title)}</h{min(6, section.level)}>",
    ]
    if section.summary:
        parts.append(f'<p class="section-summary">{esc(section.summary)}</p>')
    if section.body.strip():
        parts.append(f'<div class="section-body">{esc(section.body)}</div>')
    for finding in section.findings:
        parts.append(render_finding_html(finding, include_evidence=include_evidence))
    for child in section.children:
        parts.append(render_section_html(child, include_evidence=include_evidence))
    parts.append("</section>")
    return "\n".join(parts)


def render_warnings_html(warnings: Iterable[str]) -> str:
    """Render a report warning callout."""
    items = list(warnings)
    if not items:
        return ""
    rows = ['<aside class="report-warnings"><h2>Build warnings</h2><ul>']
    rows.extend(f"<li>{esc(item)}</li>" for item in items)
    rows.append("</ul></aside>")
    return "\n".join(rows)


REPORT_CSS = """
:root {
  color-scheme: light;
  --rs-bg: #ffffff;
  --rs-text: #1b2030;
  --rs-muted: #626c82;
  --rs-border: #d8deeb;
  --rs-accent: #c2185b;
  --rs-surface: #f7f8fb;
  --rs-critical: #991b1b;
  --rs-high: #c2410c;
  --rs-medium: #a16207;
  --rs-low: #1d4ed8;
  --rs-info: #475569;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--rs-bg);
  color: var(--rs-text);
  font: 15px/1.6 "Segoe UI", Inter, Helvetica, Arial, sans-serif;
}
.report-page {
  max-width: 960px; margin: 0 auto; padding: 48px 44px 72px;
}
.report-header {
  border-bottom: 2px solid var(--rs-accent); padding-bottom: 24px;
}
.report-kicker {
  color: var(--rs-accent); font-size: 11px; font-weight: 700;
  letter-spacing: .22em;
}
.report-header h1 {
  font-size: 36px; line-height: 1.15; margin: 10px 0 12px;
}
.report-meta {
  display: flex; flex-wrap: wrap; gap: 12px 28px; margin-top: 18px;
}
.meta-item {
  display: flex; flex-direction: column; gap: 2px; font-size: 12px;
}
.meta-item span {
  color: var(--rs-muted); letter-spacing: .12em; text-transform: uppercase;
}
.meta-item strong { font-size: 13px; font-weight: 600; }
.classification {
  display: inline-block; padding: 3px 9px;
  border: 1px solid var(--rs-accent); border-radius: 99px;
  color: var(--rs-accent); font-size: 11px; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase;
}
.report-toc {
  margin: 32px 0; padding: 18px 22px;
  background: var(--rs-surface); border: 1px solid var(--rs-border);
}
.report-toc h2 {
  margin: 0 0 10px; font-size: 16px;
  letter-spacing: .1em; text-transform: uppercase;
}
.report-toc ol { list-style: none; margin: 0; padding: 0; }
.report-toc li { margin: 4px 0; font-size: 14px; }
.report-toc .toc-level-3 { padding-left: 18px; }
.report-toc .toc-level-4,
.report-toc .toc-level-5,
.report-toc .toc-level-6 { padding-left: 36px; }
.report-toc a { color: var(--rs-text); text-decoration: none; }
.report-section { margin: 34px 0; }
.report-section > h1,
.report-section > h2,
.report-section > h3,
.report-section > h4,
.report-section > h5,
.report-section > h6 { margin-bottom: 10px; }
.section-summary { color: var(--rs-muted); font-size: 16px; }
.section-body { white-space: pre-wrap; }
.finding {
  margin: 24px 0; padding: 18px 20px;
  border: 1px solid var(--rs-border); border-left: 4px solid var(--rs-info);
}
.finding.severity-critical { border-left-color: var(--rs-critical); }
.finding.severity-high { border-left-color: var(--rs-high); }
.finding.severity-medium { border-left-color: var(--rs-medium); }
.finding.severity-low { border-left-color: var(--rs-low); }
.finding header {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
}
.finding h3 { width: 100%; margin: 4px 0; font-size: 20px; }
.finding-id {
  color: var(--rs-muted); font-family: Consolas, monospace;
  font-size: 12px; width: 100%;
}
.finding-block h4,
.finding > section h4 {
  font-size: 13px; letter-spacing: .08em; text-transform: uppercase;
  margin: 16px 0 4px;
}
.badge {
  padding: 2px 7px; border: 1px solid var(--rs-border);
  border-radius: 99px; font-size: 11px; text-transform: uppercase;
}
.badge.severity { color: var(--rs-accent); border-color: var(--rs-accent); }
.badge.sensitive { color: var(--rs-critical); border-color: var(--rs-critical); }
.finding-meta {
  display: flex; flex-wrap: wrap; gap: 10px 24px; margin-top: 14px;
}
.severity-table {
  width: 100%; border-collapse: collapse; margin: 12px 0 28px;
}
.severity-table th,
.severity-table td {
  padding: 7px 10px; border: 1px solid var(--rs-border); text-align: left;
}
.severity-table th { background: var(--rs-surface); }
.severity-table tr.severity-critical td:first-child { color: var(--rs-critical); }
.severity-table tr.severity-high td:first-child { color: var(--rs-high); }
.evidence-list { margin: 8px 0; padding-left: 22px; }
.evidence-item { margin: 10px 0; }
.evidence-title { font-weight: 600; }
.evidence-citation { color: var(--rs-muted); font-size: 12px; }
.evidence-item blockquote {
  margin: 6px 0; padding: 4px 12px;
  border-left: 3px solid var(--rs-border); color: var(--rs-muted);
}
.evidence-item pre {
  padding: 10px; background: var(--rs-surface);
  border: 1px solid var(--rs-border); overflow-x: auto; white-space: pre-wrap;
}
.report-warnings {
  margin: 28px 0; padding: 14px 18px;
  border: 1px solid var(--rs-medium); background: #fffbeb;
}
.page-break { break-before: page; }
.report-footer {
  margin-top: 56px; padding-top: 16px;
  border-top: 1px solid var(--rs-border); color: var(--rs-muted); font-size: 12px;
}
.empty-note { color: var(--rs-muted); font-style: italic; }
"""


def render_html(
    document: ReportDocument,
    *,
    profile: PrintProfile | None = None,
    include_manifest: bool = False,
) -> str:
    """Render a report as a complete standalone HTML document."""
    layout = profile or get_print_profile(document.config.print_profile)
    css = f"{REPORT_CSS}\n{build_print_css(layout)}"
    toc = render_toc_html(document) if document.config.print_toc else ""
    sections = "\n".join(
        render_section_html(section, include_evidence=document.config.include_evidence)
        for section in document.sections
    )
    findings = ""
    if document.findings:
        finding_rows = "\n".join(
            render_finding_html(item, include_evidence=document.config.include_evidence)
            for item in document.findings
        )
        findings = (
            '<section class="report-section" id="finding-register">'
            f"<h2>Finding Register</h2>{finding_rows}</section>"
        )
    manifest = ""
    if include_manifest:
        manifest = (
            '<section class="report-section" id="reproducibility">'
            "<h2>Reproducibility</h2>"
            f"<p>Source digest: <code>{esc(document.source_digest)}</code></p>"
            "</section>"
        )
    warnings = render_warnings_html(document.warnings)
    intro = ""
    if document.config.introduction.strip():
        intro = (
            '<section class="report-section"><h2>Introduction</h2>'
            f"<p>{esc(document.config.introduction)}</p></section>"
        )
    conclusion = ""
    if document.config.conclusion.strip():
        conclusion = (
            '<section class="report-section"><h2>Conclusion</h2>'
            f"<p>{esc(document.config.conclusion)}</p></section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(document.title)}</title>
<style>
{css}
</style>
</head>
<body>
<main class="report-page">
<header class="report-header">
  <div class="report-kicker">REDSCRIBE REPORT</div>
  <h1>{esc(document.title)}</h1>
  <span class="classification">{esc(document.config.classification)}</span>
  <div class="report-meta">{render_meta_html(document)}</div>
</header>
{intro}
{toc}
<section class="report-section"><h2>Severity Summary</h2>{render_severity_html(document)}</section>
{sections}
{findings}
{conclusion}
{manifest}
{warnings}
<footer class="report-footer">
Generated by RedScribe Reporting Studio · local-first and reproducible
</footer>
</main>
</body>
</html>
"""


def render_print_html(document: ReportDocument) -> str:
    """Render an HTML document optimized for a print pipeline."""
    return render_html(document, profile=get_print_profile(document.config.print_profile))
