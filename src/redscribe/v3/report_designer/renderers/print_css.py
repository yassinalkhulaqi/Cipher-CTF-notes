"""Print CSS renderer derived from report theme tokens."""

from __future__ import annotations

from redscribe.v3.report_designer.renderers.base import (
    PRINT,
    RenderContext,
    RenderOutput,
    make_output,
)


class PrintCssRenderer:
    """Render a stylesheet that matches the HTML structure byte-for-byte."""

    @property
    def format(self) -> str:
        """Format discriminator."""
        return PRINT

    def render(self, context: RenderContext) -> RenderOutput:
        """Render print CSS for the current theme."""
        tokens = context.theme.tokens
        width_mm, height_mm = tokens.page_dimensions_mm
        rules = [
            "@page {",
            f"  size: {width_mm}mm {height_mm}mm;",
            f"  margin: {tokens.margin_mm}mm;",
            "}",
            "",
            ":root {",
            f"  --rd-ink: {tokens.ink};",
            f"  --rd-muted: {tokens.muted};",
            f"  --rd-accent: {tokens.accent};",
            f"  --rd-rule: {tokens.rule};",
            f"  --rd-surface: {tokens.surface};",
            f"  --rd-cover-bg: {tokens.cover_background};",
            f"  --rd-cover-ink: {tokens.cover_ink};",
            f"  --rd-body-font: {tokens.body_font};",
            f"  --rd-heading-font: {tokens.heading_font};",
            f"  --rd-mono-font: {tokens.mono_font};",
            f"  --rd-space: {tokens.space_unit_pt}pt;",
            f"  --rd-radius: {tokens.border_radius_pt}pt;",
            "}",
            "",
            "html { background: var(--rd-rule); }",
            "body.rd-body {",
            "  margin: 0 auto;",
            "  background: var(--rd-surface);",
            "  color: var(--rd-ink);",
            "  font-family: var(--rd-body-font);",
            f"  font-size: {tokens.base_size_pt}pt;",
            f"  line-height: {tokens.line_height};",
            f"  max-width: {width_mm - 2 * tokens.margin_mm}mm;",
            "  padding: 0;",
            "}",
            ".rd-report { padding: 0; }",
            ".rd-lines { margin: 0 0 calc(var(--rd-space) * 1.5) 0; }",
            "h1, h2, h3, h4, h5 { font-family: var(--rd-heading-font); color: var(--rd-ink); }",
            f"h2.rd-section__title {{ font-size: {tokens.heading_size_pt}pt; }}",
            ".rd-cover {",
            "  background: var(--rd-cover-bg);",
            "  color: var(--rd-cover-ink);",
            "  padding: 24pt;",
            "  border-radius: var(--rd-radius);",
            "  break-after: page;",
            "  page-break-after: always;",
            "}",
            ".rd-cover h1, .rd-cover p { color: var(--rd-cover-ink); }",
            ".rd-cover__glyph { font-size: 28pt; opacity: 0.7; }",
            ".rd-toc { break-after: page; page-break-after: always; }",
            ".rd-toc__list { list-style: none; padding: 0; margin: 0; }",
            ".rd-toc__item { display: flex; justify-content: space-between; gap: 8pt; }",
            ".rd-toc__item a { color: inherit; text-decoration: none; }",
            ".rd-toc__page { color: var(--rd-muted); font-variant-numeric: tabular-nums; }",
            ".rd-section { break-inside: auto; margin-bottom: calc(var(--rd-space) * 3); }",
            ".rd-finding {",
            "  border-left: 3pt solid var(--rd-accent);",
            "  padding: var(--rd-space) calc(var(--rd-space) * 2);",
            "  margin: 0 0 calc(var(--rd-space) * 2) 0;",
            "  break-inside: avoid;",
            "}",
            ".rd-finding__meta { color: var(--rd-muted); font-size: 0.85em; }",
            ".rd-finding__subhead { margin-bottom: 0; }",
            ".rd-evidence {",
            "  border: 1pt solid var(--rd-rule);",
            "  border-radius: var(--rd-radius);",
            "  padding: var(--rd-space);",
            "  margin: var(--rd-space) 0;",
            "  font-family: var(--rd-mono-font);",
            "  font-size: 0.9em;",
            "}",
            ".rd-evidence__cite { color: var(--rd-muted); font-weight: bold; }",
            ".rd-footer {",
            "  border-top: 1pt solid var(--rd-rule);",
            "  padding-top: var(--rd-space);",
            "  display: flex;",
            "  justify-content: space-between;",
            "  color: var(--rd-muted);",
            "  font-size: 0.8em;",
            "}",
        ]
        if not tokens.toc_leaders:
            rules.append(".rd-toc__page::before { content: ''; }")
        if tokens.show_watermark:
            rules.append(".rd-body::before { content: 'DRAFT'; opacity: 0.06; }")
        if not tokens.show_header:
            rules.append(".rd-report header.rd-cover { border: 0; }")
        if not tokens.show_footer:
            rules.append(".rd-footer { display: none; }")
        rules.extend(
            [
                "",
                "@media print {",
                "  html { background: #ffffff; }",
                "  body.rd-body { max-width: none; }",
                "  a { color: inherit !important; }",
                "}",
            ]
        )
        return make_output(PRINT, "\n".join(rules), context.document)
