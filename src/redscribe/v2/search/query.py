"""Parser and normalizer for the v2 search query grammar."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from redscribe.v2.search.filters import FILTER_FIELDS, parse_filter_token
from redscribe.v2.search.models import (
    MAX_QUERY_LENGTH,
    SEARCH_FIELDS,
    FilterClause,
    ParsedQuery,
    QueryTerm,
    SortKey,
)
from redscribe.v2.search.synonyms import SynonymSet
from redscribe.v2.search.tokenizer import collapse_whitespace, fold_text, normalize_token, stem

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
_FIELD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*:")
_BOOST_RE = re.compile(r"\^(?P<value>\d+(?:\.\d+)?)")
_FUZZY_RE = re.compile(r"~(?P<value>\d*)")
_PREFIX_CHAR = "*"
_SYNONYM_WEIGHT = 0.55


@dataclass(frozen=True, slots=True)
class QueryLexeme:
    """One lexical unit emitted by the query scanner."""

    text: str
    start: int
    end: int
    field: str = ""
    quoted: bool = False
    negated: bool = False
    optional: bool = False
    prefix: bool = False
    fuzzy: bool = False
    boost: float = 1.0
    operator: str = ""

    @property
    def is_operator(self) -> bool:
        return bool(self.operator)


def _read_boost(text: str, start: int) -> tuple[float, int]:
    match = _BOOST_RE.match(text, start)
    if match is None:
        return 1.0, start
    value = float(match.group("value"))
    return max(0.0, min(10.0, value)), match.end()


def _read_fuzzy(text: str, start: int) -> tuple[bool, int]:
    match = _FUZZY_RE.match(text, start)
    if match is None:
        return False, start
    return True, match.end()


def lex_query(text: str) -> tuple[QueryLexeme, ...]:
    """Scan a query string into lexemes with modifiers and positions."""
    result: list[QueryLexeme] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        start = index
        negated = False
        optional = False
        if character in "-+" and index + 1 < length and not text[index + 1].isspace():
            negated = character == "-"
            optional = character == "+"
            index += 1
            character = text[index]

        if character in "()":
            result.append(QueryLexeme(character, start, index + 1, operator="group"))
            index += 1
            continue

        word_match = _WORD_RE.match(text, index)
        if word_match is not None and word_match.group(0).upper() in {"AND", "OR", "NOT"}:
            word = word_match.group(0).upper()
            result.append(QueryLexeme(word, start, word_match.end(), operator=word))
            index = word_match.end()
            continue

        field = ""
        field_match = _FIELD_RE.match(text, index)
        if field_match is not None:
            field = field_match.group(0)[:-1].casefold()
            index = field_match.end()

        quoted = False
        if index < length and text[index] == '"':
            quoted = True
            index += 1
            value_start = index
            closing = text.find('"', index)
            if closing < 0:
                raw = text[value_start:]
                index = length
            else:
                raw = text[value_start:closing]
                index = closing + 1
        else:
            value_match = _WORD_RE.match(text, index)
            if value_match is None:
                index += 1
                continue
            raw = value_match.group(0)
            index = value_match.end()

        prefix = False
        if index < length and text[index] == _PREFIX_CHAR:
            prefix = True
            index += 1
        fuzzy, index = _read_fuzzy(text, index)
        boost, index = _read_boost(text, index)
        if not raw and not field:
            continue
        result.append(
            QueryLexeme(
                text=raw,
                start=start,
                end=index,
                field=field,
                quoted=quoted,
                negated=negated,
                optional=optional,
                prefix=prefix,
                fuzzy=fuzzy,
                boost=boost,
            )
        )
    return tuple(result)


def _term_value(lexeme: QueryLexeme) -> str:
    if lexeme.quoted:
        return collapse_whitespace(fold_text(lexeme.text))
    return stem(normalize_token(lexeme.text))


def _parse_sort(value: str | None) -> SortKey:
    if not value:
        return SortKey.RELEVANCE
    try:
        return SortKey(value.strip().casefold())
    except ValueError as exc:
        raise ValueError(f"Unsupported sort key: {value}") from exc


class QueryParser:
    """Turn user text into weighted terms, filters, and sort options."""

    def __init__(self, synonyms: SynonymSet | None = None) -> None:
        self._synonyms = synonyms if synonyms is not None else SynonymSet()

    def parse(
        self,
        text: str,
        *,
        sort: str | None = None,
        group_by: str = "",
        expand: bool = True,
    ) -> ParsedQuery:
        """Parse and normalize one search expression."""
        if not isinstance(text, str):
            raise TypeError("query must be a string")
        if len(text) > MAX_QUERY_LENGTH:
            raise ValueError(f"query exceeds {MAX_QUERY_LENGTH} characters")
        lexemes = lex_query(text.strip())
        terms: list[QueryTerm] = []
        filters: list[FilterClause] = []
        negate_next = False
        optional_next = False

        for lexeme in lexemes:
            if lexeme.is_operator:
                if lexeme.operator == "NOT":
                    negate_next = True
                elif lexeme.operator == "OR":
                    optional_next = True
                continue
            if (
                lexeme.field
                and lexeme.field in FILTER_FIELDS
                and not (lexeme.quoted and lexeme.field in SEARCH_FIELDS)
            ):
                raw = f"{lexeme.field}{'!=' if lexeme.negated else ':'}{lexeme.text}"
                filters.append(parse_filter_token(raw))
                continue
            value = _term_value(lexeme)
            if not value:
                continue
            terms.append(
                QueryTerm(
                    value=value,
                    field=lexeme.field if lexeme.field in SEARCH_FIELDS else "",
                    boost=lexeme.boost,
                    prefix=lexeme.prefix,
                    fuzzy=lexeme.fuzzy,
                    phrase=lexeme.quoted or " " in value,
                    negated=lexeme.negated or negate_next,
                    optional=lexeme.optional or optional_next,
                )
            )
            negate_next = False
            optional_next = False

        terms = _dedupe_terms(terms)
        if expand and self._synonyms:
            terms = _with_synonyms(terms, self._synonyms)
        return ParsedQuery(
            text=text.strip(),
            terms=tuple(terms),
            filters=tuple(filters),
            sort=_parse_sort(sort),
            group_by=group_by.strip().casefold(),
        )


def _dedupe_terms(terms: list[QueryTerm]) -> list[QueryTerm]:
    merged: dict[str, QueryTerm] = {}
    for term in terms:
        existing = merged.get(term.key)
        if existing is None:
            merged[term.key] = term
            continue
        merged[term.key] = QueryTerm(
            value=term.value,
            field=term.field,
            boost=max(existing.boost, term.boost),
            prefix=existing.prefix or term.prefix,
            fuzzy=existing.fuzzy or term.fuzzy,
            phrase=existing.phrase or term.phrase,
            negated=existing.negated and term.negated,
            optional=existing.optional or term.optional,
            synonym=existing.synonym and term.synonym,
        )
    return list(merged.values())


def _with_synonyms(terms: list[QueryTerm], synonyms: SynonymSet) -> list[QueryTerm]:
    expanded = list(terms)
    for term in terms:
        if term.negated or term.phrase:
            continue
        for value in synonyms.expand(term.value, include_self=False):
            candidate = QueryTerm(
                value=value,
                field=term.field,
                boost=round(term.boost * _SYNONYM_WEIGHT, 4),
                prefix=False,
                fuzzy=False,
                negated=False,
                optional=True,
                synonym=True,
            )
            if candidate.key not in {item.key for item in expanded}:
                expanded.append(candidate)
    return expanded


def query_fingerprint(query: ParsedQuery) -> str:
    """Return a stable cache key for a parsed query."""
    raw = "|".join(
        [
            query.text.casefold(),
            ",".join(term.key for term in query.terms),
            ",".join(item.key for item in query.filters),
            query.sort.value,
            query.group_by,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def describe_query(query: ParsedQuery) -> dict[str, object]:
    """Return a human-readable debug view of a parsed query."""
    return {
        "text": query.text,
        "terms": [term.as_dict() for term in query.terms],
        "filters": [item.as_dict() for item in query.filters],
        "sort": query.sort.value,
        "group_by": query.group_by,
        "fingerprint": query_fingerprint(query),
    }


def query_to_text(query: ParsedQuery) -> str:
    """Serialize a parsed query back into a compact query string."""
    pieces: list[str] = []
    for item in query.filters:
        pieces.append(f"{'-' if item.negated else ''}{item.field}{item.operator}{item.value}")
    for term in query.terms:
        if term.synonym:
            continue
        prefix = "-" if term.negated else ("+" if term.optional else "")
        field = f"{term.field}:" if term.field else ""
        value = f'"{term.value}"' if term.phrase else term.value
        suffix = "~" if term.fuzzy else ""
        suffix += f"^{term.boost:g}" if term.boost != 1.0 else ""
        pieces.append(f"{prefix}{field}{value}{suffix}")
    return " ".join(pieces)


def suggest_query_completions(
    text: str,
    vocabulary: Iterable[str],
    *,
    limit: int = 8,
) -> tuple[str, ...]:
    """Complete the final token of a query from an index vocabulary."""
    last = text.rsplit(" ", 1)[-1].casefold().strip('"')
    if not last:
        return ()
    matches = sorted(term for term in vocabulary if term.startswith(last))
    return tuple(matches[: max(0, limit)])
