"""Shared contracts and helpers for report renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape as _html_escape
from typing import Any, Protocol

from redscribe.v3.report_designer.builders import TocEntry
from redscribe.v3.report_designer.identifiers import digest, slugify
from redscribe.v3.report_designer.model import LayoutDocument
from redscribe.v3.report_designer.pagination import PaginationPlan
from redscribe.v3.report_designer.themes import ReportTheme

RenderFormat = str

HTML: RenderFormat = "html"
MARKDOWN: RenderFormat = "markdown"
JSON: RenderFormat = "json"
PRINT: RenderFormat = "print"
RENDER_FORMATS: tuple[RenderFormat, ...] = (HTML, MARKDOWN, JSON, PRINT)

MIME_TYPES: dict[RenderFormat, str] = {
    HTML: "text/html; charset=utf-8",
    MARKDOWN: "text/markdown; charset=utf-8",
    JSON: "application/json; charset=utf-8",
    PRINT: "text/css; charset=utf-8",
}
EXTENSIONS: dict[RenderFormat, str] = {
    HTML: "html",
    MARKDOWN: "md",
    JSON: "json",
    PRINT: "css",
}


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Everything a renderer needs to produce one output."""

    document: LayoutDocument
    theme: ReportTheme
    plan: PaginationPlan
    entries: tuple[TocEntry, ...] = ()
    manifest: dict[str, Any] = field(default_factory=dict)
    options: dict[str, bool] = field(default_factory=dict)

    def option(self, name: str, default: bool = False) -> bool:
        """Read a boolean render option."""
        return bool(self.options.get(name, default))


@dataclass(frozen=True, slots=True)
class RenderOutput:
    """One rendered artifact with reproducibility metadata."""

    format: RenderFormat
    content: str
    mime: str
    filename: str
    content_digest: str = ""

    def __post_init__(self) -> None:
        if not self.content_digest:
            object.__setattr__(self, "content_digest", digest(self.content))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation, omitting the large body by default."""
        return {
            "format": self.format,
            "mime": self.mime,
            "filename": self.filename,
            "bytes": len(self.content.encode("utf-8")),
            "digest": self.content_digest,
        }


class Renderer(Protocol):
    """Interface implemented by every report renderer."""

    @property
    def format(self) -> RenderFormat:
        """Format discriminator."""
        ...

    def render(self, context: RenderContext) -> RenderOutput:
        """Render one output from a context."""
        ...


def html_escape(text: str) -> str:
    """Escape text for safe embedding in HTML."""
    return _html_escape(text, quote=True)


def markdown_escape(text: str) -> str:
    """Escape characters that would alter Markdown structure."""
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*").replace("_", "\\_")


def filename_for(document: LayoutDocument, output_format: RenderFormat) -> str:
    """Build a stable output filename."""
    return (
        f"{slugify(document.title, fallback=document.key)}.{EXTENSIONS.get(output_format, 'txt')}"
    )


def make_output(
    output_format: RenderFormat,
    content: str,
    document: LayoutDocument,
) -> RenderOutput:
    """Assemble a render output with the right mime type and filename."""
    return RenderOutput(
        format=output_format,
        content=content,
        mime=MIME_TYPES.get(output_format, "text/plain; charset=utf-8"),
        filename=filename_for(document, output_format),
    )
