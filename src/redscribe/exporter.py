"""Backward-compatible imports for the canonical export service.

New code should import from :mod:`redscribe.services.exporter`.
"""

from __future__ import annotations

from redscribe.domain.utils import safe_filename
from redscribe.services.exporter import (
    export_note_html,
    export_note_markdown,
    export_vault_html,
    export_vault_markdown,
    note_front_matter,
    note_to_markdown,
)

__all__ = [
    "export_note_html",
    "export_note_markdown",
    "export_vault_html",
    "export_vault_markdown",
    "note_front_matter",
    "note_to_markdown",
    "safe_filename",
]
