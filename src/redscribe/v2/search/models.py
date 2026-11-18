"""Shared value objects for the v2 search and command engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SEARCH_FIELDS: tuple[str, ...] = (
    "title",
    "content",
    "tags",
    "target",
    "flag",
    "path",
)

DEFAULT_FIELD_BOOSTS: dict[str, float] = {
    "title": 6.0,
    "tags": 4.0,
    "flag": 3.5,
    "target": 2.5,
    "path": 1.5,
    "content": 1.0,
}

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100
MAX_QUERY_LENGTH = 500
SNIPPET_WIDTH = 180


class SearchField(str, Enum):
    """Searchable fields exposed by the index."""

    TITLE = "title"
    CONTENT = "content"
    TAGS = "tags"
    TARGET = "target"
    FLAG = "flag"
    PATH = "path"


class SortKey(str, Enum):
    """Supported result orderings."""

    RELEVANCE = "relevance"
    UPDATED = "updated"
    TITLE = "title"
    ID = "id"


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical token with offsets into the original text."""

    text: str
    normalized: str
    start: int
    end: int
    field: str = ""
    kind: str = "word"

    @property
    def length(self) -> int:
        return self.end - self.start

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "normalized": self.normalized,
            "start": self.start,
            "end": self.end,
            "field": self.field,
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class IndexedField:
    """A named text field stored for one document."""

    name: str
    text: str
    tokens: tuple[Token, ...]
    boost: float

    @property
    def length(self) -> int:
        return len(self.tokens)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "text": self.text,
            "tokens": [token.as_dict() for token in self.tokens],
            "boost": self.boost,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> IndexedField:
        tokens = tuple(Token(**dict(item)) for item in payload.get("tokens", ()))
        return cls(
            name=str(payload.get("name", "")),
            text=str(payload.get("text", "")),
            tokens=tokens,
            boost=float(payload.get("boost", 1.0)),
        )


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    """A searchable note snapshot with metadata used by filters and ranking."""

    doc_id: int
    fields: tuple[IndexedField, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.field_text("title")

    @property
    def path(self) -> str:
        return str(self.metadata.get("path", ""))

    @property
    def updated_at(self) -> str:
        return str(self.metadata.get("updated_at", ""))

    @property
    def pinned(self) -> bool:
        return bool(self.metadata.get("pinned", False))

    def field(self, name: str) -> IndexedField | None:
        for item in self.fields:
            if item.name == name:
                return item
        return None

    def field_text(self, name: str) -> str:
        item = self.field(name)
        return item.text if item is not None else ""

    def fingerprint(self) -> str:
        payload = {
            "id": self.doc_id,
            "fields": [[item.name, item.text, item.boost] for item in self.fields],
            "metadata": self.metadata,
        }
        raw = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "fields": [item.as_dict() for item in self.fields],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> IndexedDocument:
        fields = tuple(IndexedField.from_dict(item) for item in payload.get("fields", ()))
        return cls(
            doc_id=int(payload["doc_id"]),
            fields=fields,
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class Posting:
    """One term occurrence set for a document and field."""

    term: str
    doc_id: int
    field: str
    frequency: int
    positions: tuple[int, ...]
    boost: float
    field_length: int


@dataclass(frozen=True, slots=True)
class TermStats:
    """Aggregate statistics for a term in the index."""

    term: str
    document_frequency: int
    total_frequency: int
    fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "document_frequency": self.document_frequency,
            "total_frequency": self.total_frequency,
            "fields": list(self.fields),
        }


@dataclass(frozen=True, slots=True)
class IndexStats:
    """A point-in-time summary of the inverted index."""

    documents: int
    terms: int
    postings: int
    generation: int
    average_field_length: float
    updated_at: str
    rebuilds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "documents": self.documents,
            "terms": self.terms,
            "postings": self.postings,
            "generation": self.generation,
            "average_field_length": round(self.average_field_length, 3),
            "updated_at": self.updated_at,
            "rebuilds": self.rebuilds,
        }


