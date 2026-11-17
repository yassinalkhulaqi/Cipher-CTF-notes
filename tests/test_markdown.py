from __future__ import annotations

from redscribe.content.markdown import (
    DEFAULT_RENDER_OPTIONS,
    CodeBlock,
    DefinitionList,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    RenderOptions,
    Rule,
    TableBlock,
    TocEntry,
    collect_toc,
    parse_inline,
    parse_markdown,
    render_html,
    render_markdown_body,
    render_toc_html,
    safe_url,
)
from redscribe.content.render import render_document


def test_parse_markdown_mixed_blocks() -> None:
    text = """# Title

A paragraph with **bold** text.

## Steps

- first
- second

1. one
2. two

> quoted text

```python
print("hi")
```

| Name | Value |
|:-----|------:|
| a    | 1     |

---
"""
    blocks = parse_markdown(text)
    kinds = [type(block) for block in blocks]
    assert kinds == [
        Heading,
        Paragraph,
        Heading,
        ListBlock,
        ListBlock,
        Quote,
        CodeBlock,
        TableBlock,
        Rule,
    ]
    assert blocks[0] == Heading(1, "Title")
    assert blocks[3].items[1].text == "second"  # type: ignore[union-attr]
    assert blocks[4].items[0].number == 1  # type: ignore[union-attr]
    assert blocks[6].language == "python"  # type: ignore[union-attr]
    assert blocks[7].headers == ["Name", "Value"]  # type: ignore[union-attr]
    assert blocks[7].aligns == ["left", "right"]  # type: ignore[union-attr]


def test_parse_markdown_task_lists_and_setext() -> None:
    blocks = parse_markdown("Title\n=====\n\n- [x] done\n- [ ] todo")
    assert blocks[0] == Heading(1, "Title")
    assert isinstance(blocks[1], ListBlock)
    assert blocks[1].items[0].checked is True
    assert blocks[1].items[1].checked is False
    assert blocks[1].items[0].text == "done"


def test_parse_markdown_handles_crlf_and_bom() -> None:
    blocks = parse_markdown("\ufeff# Title\r\n\r\nBody\r\n")
    assert blocks[0] == Heading(1, "Title")
    assert blocks[1] == Paragraph("Body")


def test_parse_markdown_consumes_unterminated_fence() -> None:
    blocks = parse_markdown("```bash\necho hi\n")
    assert blocks == [CodeBlock("bash", "echo hi\n")]


def test_parse_inline_spans() -> None:
    spans = parse_inline(
        "A **bold** *italic* `code` ~~old~~ [link](https://example.test) https://auto.test."
    )
    kinds = [span.kind for span in spans]
    assert kinds == [
        "text",
        "bold",
        "text",
        "italic",
        "text",
        "code",
        "text",
        "strike",
        "text",
        "link",
        "text",
        "link",
        "text",
    ]
    assert spans[1].text == "bold"
    assert spans[5].text == "code"
    assert spans[9].url == "https://example.test"
    assert spans[11].url == "https://auto.test"
    assert spans[-1].text == "."


def test_parse_inline_handles_escapes_and_underscores() -> None:
    spans = parse_inline(r"\*not italic\* and snake_case_name and _real italic_")
    text = "".join(span.text for span in spans)
    assert "*not italic*" in text
    assert "snake_case_name" in text
    assert any(span.kind == "italic" and span.text == "real italic" for span in spans)


def test_parse_inline_requires_closed_markup() -> None:
    spans = parse_inline("**open and `code")
    assert all(span.kind == "text" for span in spans)


def test_safe_url_allows_only_safe_schemes() -> None:
    assert safe_url("https://example.test") == "https://example.test"
    assert safe_url("http://example.test") == "http://example.test"
    assert safe_url("mailto:test@example.test") == "mailto:test@example.test"
    assert safe_url("#section") == "#section"
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("data:text/html,<script>") is None
    assert safe_url("") is None
    assert safe_url("https://example.test/a b") is None
    assert safe_url("https://example.test/\njavascript:alert(1)") is None
    assert safe_url("https://example.test/?q=one%20two") == "https://example.test/?q=one%20two"


