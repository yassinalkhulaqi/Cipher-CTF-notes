"""Backward-compatible imports for the canonical Markdown renderer.

New code should import from :mod:`redscribe.content.markdown`.
"""

from __future__ import annotations

from redscribe.content.markdown import (
    DOCUMENT_CSS,
    Block,
    CodeBlock,
    Heading,
    ListBlock,
    ListItem,
    Paragraph,
    Quote,
    Rule,
    Span,
    SpanKind,
    TableBlock,
    inline_html,
    parse_inline,
    parse_markdown,
    render_html,
    render_markdown_body,
    safe_url,
)

__all__ = [
    "DOCUMENT_CSS",
    "Block",
    "CodeBlock",
    "Heading",
    "ListBlock",
    "ListItem",
    "Paragraph",
    "Quote",
    "Rule",
    "Span",
    "SpanKind",
    "TableBlock",
    "inline_html",
    "parse_inline",
    "parse_markdown",
    "render_html",
    "render_markdown_body",
    "safe_url",
]
