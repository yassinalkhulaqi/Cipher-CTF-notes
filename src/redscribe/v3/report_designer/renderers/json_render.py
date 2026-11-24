"""Canonical JSON renderer for report designs."""

from __future__ import annotations

from typing import Any

from redscribe.v3.report_designer.identifiers import canonical_json
from redscribe.v3.report_designer.renderers.base import (
    JSON,
    RenderContext,
    RenderOutput,
    make_output,
)


class JsonRenderer:
    """Render the full design, plan, and manifest as stable JSON."""

    @property
    def format(self) -> str:
        """Format discriminator."""
        return JSON

    def payload(self, context: RenderContext) -> dict[str, Any]:
        """Build the JSON-serializable payload."""
        return {
            "document": context.document.as_dict(),
            "theme": context.theme.as_dict(),
            "pagination": context.plan.as_dict(),
            "toc": [entry.as_dict() for entry in context.entries],
            "manifest": context.manifest,
        }

    def render(self, context: RenderContext) -> RenderOutput:
        """Render the report payload as canonical JSON."""
        return make_output(JSON, canonical_json(self.payload(context)), context.document)
