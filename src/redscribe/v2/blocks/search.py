"""In-memory full-text index scoped to individual blocks."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.blocks.constants import (
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SNIPPET_LENGTH,
    MAX_SEARCH_RESULTS,
    MAX_SEARCH_TERMS,
)
from redscribe.v2.blocks.model import Block, BlockDocument
from redscribe.v2.blocks.types import BlockType

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_WORD_BOUNDARY = re.compile(r"(?<=\w)(?=\W)|(?<=\W)(?=\w)")


def tokenize(text: str) -> tuple[str, ...]:
    """Return lowercase word tokens from arbitrary text."""
    return tuple(token for token in _TOKEN_RE.findall(text.casefold()) if token)


def query_terms(query: str) -> tuple[str, ...]:
    """Parse a search query into a capped list of unique terms."""
    seen: set[str] = set()
    terms: list[str] = []
    for term in tokenize(query):
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= MAX_SEARCH_TERMS:
            break
    return tuple(terms)


def snippet_for(text: str, terms: Sequence[str], *, width: int = DEFAULT_SNIPPET_LENGTH) -> str:
    """Return a compact excerpt centred on the first query match."""
    if len(text) <= width:
        return text
    lowered = text.casefold()
    position = -1
    for term in terms:
        candidate = lowered.find(term)
        if candidate >= 0 and (position < 0 or candidate < position):
            position = candidate
    if position < 0:
        return text[:width].rstrip() + "…"
    start = max(0, position - width // 3)
    end = min(len(text), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def highlight_terms(text: str, terms: Sequence[str]) -> tuple[str, ...]:
    """Return terms that occur in ``text``, ordered by query position."""
    lowered = text.casefold()
    return tuple(term for term in terms if term and term in lowered)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One matching block with ranking and excerpt metadata."""

    document_id: str
    document_title: str
    block_id: str
    block_type: str
    score: int
    snippet: str
    highlights: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "block_id": self.block_id,
            "block_type": self.block_type,
            "score": self.score,
            "snippet": self.snippet,
            "highlights": list(self.highlights),
        }


