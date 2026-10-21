"""Backward-compatible imports for the canonical syntax highlighter.

New code should import from :mod:`redscribe.content.highlight`.
"""

from __future__ import annotations

from redscribe.content.highlight import CodeToken, normalize_language, tokenize_code

__all__ = ["CodeToken", "normalize_language", "tokenize_code"]
