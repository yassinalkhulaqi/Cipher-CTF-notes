"""Backward-compatible imports for the canonical fuzzy matcher.

New code should import from :mod:`redscribe.domain.fuzzy`.
"""

from __future__ import annotations

from redscribe.domain.fuzzy import fuzzy_match, fuzzy_score, rank_items

__all__ = ["fuzzy_match", "fuzzy_score", "rank_items"]