@dataclass(slots=True)
class IndexUpdate:
    """The outcome of a synchronous index update."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    generation: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "unchanged": self.unchanged,
            "generation": self.generation,
            "changed": self.changed,
        }


@dataclass(frozen=True, slots=True)
class FilterClause:
    """One structured filter extracted from a query string."""

    field: str
    operator: str
    value: str
    negated: bool = False

    @property
    def key(self) -> str:
        return f"{'-' if self.negated else ''}{self.field}{self.operator}{self.value}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
            "negated": self.negated,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> FilterClause:
        return cls(
            field=str(payload["field"]),
            operator=str(payload.get("operator", ":")),
            value=str(payload.get("value", "")),
            negated=bool(payload.get("negated", False)),
        )


@dataclass(frozen=True, slots=True)
class QueryTerm:
    """One weighted term in a parsed search query."""

    value: str
    field: str = ""
    boost: float = 1.0
    prefix: bool = False
    fuzzy: bool = False
    phrase: bool = False
    negated: bool = False
    optional: bool = False
    synonym: bool = False

    @property
    def key(self) -> str:
        return f"{self.field}:{self.value}" if self.field else self.value

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "field": self.field,
            "boost": self.boost,
            "prefix": self.prefix,
            "fuzzy": self.fuzzy,
            "phrase": self.phrase,
            "negated": self.negated,
            "optional": self.optional,
            "synonym": self.synonym,
        }


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """The normalized representation of a user search expression."""

    text: str
    terms: tuple[QueryTerm, ...]
    filters: tuple[FilterClause, ...] = ()
    sort: SortKey = SortKey.RELEVANCE
    group_by: str = ""

    @property
    def positive(self) -> tuple[QueryTerm, ...]:
        return tuple(term for term in self.terms if not term.negated)

    @property
    def negative(self) -> tuple[QueryTerm, ...]:
        return tuple(term for term in self.terms if term.negated)

    @property
    def phrases(self) -> tuple[QueryTerm, ...]:
        return tuple(term for term in self.terms if term.phrase and not term.negated)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "terms": [term.as_dict() for term in self.terms],
            "filters": [item.as_dict() for item in self.fields()],
            "sort": self.sort.value,
            "group_by": self.group_by,
        }

    def fields(self) -> tuple[FilterClause, ...]:
        return self.filters


@dataclass(frozen=True, slots=True)
class HighlightSpan:
    """A character range in a snippet that matched the query."""

    start: int
    end: int
    term: str
    kind: str = "term"

    def as_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "term": self.term, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A plain or highlighted slice of a snippet."""

    text: str
    match: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "match": self.match}


@dataclass(frozen=True, slots=True)
class Snippet:
    """A compact text excerpt with non-overlapping highlight ranges."""

    text: str
    highlights: tuple[HighlightSpan, ...] = ()
    fragments: int = 1

    @property
    def matched(self) -> bool:
        return bool(self.highlights)

    def chunks(self) -> tuple[TextChunk, ...]:
        result: list[TextChunk] = []
        cursor = 0
        for span in self.highlights:
            if span.start > cursor:
                result.append(TextChunk(self.text[cursor : span.start]))
            result.append(TextChunk(self.text[span.start : span.end], True))
            cursor = span.end
        if cursor < len(self.text):
            result.append(TextChunk(self.text[cursor:]))
        return tuple(result)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "highlights": [span.as_dict() for span in self.highlights],
            "chunks": [chunk.as_dict() for chunk in self.chunks()],
            "fragments": self.fragments,
            "matched": self.matched,
        }


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Explainable components of a document's relevance score."""

    total: float
    components: Mapping[str, float] = field(default_factory=dict)
    matched_terms: tuple[str, ...] = ()
    coverage: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 4),
            "components": {key: round(value, 4) for key, value in self.components.items()},
            "matched_terms": list(self.matched_terms),
            "coverage": round(self.coverage, 4),
        }


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One ranked search result ready for serialization."""

    node_id: int
    title: str
    path: str
    snippet: Snippet
    score: float
    score_details: ScoreBreakdown
    metadata: Mapping[str, Any] = field(default_factory=dict)
    group: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "path": self.path,
            "snippet": self.snippet.as_dict(),
            "score": round(self.score, 4),
            "score_details": self.score_details.as_dict(),
            "metadata": dict(self.metadata),
            "group": self.group,
        }


@dataclass(frozen=True, slots=True)
class FacetCount:
    """One value/count pair for a faceted field."""

    value: str
    count: int

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "count": self.count}


@dataclass(frozen=True, slots=True)
class ResultGroup:
    """A labeled bucket of search hits."""

    key: str
    label: str
    hits: tuple[SearchHit, ...]
    total: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "hits": [hit.as_dict() for hit in self.hits],
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class SearchResult:
    """The complete response produced by the search service."""

    query: ParsedQuery
    hits: tuple[SearchHit, ...]
    total: int
    facets: tuple[FacetCount, ...] = ()
    suggestions: tuple[str, ...] = ()
    generation: int = 0
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query.as_dict(),
            "items": [hit.as_dict() for hit in self.hits],
            "total": self.total,
            "facets": [facet.as_dict() for facet in self.facets],
            "suggestions": list(self.suggestions),
            "generation": self.generation,
            "elapsed_ms": round(self.elapsed_ms, 3),
        }


@dataclass(frozen=True, slots=True)
class SavedQuery:
    """A named, reusable search expression persisted in vault settings."""

    id: str
    name: str
    query: str
    description: str = ""
    tags: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    use_count: int = 0
    pinned: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "query": self.query,
            "description": self.description,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "use_count": self.use_count,
            "pinned": self.pinned,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SavedQuery:
        raw_tags = payload.get("tags", ())
        tags = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, Sequence) else ()
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            query=str(payload["query"]),
            description=str(payload.get("description", "")),
            tags=tags,
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            use_count=int(payload.get("use_count", 0)),
            pinned=bool(payload.get("pinned", False)),
        )


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp at second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_field_boosts(values: Mapping[str, float] | None = None) -> dict[str, float]:
    """Merge caller boosts with the defaults and reject unknown fields."""
    merged = dict(DEFAULT_FIELD_BOOSTS)
    if not values:
        return merged
    for name, value in values.items():
        if name not in merged:
            raise ValueError(f"Unknown search field: {name}")
        if value < 0:
            raise ValueError(f"Boost for {name} must be non-negative")
        merged[name] = float(value)
    return merged
