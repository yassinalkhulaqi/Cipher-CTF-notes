"""Document-level rendering helpers built on the Markdown renderer."""

from __future__ import annotations

from dataclasses import dataclass

from redscribe.content.markdown import (
    DEFAULT_RENDER_OPTIONS,
    RenderOptions,
    TocEntry,
    collect_toc,
    parse_markdown,
    render_blocks,
    render_html,
    render_toc_html,
)


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    body_html: str
    toc_html: str
    toc: tuple[TocEntry, ...]
    document_html: str


def render_document(
    text: str,
    *,
    title: str,
    subtitle: str = "",
    meta: list[tuple[str, str]] | None = None,
    toc: bool = False,
    toc_title: str = "Contents",
    options: RenderOptions | None = None,
) -> RenderedDocument:
    opts = options or DEFAULT_RENDER_OPTIONS
    if toc:
        opts = opts.with_heading_ids()
    blocks = parse_markdown(text)
    body_html = render_blocks(blocks, options=opts)
    entries = collect_toc(blocks, options=opts) if toc else []
    toc_html = render_toc_html(entries, title=toc_title, options=opts) if entries else ""
    document_html = render_html(
        text,
        title,
        subtitle=subtitle,
        meta=meta,
        options=opts,
        toc=toc,
        toc_title=toc_title,
    )
    return RenderedDocument(body_html, toc_html, tuple(entries), document_html)


def render_standalone_html(
    text: str,
    *,
    title: str,
    subtitle: str = "",
    meta: list[tuple[str, str]] | None = None,
    toc: bool = False,
    toc_title: str = "Contents",
    options: RenderOptions | None = None,
) -> str:
    return render_document(
        text,
        title=title,
        subtitle=subtitle,
        meta=meta,
        toc=toc,
        toc_title=toc_title,
        options=options,
    ).document_html
