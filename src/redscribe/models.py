"""Backward-compatible imports for the canonical domain records.

New code should import from :mod:`redscribe.domain.models`.
"""

from __future__ import annotations

from redscribe.domain.models import (
    DIFFICULTIES,
    DIFFICULTY_LABELS,
    KINDS,
    STATUS_ICONS,
    STATUS_LABELS,
    STATUSES,
    FlagHit,
    Node,
    NodeTree,
    SearchHit,
    Snippet,
    TagCount,
    Template,
    VaultStats,
)

__all__ = [
    "DIFFICULTIES",
    "DIFFICULTY_LABELS",
    "KINDS",
    "STATUSES",
    "STATUS_ICONS",
    "STATUS_LABELS",
    "FlagHit",
    "Node",
    "NodeTree",
    "SearchHit",
    "Snippet",
    "TagCount",
    "Template",
    "VaultStats",
]
