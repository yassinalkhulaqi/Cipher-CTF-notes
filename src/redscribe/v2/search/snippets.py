"""Snippet extraction and match highlighting for search results."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from redscribe.domain.fuzzy import edit_distance
from redscribe.v2.search.models import (
    SNIPPET_WIDTH,
    HighlightSpan,
    IndexedDocument,
    ParsedQuery,
    Snippet,
    TextChunk,
    Token,
)
from redscribe.v2.search.tokenizer import collapse_whitespace, fold_text, stem

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
_ELLIPSIS = "…"


def _fold_span(text: str, start: int, end: int) -> str:
    return stem(fold_text(text[start:end]))


def find_term_spans(text: str, term: str, *, fuzzy: bool = True) -> tuple[HighlightSpan, ...]:
    """Return source-offset highlight spans for one query term."""
    if not text or not term:
        return ()
    needle = stem(term) if " " not in term else fold_text(term)
    if " " in needle:
        folded = fold_text(text)
        position = folded.find(needle)
        if position < 0:
            return ()
        return (HighlightSpan(position, min(len(text), position + len(needle)), term, "phrase"),)

    spans: list[HighlightSpan] = []
    for match in _WORD_RE.finditer(text):
        candidate = _fold_span(text, match.start(), match.end())
        if not candidate:
            continue
        kind = ""
        if candidate == needle:
            kind = "exact"
        elif needle and candidate.startswith(needle):
            kind = "prefix"
        elif (
            fuzzy
            and len(needle) >= 4
            and edit_distance(needle, candidate, max_distance=1) is not None
        ):
            kind = "fuzzy"
        if kind:
            spans.append(HighlightSpan(match.start(), match.end(), term, kind))
    return tuple(spans)


def find_query_spans(
    text: str,
    terms: Iterable[str],
    *,
    fuzzy: bool = True,
) -> tuple[HighlightSpan, ...]:
    """Collect and merge highlight spans for many query terms."""
    collected: list[HighlightSpan] = []
    for term in terms:
        collected.extend(find_term_spans(text, term, fuzzy=fuzzy))
    return merge_spans(collected)


def merge_spans(spans: Iterable[HighlightSpan]) -> tuple[HighlightSpan, ...]:
    """Merge overlapping or adjacent highlight spans."""
    ordered = sorted(spans, key=lambda span: (span.start, span.end))
    merged: list[HighlightSpan] = []
    for span in ordered:
        if span.end <= span.start:
            continue
        if merged and span.start <= merged[-1].end:
            previous = merged[-1]
            kind = "mixed" if previous.kind != span.kind else previous.kind
            merged[-1] = HighlightSpan(
                previous.start,
                max(previous.end, span.end),
                previous.term,
                kind,
            )
            continue
        merged.append(span)
    return tuple(merged)


def _window(span: HighlightSpan, text_length: int, width: int) -> tuple[int, int]:
    radius = max(1, width // 2)
    start = max(0, span.start - radius // 2)
    end = min(text_length, max(span.end + radius // 2, start + width))
    if end - start < width and start > 0:
        start = max(0, end - width)
    return start, end


def _merge_windows(
    windows: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            continue
        merged.append((start, end))
    return merged


def _clipped_spans(
    spans: Sequence[HighlightSpan],
    start: int,
    end: int,
) -> list[tuple[int, int, HighlightSpan]]:
    clipped: list[tuple[int, int, HighlightSpan]] = []
    for span in spans:
        if span.end <= start or span.start >= end:
            continue
        clipped.append((max(span.start, start), min(span.end, end), span))
    return clipped


def build_snippet(
    text: str,
    terms: Iterable[str],
    *,
    width: int = SNIPPET_WIDTH,
    max_fragments: int = 2,
) -> Snippet:
    """Build a compact excerpt with highlights mapped to its offsets."""
    cleaned = collapse_whitespace(text)
    values = [value for value in terms if value]
    if not cleaned or not values or width < 1:
        excerpt = cleaned[:width]
        if len(cleaned) > width:
            excerpt = f"{excerpt.rstrip()}{_ELLIPSIS}"
        return Snippet(excerpt, (), 0)

    spans = find_query_spans(cleaned, values)
    if not spans:
        excerpt = cleaned[:width]
        if len(cleaned) > width:
            excerpt = f"{excerpt.rstrip()}{_ELLIPSIS}"
        return Snippet(excerpt, (), 0)

    windows = _merge_windows([_window(span, len(cleaned), width) for span in spans])[
        : max(1, max_fragments)
    ]
    pieces: list[str] = []
    mapped: list[HighlightSpan] = []
    cursor = 0
    for index, (start, end) in enumerate(windows):
        if index:
            pieces.append(f" {_ELLIPSIS} ")
            cursor += 3
        prefix = _ELLIPSIS if start > 0 else ""
        suffix = _ELLIPSIS if end < len(cleaned) else ""
        pieces.append(prefix)
        cursor += len(prefix)
        fragment = cleaned[start:end]
        for local_start, local_end, span in _clipped_spans(spans, start, end):
            mapped.append(
                HighlightSpan(
                    cursor + local_start - start,
                    cursor + local_end - start,
                    span.term,
                    span.kind,
                )
            )
        pieces.append(fragment)
        cursor += len(fragment)
        pieces.append(suffix)
        cursor += len(suffix)
    return Snippet("".join(pieces), merge_spans(mapped), len(windows))


def build_document_snippet(
    document: IndexedDocument,
    query: ParsedQuery,
    *,
    width: int = SNIPPET_WIDTH,
) -> Snippet:
    """Select the best matching field and build a highlighted snippet."""
    search_terms = [term.value for term in query.positive if not term.negated]
    if not search_terms:
        return build_snippet(document.field_text("content"), (), width=width)
    best: Snippet | None = None
    best_score = -1.0
    for field in document.fields:
        spans = find_query_spans(field.text, search_terms)
        if not spans:
            continue
        score = len(spans) * field.boost + min(field.length, 40) / 100.0
        if score > best_score:
            best_score = score
            best = build_snippet(field.text, search_terms, width=width)
    if best is not None:
        return best
    for fallback in ("content", "tags", "target", "title"):
        text = document.field_text(fallback)
        if text:
            return build_snippet(text, (), width=width)
    return Snippet("", (), 0)


def highlight_chunks(snippet: Snippet) -> tuple[TextChunk, ...]:
    """Return alternating plain and highlighted chunks for rendering."""
    return snippet.chunks()


def token_offsets(text: str) -> tuple[Token, ...]:
    """Tokenize text while preserving original source offsets."""
    tokens: list[Token] = []
    for match in _WORD_RE.finditer(text):
        raw = match.group(0)
        tokens.append(
            Token(
                text=raw,
                normalized=fold_text(raw),
                start=match.start(),
                end=match.end(),
            )
        )
    return tuple(tokens)
