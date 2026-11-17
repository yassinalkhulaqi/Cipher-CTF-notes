"""Fuzzy matching and opt-in token-aware ranking for the quick switcher."""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import Generic, TypeVar

T = TypeVar("T")


_WORD_BOUNDARIES = frozenset(" /\\_-.:([{")
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


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


def fold_key(value: str) -> str:
    """Fold accents, case, and whitespace into a stable comparison key."""
    decomposed = unicodedata.normalize("NFKD", value)
    unmarked = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _WHITESPACE_RE.sub(" ", unmarked).strip().casefold()


def word_tokens(value: str) -> tuple[str, ...]:
    """Split text into folded word tokens."""
    return tuple(_TOKEN_RE.findall(fold_key(value)))


def edit_distance(left: str, right: str, *, max_distance: int = 2) -> int | None:
    """Return the bounded edit distance, or ``None`` when it exceeds the bound.

    Insertions, deletions, substitutions, and adjacent transpositions each
    cost one. Work stops as soon as the bound can no longer be met.
    """
    if max_distance < 0:
        raise ValueError("max_distance must be non-negative")
    if left == right:
        return 0
    if max_distance == 0 or abs(len(left) - len(right)) > max_distance:
        return None
    before_previous: list[int] = []
    previous = list(range(len(right) + 1))
    for row_index, left_character in enumerate(left, start=1):
        current = [row_index] + [0] * len(right)
        for column_index, right_character in enumerate(right, start=1):
            substitution = previous[column_index - 1] + (
                0 if left_character == right_character else 1
            )
            current[column_index] = min(
                previous[column_index] + 1,
                current[column_index - 1] + 1,
                substitution,
            )
            if (
                row_index > 1
                and column_index > 1
                and left_character == right[column_index - 2]
                and left[row_index - 2] == right_character
            ):
                current[column_index] = min(
                    current[column_index], before_previous[column_index - 2] + 1
                )
        if min(current) > max_distance:
            return None
        before_previous = previous
        previous = current
    distance = previous[len(right)]
    return distance if distance <= max_distance else None


def is_typo_of(word: str, candidate: str, *, max_distance: int = 1) -> bool:
    """Return whether two distinct words look like a one-edit typo pair."""
    if len(word) < 4 or word == candidate:
        return False
    return edit_distance(word, candidate, max_distance=max_distance) is not None


def _score_token(token: str, candidate: str) -> int | None:
    if token == candidate:
        return 60 + min(len(token), 8)
    if candidate.startswith(token):
        return 46 + min(len(token), 8)
    if token in candidate:
        return 34 + min(len(token), 8)
    subsequence = fuzzy_score(token, candidate)
    if subsequence is not None:
        return 8 + subsequence // 2
    if is_typo_of(token, candidate):
        return 22
    return None


def token_aware_score(query: str, text: str) -> int | None:
    """Score a query against text token by token, with tolerance for typos.

    Accents and case are folded first. Every query token must find a distinct
    candidate token (or the folded whole text); exact and prefix hits outrank
    subsequences and single-edit typos.
    """
    folded_query = fold_key(query)
    folded_text = fold_key(text)
    if not folded_query:
        return 0
    if not folded_text:
        return None
    query_tokens = word_tokens(folded_query) or (folded_query,)
    text_tokens = word_tokens(folded_text) or (folded_text,)
    candidates = [*text_tokens, folded_text]
    used: set[int] = set()
    score = 0
    positions: list[int] = []
    for token in query_tokens:
        best_index = -1
        best_score = 0
        for index, candidate in enumerate(candidates):
            if index in used:
                continue
            candidate_score = _score_token(token, candidate)
            if candidate_score is not None and candidate_score > best_score:
                best_score = candidate_score
                best_index = index
        if best_index < 0:
            return None
        used.add(best_index)
        score += best_score
        if best_index < len(text_tokens):
            positions.append(best_index)
    if folded_query == folded_text:
        score += 80
    elif folded_query in folded_text:
        score += 36
    if len(positions) == len(query_tokens) and positions == sorted(set(positions)):
        score += 12
    score -= max(0, len(folded_text) - len(folded_query)) // 12
    return max(1, score)


@dataclasses.dataclass(frozen=True, slots=True)
class RankedItem(Generic[T]):
    """One ranked item with its score and original input position."""

    item: T
    score: int
    order: int


def rank_scored(
    query: str,
    items: Sequence[T],
    *,
    key: Callable[[T], str],
    limit: int | None = None,
    scorer: Callable[[str, str], int | None] = token_aware_score,
) -> list[RankedItem[T]]:
    """Rank items with explicit, content-based tie-breaking.

    Ties are resolved by shorter text, then folded text, then input position,
    so the result is stable across runs and independent of hash ordering.
    """
    if not query.strip():
        return [RankedItem(item, 0, index) for index, item in enumerate(items)][:limit]
    scored: list[tuple[int, int, str, int, T]] = []
    cache: dict[str, tuple[int | None, str]] = {}
    for index, item in enumerate(items):
        text = key(item)
        cached = cache.get(text)
        if cached is None:
            cached = (scorer(query, text), fold_key(text))
            cache[text] = cached
        score, folded = cached
        if score is not None:
            scored.append((score, len(folded), folded, index, item))
    scored.sort(key=lambda entry: (-entry[0], entry[1], entry[2], entry[3]))
    ranked = [RankedItem(entry[4], entry[0], entry[3]) for entry in scored]
    return ranked[:limit] if limit is not None else ranked


def rank_tokens(
    query: str,
    items: Sequence[T],
    *,
    key: Callable[[T], str],
    limit: int | None = None,
) -> list[T]:
    """Return items ordered by token-aware score without exposing the scores."""
    return [entry.item for entry in rank_scored(query, items, key=key, limit=limit)]
