"""Backward-compatible imports for the canonical snippet library.

New code should import from :mod:`redscribe.content.snippets`.
"""

from __future__ import annotations

from redscribe.content.snippets import (
    BUILTIN_BY_KEY,
    BUILTIN_SNIPPETS,
    resolve_command,
    snippet_placeholders,
)

__all__ = [
    "BUILTIN_BY_KEY",
    "BUILTIN_SNIPPETS",
    "resolve_command",
    "snippet_placeholders",
]
