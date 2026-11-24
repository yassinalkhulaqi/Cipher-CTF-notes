"""Renderer registry with stable format ordering."""

from __future__ import annotations

from redscribe.v3.report_designer.renderers.base import (
    RENDER_FORMATS,
    RenderContext,
    Renderer,
    RenderFormat,
    RenderOutput,
)
from redscribe.v3.report_designer.renderers.html_render import HtmlRenderer
from redscribe.v3.report_designer.renderers.json_render import JsonRenderer
from redscribe.v3.report_designer.renderers.markdown_render import MarkdownRenderer
from redscribe.v3.report_designer.renderers.print_css import PrintCssRenderer


class DuplicateRendererError(ValueError):
    """Raised when a renderer format is registered twice."""


class UnknownFormatError(KeyError):
    """Raised when a render format is not registered."""


class RendererRegistry:
    """Additive registry of renderers keyed by output format."""

    def __init__(self, renderers: tuple[Renderer, ...] = ()) -> None:
        self._renderers: dict[RenderFormat, Renderer] = {}
        for renderer in renderers:
            self.register(renderer)

    def register(self, renderer: Renderer) -> None:
        """Add a renderer, rejecting duplicate formats."""
        if renderer.format in self._renderers:
            raise DuplicateRendererError(f"Duplicate renderer: {renderer.format}")
        self._renderers[renderer.format] = renderer

    def get(self, output_format: RenderFormat) -> Renderer:
        """Return a renderer by format."""
        try:
            return self._renderers[output_format]
        except KeyError as exc:
            raise UnknownFormatError(f"Unknown format: {output_format}") from exc

    def has(self, output_format: RenderFormat) -> bool:
        """Return whether a format is registered."""
        return output_format in self._renderers

    def render(self, output_format: RenderFormat, context: RenderContext) -> RenderOutput:
        """Render one output."""
        return self.get(output_format).render(context)

    def formats(self) -> tuple[RenderFormat, ...]:
        """Return registered formats in canonical order."""
        return tuple(
            output_format for output_format in RENDER_FORMATS if output_format in self._renderers
        )

    def render_all(self, context: RenderContext) -> tuple[RenderOutput, ...]:
        """Render every registered format in canonical order."""
        return tuple(self.render(output_format, context) for output_format in self.formats())


def default_registry() -> RendererRegistry:
    """Return a registry populated with all built-in renderers."""
    return RendererRegistry(
        (
            HtmlRenderer(),
            MarkdownRenderer(),
            JsonRenderer(),
            PrintCssRenderer(),
        )
    )


default_renderers = default_registry()
