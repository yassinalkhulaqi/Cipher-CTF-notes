"""HTML, Markdown, JSON, and print CSS renderers for report designs."""

from __future__ import annotations

from redscribe.v3.report_designer.renderers.base import (
    EXTENSIONS,
    HTML,
    JSON,
    MARKDOWN,
    MIME_TYPES,
    PRINT,
    RENDER_FORMATS,
    RenderContext,
    Renderer,
    RenderFormat,
    RenderOutput,
    filename_for,
    html_escape,
    make_output,
    markdown_escape,
)
from redscribe.v3.report_designer.renderers.html_render import HtmlRenderer
from redscribe.v3.report_designer.renderers.json_render import JsonRenderer
from redscribe.v3.report_designer.renderers.markdown_render import MarkdownRenderer
from redscribe.v3.report_designer.renderers.print_css import PrintCssRenderer
from redscribe.v3.report_designer.renderers.registry import (
    DuplicateRendererError,
    RendererRegistry,
    UnknownFormatError,
    default_registry,
    default_renderers,
)

__all__ = [
    "EXTENSIONS",
    "HTML",
    "JSON",
    "MARKDOWN",
    "MIME_TYPES",
    "PRINT",
    "RENDER_FORMATS",
    "DuplicateRendererError",
    "HtmlRenderer",
    "JsonRenderer",
    "MarkdownRenderer",
    "PrintCssRenderer",
    "RenderContext",
    "RenderFormat",
    "RenderOutput",
    "Renderer",
    "RendererRegistry",
    "UnknownFormatError",
    "default_registry",
    "default_renderers",
    "filename_for",
    "html_escape",
    "make_output",
    "markdown_escape",
]