def test_render_markdown_body_escapes_html_and_filters_links() -> None:
    html = render_markdown_body(
        "<script>alert(1)</script> [bad](javascript:alert(1)) [good](https://example.test)"
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "javascript:" not in html
    assert 'href="https://example.test"' in html
    assert 'rel="noreferrer noopener"' in html


def test_render_markdown_body_renders_code_and_tables() -> None:
    html = render_markdown_body("```python\nprint('hello')\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |")
    assert 'class="codeblock"' in html
    assert 'class="code-lang">python' in html
    assert '<span class="tok-builtin">print</span>' in html
    assert "<table>" in html
    assert "<td" in html
    assert ">1</td>" in html


def test_render_html_includes_metadata_and_escapes_title() -> None:
    document = render_html(
        "# Hello\n\nBody",
        "Title <x>",
        subtitle="Sub",
        meta=[("Target", "10.10.10.10"), ("Empty", "")],
    )
    assert document.startswith("<!doctype html>")
    assert "<title>Title &lt;x&gt;</title>" in document
    assert "<h1>Hello</h1>" in document
    assert "10.10.10.10" in document
    assert ">Empty<" not in document
    assert 'class="subtitle">Sub' in document


def test_heading_ids_and_table_of_contents_are_opt_in() -> None:
    text = "# Alpha {#intro}\n\n## Beta\n\n## Beta\n"
    blocks = parse_markdown(text)
    assert render_markdown_body(text) == "<h1>Alpha</h1>\n<h2>Beta</h2>\n<h2>Beta</h2>"

    options = DEFAULT_RENDER_OPTIONS.with_heading_ids("doc-")
    body = render_markdown_body(text, options=options)
    assert '<h1 id="doc-intro">Alpha</h1>' in body
    assert '<h2 id="doc-beta">Beta</h2>' in body
    assert '<h2 id="doc-beta-2">Beta</h2>' in body

    entries = collect_toc(blocks, options=options)
    assert entries == [
        TocEntry(1, "Alpha", "doc-intro"),
        TocEntry(2, "Beta", "doc-beta"),
        TocEntry(2, "Beta", "doc-beta-2"),
    ]
    toc = render_toc_html(entries, options=options)
    assert 'aria-label="Contents"' in toc
    assert 'href="#doc-intro"' in toc
    assert 'href="#doc-beta-2"' in toc


def test_footnotes_render_with_backlinks_and_can_be_disabled() -> None:
    text = "A claim[^one].\n\n[^one]: Evidence with [link](https://example.test)."
    body = render_markdown_body(text)
    assert 'class="footnote-ref"' in body
    assert 'href="#fn-one"' in body
    assert 'id="fn-one"' in body
    assert "Evidence" in body
    assert 'class="footnote-backref"' in body

    plain = render_markdown_body(text, options=RenderOptions(footnotes=False))
    assert "footnote-ref" not in plain
    assert "Evidence" not in plain
    assert "[^one]" in plain


def test_definition_lists_parse_and_render() -> None:
    text = "API\n: Public surface\n: Stable contract\n\nCLI\n: Local command"
    blocks = parse_markdown(text)
    assert [type(block) for block in blocks] == [DefinitionList, DefinitionList]
    assert blocks[0].items[0].term == "API"  # type: ignore[union-attr]

    body = render_markdown_body(text)
    assert '<dl class="definition-list">' in body
    assert "<dt>API</dt>" in body
    assert "<dd>Public surface</dd>" in body
    assert "<dt>CLI</dt>" in body


def test_autolinks_can_be_disabled_without_removing_explicit_links() -> None:
    text = "Visit https://example.test or [docs](https://docs.test)."
    default = render_markdown_body(text)
    assert 'href="https://example.test"' in default
    assert 'href="https://docs.test"' in default

    plain = render_markdown_body(text, options=RenderOptions(autolinks=False))
    assert 'href="https://example.test"' not in plain
    assert "https://example.test" in plain
    assert 'href="https://docs.test"' in plain


def test_render_document_exposes_body_toc_and_full_document() -> None:
    document = render_document("# Alpha\n\n## Beta", title="Doc", toc=True)
    assert document.toc == (TocEntry(1, "Alpha", "alpha"), TocEntry(2, "Beta", "beta"))
    assert '<h1 id="alpha">Alpha</h1>' in document.body_html
    assert 'href="#alpha"' in document.toc_html
    assert document.document_html.startswith("<!doctype html>")
    assert '<nav class="toc"' in document.document_html
    assert "<title>Doc</title>" in document.document_html