class BlockSearchIndex:
    """Token-postings index over documents and their blocks."""

    def __init__(self) -> None:
        self._documents: dict[str, BlockDocument] = {}
        self._postings: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._owners: dict[tuple[str, str], str] = {}
        self._block_types: dict[tuple[str, str], BlockType] = {}

    def clear(self) -> None:
        """Drop all indexed documents."""
        self._documents.clear()
        self._postings.clear()
        self._owners.clear()
        self._block_types.clear()

    def add(self, document: BlockDocument) -> int:
        """Index a document, replacing any previous copy."""
        self.remove(document.id)
        self._documents[document.id] = document
        count = 0
        for block in document.blocks:
            owner = (document.id, block.id)
            self._owners[owner] = document.title
            self._block_types[owner] = block.type
            for token in set(tokenize(block.plain_text)):
                self._postings[token].add(owner)
                count += 1
        return count

    def remove(self, document_id: str) -> bool:
        """Remove a document from the index."""
        document = self._documents.pop(document_id, None)
        if document is None:
            return False
        for owner in [(document_id, block.id) for block in document.blocks]:
            self._owners.pop(owner, None)
            self._block_types.pop(owner, None)
            for values in self._postings.values():
                values.discard(owner)
        for token in [token for token, values in self._postings.items() if not values]:
            del self._postings[token]
        return True

    def replace(self, document: BlockDocument) -> int:
        """Atomically replace one indexed document."""
        return self.add(document)

    def reindex(self, documents: Iterable[BlockDocument]) -> int:
        """Rebuild the index from a collection of documents."""
        self.clear()
        return sum(1 for document in documents if self.add(document) >= 0)

    @property
    def document_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._documents))

    def size(self) -> int:
        """Return the number of indexed blocks."""
        return len(self._owners)

    def vocabulary(self) -> tuple[str, ...]:
        """Return indexed terms in deterministic order."""
        return tuple(sorted(self._postings))

    def search(
        self,
        query: str,
        *,
        block_types: Iterable[BlockType | str] | None = None,
        document_id: str | None = None,
        match_all: bool = True,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Rank blocks matching every (or any) term in ``query``."""
        terms = query_terms(query)
        if not terms:
            return []
        allowed: set[str] | None = None
        if block_types is not None:
            allowed = {
                item.value if isinstance(item, BlockType) else str(item) for item in block_types
            }
        candidates: dict[tuple[str, str], int] = {}
        for term in terms:
            for owner in self._postings.get(term, ()):
                candidates[owner] = candidates.get(owner, 0) + 1
        if match_all:
            owners = [owner for owner, count in candidates.items() if count == len(terms)]
        else:
            owners = list(candidates)
        results: list[SearchResult] = []
        for document_id_value, block_id in owners:
            if document_id is not None and document_id_value != document_id:
                continue
            block_type = self._block_types.get((document_id_value, block_id))
            if block_type is None:
                continue
            if allowed is not None and block_type.value not in allowed:
                continue
            document = self._documents[document_id_value]
            block = document.find(block_id)
            if block is None:
                continue
            text = block.plain_text
            lowered = text.casefold()
            score = 10 * candidates[(document_id_value, block_id)]
            score += sum(3 for term in terms if term == lowered)
            score += sum(2 for term in terms if lowered.startswith(term))
            score += min(10, len(text) // 200)
            results.append(
                SearchResult(
                    document_id=document_id_value,
                    document_title=self._owners[(document_id_value, block_id)],
                    block_id=block_id,
                    block_type=block_type.value,
                    score=score,
                    snippet=snippet_for(text, terms),
                    highlights=highlight_terms(text, terms),
                )
            )
        results.sort(
            key=lambda item: (
                -item.score,
                item.document_id,
                item.block_id,
            )
        )
        start = max(0, offset)
        return results[start : start + max(0, min(limit, MAX_SEARCH_RESULTS))]

    def facets(self) -> dict[str, int]:
        """Return indexed block counts by type."""
        return dict(sorted(Counter(item.value for item in self._block_types.values()).items()))

    def terms_for(self, document_id: str, block_id: str) -> tuple[str, ...]:
        """Return all indexed tokens for one block."""
        document = self._documents.get(document_id)
        if document is None:
            return ()
        block = document.find(block_id)
        return tokenize(block.plain_text) if block is not None else ()


def build_search_index(documents: Sequence[BlockDocument]) -> BlockSearchIndex:
    """Build a search index from a document sequence."""
    index = BlockSearchIndex()
    index.reindex(documents)
    return index


def search_payload(results: Sequence[SearchResult]) -> dict[str, Any]:
    """Serialize a result list with stable metadata."""
    return {
        "total": len(results),
        "items": [result.as_dict() for result in results],
    }


def merge_results(
    left: Sequence[SearchResult], right: Sequence[SearchResult]
) -> list[SearchResult]:
    """Merge result lists by score and identity."""
    seen: set[tuple[str, str]] = set()
    combined: list[SearchResult] = []
    for result in [*left, *right]:
        key = (result.document_id, result.block_id)
        if key in seen:
            continue
        seen.add(key)
        combined.append(result)
    combined.sort(key=lambda item: (-item.score, item.document_id, item.block_id))
    return combined


def result_to_mapping(result: SearchResult) -> Mapping[str, Any]:
    """Return a read-only mapping view of one result."""
    return result.as_dict()


def block_from_result(
    documents: Mapping[str, BlockDocument],
    result: SearchResult,
) -> Block | None:
    """Resolve a search result back to its block."""
    document = documents.get(result.document_id)
    return document.find(result.block_id) if document is not None else None


def word_boundary_count(text: str) -> int:
    """Count coarse word boundaries, useful for diff summaries."""
    return len(_WORD_BOUNDARY.findall(text))
