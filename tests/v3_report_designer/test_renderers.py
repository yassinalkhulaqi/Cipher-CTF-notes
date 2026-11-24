"""Tests for HTML, Markdown, JSON, and print CSS renderers."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from redscribe.v3.report_designer.builders import TocEntry
from redscribe.v3.report_designer.model import LayoutDocument, LayoutSection
from redscribe.v3.report_designer.pagination import PaginationEngine
from redscribe.v3.report_designer.renderers import (
    HTML,
    JSON,
    MARKDOWN,
    PRINT,
    DuplicateRendererError,
    HtmlRenderer,
    JsonRenderer,
    MarkdownRenderer,
    PrintCssRenderer,
    RenderContext,
    RendererRegistry,
    UnknownFormatError,
    default_registry,
    filename_for,
    html_escape,
    make_output,
    markdown_escape,
)
from redscribe.v3.report_designer.themes import default_theme_registry


def make_context(finding) -> RenderContext:
    section = LayoutSection(
        key="overview",
        title="Overview",
        body="Contact security@acme.com and <script>alert(1)</script>.",
        findings=(finding,),
    )
    document = LayoutDocument(key="doc", title="Acme Report", client="Acme", sections=(section,))
    theme = default_theme_registry().default()
    plan = PaginationEngine().paginate(document, theme)
    entries = (TocEntry(title="Overview", anchor="sec-overview", page=1, level=1, kind="text"),)
    return RenderContext(
        document=document,
        theme=theme,
        plan=plan,
        entries=entries,
        manifest={"design_digest": "abc"},
        options={"cover": True, "toc": True},
    )


def test_html_renderer_escapes_and_anchors(finding) -> None:
    output = HtmlRenderer().render(make_context(finding))
    assert output.format == HTML
    assert output.mime.startswith("text/html")
    assert output.filename == "acme-report.html"
    assert "<!doctype html>" in output.content
    assert 'id="sec-overview"' in output.content
    assert "&lt;script&gt;" in output.content
    assert "security@acme.com" in output.content
    assert "Table of Contents" in output.content
    assert "rd-finding" in output.content
    assert "Page 1 of" in output.content
    assert output.content == HtmlRenderer().render(make_context(finding)).content


def test_markdown_renderer(finding) -> None:
    output = MarkdownRenderer().render(make_context(finding))
    assert output.format == MARKDOWN
    assert output.filename == "acme-report.md"
    assert output.content.startswith("# Acme Report")
    assert "[Overview](#sec-overview)" in output.content
    assert "#### Finding:" in output.content
    assert "\\<script>" not in output.content
    assert "---" in output.content


def test_json_renderer_is_canonical(finding) -> None:
    output = JsonRenderer().render(make_context(finding))
    assert output.format == JSON
    assert output.mime.startswith("application/json")
    parsed = json.loads(output.content)
    assert parsed["document"]["title"] == "Acme Report"
    assert parsed["theme"]["key"] == "client"
    assert parsed["pagination"]["total_pages"] >= 1
    assert parsed["toc"][0]["anchor"] == "sec-overview"
    assert parsed["manifest"] == {"design_digest": "abc"}
    assert output.content == JsonRenderer().render(make_context(finding)).content
    assert output.content.index('"document"') < output.content.index('"theme"')


def test_print_css_uses_theme_tokens(finding) -> None:
    context = make_context(finding)
    output = PrintCssRenderer().render(context)
    assert output.format == PRINT
    assert output.filename == "acme-report.css"
    assert "@page" in output.content
    assert "size: 210mm 297mm" in output.content
    assert "margin: 18mm" in output.content
    assert "--rd-accent: #2f6fed" in output.content
    assert "break-after: page" in output.content
    assert "@media print" in output.content
    landscape = replace(
        context.theme,
        tokens=replace(context.theme.tokens, orientation="landscape"),
    )
    landscape_css = PrintCssRenderer().render(replace(context, theme=landscape))
    assert "size: 297mm 210mm" in landscape_css.content


def test_renderer_registry(finding) -> None:
    registry = default_registry()
    assert registry.formats() == (HTML, MARKDOWN, JSON, PRINT)
    assert len(registry.render_all(make_context(finding))) == 4
    assert registry.has(PRINT) is True
    with pytest.raises(DuplicateRendererError):
        registry.register(HtmlRenderer())
    with pytest.raises(UnknownFormatError):
        registry.get("pdf")
    custom = RendererRegistry((MarkdownRenderer(),))
    assert custom.formats() == (MARKDOWN,)
    assert RendererRegistry().formats() == ()


def test_helpers(finding) -> None:
    assert html_escape("<a & b>") == "&lt;a &amp; b&gt;"
    assert markdown_escape("a_b*c") == "a\\_b\\*c"
    assert filename_for(LayoutDocument(key="x", title="###"), HTML) == "x.html"
    output = make_output(JSON, "{}", LayoutDocument(key="x", title="X"))
    assert output.content_digest
    assert len(output.content_digest) == 64
    assert output.as_dict()["bytes"] == 2
