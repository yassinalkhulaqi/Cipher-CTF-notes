"""Backward-compatible imports for the canonical note templates.

New code should import from :mod:`redscribe.content.templates`.
"""

from __future__ import annotations

from redscribe.content.templates import (
    TEMPLATE_MAP,
    TEMPLATES,
    get_template,
    render_template,
)

__all__ = ["TEMPLATES", "TEMPLATE_MAP", "get_template", "render_template"]
