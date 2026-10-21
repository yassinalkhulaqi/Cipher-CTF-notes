"""Tiny fuzzy matcher for the quick switcher."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def fuzzy_score(query: str, text: str) -> int | None:
    """Score how well ``query`` matches ``text`` as a subsequence.

    Returns ``None`` when the query is not a subsequence. Higher is better.
    """
    needle = query.strip().lower()
    if not needle:
        return 0
    haystack = text.lower()
    score = 0
    position = -1
    previous = -2
    for character in needle:
        position = haystack.find(character, position + 1)
        if position < 0:
            return None
        score += 1
        if previous >= 0 and position == previous + 1:
            score += 9
        if position == 0 or haystack[position - 1] in " /\\_-.:(":
            score += 6
        previous = position
    stripped = haystack.strip()
    if stripped.startswith(needle):
        score += 24
    if needle in haystack:
        score += 12
    if needle == stripped:
        score += 40
    score -= max(0, len(haystack) - len(needle)) // 12
    return score


def rank_items(
    query: str,
    items: Sequence[T],
    *,
    key: Callable[[T], str],
    limit: int | None = None,
) -> list[T]:
    """Return items ordered by fuzzy score, preserving input order for ties."""
    if not query.strip():
        return list(items[:limit] if limit is not None else items)
    scored: list[tuple[int, int, T]] = []
    for index, item in enumerate(items):
        score = fuzzy_score(query, key(item))
        if score is not None:
            scored.append((score, -index, item))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    ranked = [entry[2] for entry in scored]
    return ranked[:limit] if limit is not None else ranked
