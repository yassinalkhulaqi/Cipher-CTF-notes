from __future__ import annotations

from redscribe.content.markdown import (
    CodeBlock,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    TableBlock,
    parse_inline,
    parse_markdown,
    render_html,
    render_markdown_body,
    safe_url,
)


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
