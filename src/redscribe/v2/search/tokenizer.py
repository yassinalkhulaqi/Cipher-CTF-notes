"""Unicode-aware tokenization for the incremental search index."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

from redscribe.v2.search.models import Token

_WORD_RE = re.compile(r"[\w]+(?:['’-][\w]+)*", re.UNICODE)
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w]+", re.UNICODE)
_ACRONYM_RE = re.compile(r"^[A-Z0-9]{2,}$")

STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "with",
    }
)

_SUFFIXES: tuple[str, ...] = (
    "iness",
    "ingly",
    "ations",
    "ation",
    "ings",
    "ies",
    "ing",
    "ed",
    "es",
    "s",
)


def collapse_whitespace(text: str) -> str:
    """Collapse all whitespace runs and trim the result."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def fold_text(text: str) -> str:
    """Fold accents and case while keeping word characters and spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    unmarked = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return collapse_whitespace(unmarked).casefold()


def normalize_token(text: str) -> str:
    """Return the canonical comparable form of a single token."""
    folded = fold_text(text)
    return _PUNCTUATION_RE.sub("", folded)


def is_stopword(token: str) -> bool:
    """Return whether a normalized token is a search stopword."""
    return normalize_token(token) in STOPWORDS


def split_compound(token: str) -> tuple[str, ...]:
    """Split camel-case and hyphenated compounds into searchable parts."""
    normalized = normalize_token(token)
    if not normalized:
        return ()
    if len(normalized) > 40:
        return (normalized,)
    parts: list[str] = []
    for section in re.split(r"[-_]", token):
        pieces = [piece for piece in _CAMEL_BOUNDARY_RE.split(section) if piece]
        for piece in pieces:
            folded = normalize_token(piece)
            if folded and folded not in parts and folded != normalized:
                parts.append(folded)
    return tuple(parts)


def stem(token: str) -> str:
    """Apply a conservative English stem used for index keys."""
    value = normalize_token(token)
    if len(value) < 5:
        return value
    for suffix in _SUFFIXES:
        if not value.endswith(suffix):
            continue
        root = value[: -len(suffix)]
        if suffix == "ies" and len(root) >= 2:
            return f"{root}y"
        if suffix in {"ing", "ed", "es", "s"} and len(root) >= 3:
            if suffix in {"ing", "ed"} and len(root) >= 4 and root[-1] == root[-2]:
                return root[:-1]
            return root
        if len(root) >= 4:
            return root
    return value


def token_key(token: str) -> str:
    """Return the index key for a token, including its compound parts."""
    value = stem(token)
    if value and not value.isdigit() and not _ACRONYM_RE.fullmatch(value):
        return value
    return value


def tokenize(
    text: str,
    *,
    field: str = "",
    keep_stopwords: bool = False,
    min_length: int = 1,
) -> tuple[Token, ...]:
    """Tokenize text with source offsets and folded comparison values."""
    if not text or min_length < 1:
        return ()
    tokens: list[Token] = []
    for match in _WORD_RE.finditer(text):
        raw = match.group(0)
        normalized = normalize_token(raw)
        if not normalized or len(normalized) < min_length:
            continue
        if not keep_stopwords and is_stopword(normalized):
            continue
        tokens.append(
            Token(
                text=raw,
                normalized=normalized,
                start=match.start(),
                end=match.end(),
                field=field,
                kind="number" if normalized.isdigit() else "word",
            )
        )
    return tuple(tokens)


def tokenize_query(text: str, *, field: str = "") -> tuple[Token, ...]:
    """Tokenize a query, retaining quoted phrases as single tokens."""
    tokens: list[Token] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if character == '"':
            end = text.find('"', index + 1)
            if end < 0:
                tokens.extend(tokenize(text[index + 1 :], field=field))
                break
            phrase = text[index + 1 : end]
            tokens.append(
                Token(
                    text=phrase,
                    normalized=collapse_whitespace(fold_text(phrase)),
                    start=index + 1,
                    end=end,
                    field=field,
                    kind="phrase",
                )
            )
            index = end + 1
            continue
        match = _WORD_RE.match(text, index)
        if match is None:
            index += 1
            continue
        raw = match.group(0)
        normalized = normalize_token(raw)
        if normalized and not is_stopword(normalized):
            tokens.append(
                Token(
                    text=raw,
                    normalized=normalized,
                    start=match.start(),
                    end=match.end(),
                    field=field,
                )
            )
        index = match.end()
    return tuple(tokens)


def index_terms(token: Token) -> tuple[str, ...]:
    """Return every index term emitted for one token."""
    terms: list[str] = []
    if token.kind == "phrase":
        for word in tokenize(token.normalized, keep_stopwords=True):
            value = stem(word.normalized)
            if value and value not in terms:
                terms.append(value)
        return tuple(terms)
    value = stem(token.normalized)
    if value:
        terms.append(value)
    for part in split_compound(token.text):
        part_value = stem(part)
        if part_value and part_value not in terms:
            terms.append(part_value)
    return tuple(terms)


def ngrams(tokens: Sequence[str], sizes: Iterable[int] = (2, 3)) -> tuple[str, ...]:
    """Return unique contiguous n-grams for the requested sizes."""
    values = list(tokens)
    results: list[str] = []
    for size in sizes:
        if size < 1:
            continue
        for index in range(0, max(0, len(values) - size + 1)):
            grams = " ".join(values[index : index + size])
            if grams not in results:
                results.append(grams)
    return tuple(results)


def word_count(text: str) -> int:
    """Count searchable words in a piece of text."""
    return len(tokenize(text, keep_stopwords=True))


def token_positions(text: str, term: str) -> tuple[int, ...]:
    """Return token ordinals where a folded term occurs in text."""
    target = stem(term)
    positions: list[int] = []
    for position, token in enumerate(tokenize(text, keep_stopwords=True)):
        if token.normalized == target or stem(token.normalized) == target:
            positions.append(position)
    return tuple(positions)
