"""Tiny fuzzy matcher for the quick switcher."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


_WORD_BOUNDARIES = frozenset(" /\\_-.:([{")


def fuzzy_score(query: str, text: str) -> int | None:
    """Score how well ``query`` matches ``text`` as a subsequence.

    Returns ``None`` when the query is not a subsequence. Higher is better.
    Prefix matches, word boundaries, contiguous runs, and exact substrings
    receive bonuses so that intentional abbreviations outrank accidental
    letter soup.
    """
    needle = query.strip().casefold()
    if not needle:
        return 0
    haystack = text.casefold()
    if len(needle) > len(haystack):
        return None
    score = 0
    position = -1
    previous = -2
    contiguous = 0
    for character in needle:
        next_position = haystack.find(character, position + 1)
        if next_position < 0:
            return None
        position = next_position
        score += 1
        if previous >= 0 and position == previous + 1:
            contiguous += 1
            score += 8 + min(contiguous, 4) * 2
        else:
            contiguous = 0
        if position == 0 or haystack[position - 1] in _WORD_BOUNDARIES:
            score += 7
        previous = position
    stripped = haystack.strip()
    if stripped.startswith(needle):
        score += 26
    if needle in haystack:
        score += 14
    if needle == stripped:
        score += 42
    score -= max(0, len(haystack) - len(needle)) // 20
    return score


def fuzzy_match(query: str, text: str) -> bool:
    """Return whether ``query`` is a subsequence of ``text``."""
    return fuzzy_score(query, text) is not None


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
