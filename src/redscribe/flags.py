"""Backward-compatible imports for the canonical flag detector.

New code should import from :mod:`redscribe.domain.flags`.
"""

from __future__ import annotations

from redscribe.domain.flags import (
    FLAG_PREFIXES,
    FLAG_RE,
    find_flags,
    has_flag,
    merge_flags,
    primary_flag,
)

__all__ = ["FLAG_PREFIXES", "FLAG_RE", "find_flags", "has_flag", "merge_flags", "primary_flag"]
