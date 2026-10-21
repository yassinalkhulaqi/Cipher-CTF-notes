"""Backward-compatible imports for the canonical domain helpers.

New code should import from :mod:`redscribe.domain.utils`.
"""

from __future__ import annotations

from redscribe.domain.utils import (
    collapse_whitespace,
    format_number,
    humanize_delta,
    parse_timestamp,
    pluralize,
    safe_filename,
    slugify,
    truncate,
    utc_now,
    word_count,
)

__all__ = [
    "collapse_whitespace",
    "format_number",
    "humanize_delta",
    "parse_timestamp",
    "pluralize",
    "safe_filename",
    "slugify",
    "truncate",
    "utc_now",
    "word_count",
]
