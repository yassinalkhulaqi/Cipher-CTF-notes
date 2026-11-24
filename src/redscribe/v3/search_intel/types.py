"""Core value types for the V3 cross-entity search intelligence package.

The types here are storage-agnostic and deliberately independent from any
branch that owns a particular entity kind. They are built on the universal
contracts in :mod:`redscribe.v3.entities` and :mod:`redscribe.v3.events`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.entities.types import ENTITY_KINDS, LINK_KINDS, EntityStatus
from redscribe.v3.events.types import EventSeverity

MAX_QUERY_LENGTH = 500
MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 240
MAX_TAG_LENGTH = 40


class FieldName(str, Enum):
    """Fields understood by the query language v2 grammar."""

    KIND = "kind"
    TAG = "tag"
    SEVERITY = "severity"
    STATUS = "status"
    BEFORE = "before"
    HAS = "has"

    @classmethod
    def parse(cls, value: str) -> FieldName | None:
        """Return the field for a token, or ``None`` when it is unknown."""
        normalized = value.strip().casefold()
        for member in cls:
            if member.value == normalized:
                return member
        return None


QUERY_FIELDS: tuple[str, ...] = tuple(member.value for member in FieldName)

KIND_VALUES: tuple[str, ...] = tuple(ENTITY_KINDS)
SEVERITY_VALUES: tuple[str, ...] = tuple(member.value for member in EventSeverity)
STATUS_VALUES: tuple[str, ...] = tuple(member.value for member in EntityStatus)
HAS_VALUES: tuple[str, ...] = ("link",)
LINK_VALUE_KINDS: tuple[str, ...] = tuple(LINK_KINDS)

FIELD_VOCABULARY: dict[str, tuple[str, ...]] = {
    FieldName.KIND.value: KIND_VALUES,
    FieldName.TAG.value: (),
    FieldName.SEVERITY.value: SEVERITY_VALUES,
    FieldName.STATUS.value: STATUS_VALUES,
    FieldName.BEFORE.value: (),
    FieldName.HAS.value: HAS_VALUES,
}


class TokenKind(str, Enum):
    """Lexical categories emitted by the query tokenizer."""

    WORD = "word"
    QUOTED = "quoted"
    COLON = "colon"
    LPAREN = "lparen"
    RPAREN = "rparen"
    PIPE = "pipe"
    MINUS = "minus"
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class Token:
    """One lexed token with source offsets."""

    kind: TokenKind
    value: str
    start: int
    end: int

    @property
    def text(self) -> str:
        """Raw source slice for this token."""
        return self.value

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "kind": self.kind.value,
            "value": self.value,
            "start": self.start,
            "end": self.end,
        }


class IssueCode(str, Enum):
    """Stable, machine-readable parser diagnostic codes."""

    EMPTY_QUERY = "empty_query"
    QUERY_TOO_LONG = "query_too_long"
    UNTERMINATED_QUOTE = "unterminated_quote"
    EMPTY_FIELD_VALUE = "empty_field_value"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_FIELD_VALUE = "invalid_field_value"
    UNKNOWN_LINK_KIND = "unknown_link_kind"
    UNEXPECTED_TOKEN = "unexpected_token"
    UNCLOSED_GROUP = "unclosed_group"
    EMPTY_GROUP = "empty_group"
    DANGLING_NEGATION = "dangling_negation"
    UNKNOWN_KEYWORD = "unknown_keyword"


@dataclass(frozen=True, slots=True)
class ParseIssue:
    """A stable diagnostic produced by tokenizing or parsing a query."""

    code: IssueCode
    message: str
    start: int
    end: int
    field: str = ""
    severity: str = "error"
    hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "code": self.code.value,
            "message": self.message,
            "start": self.start,
            "end": self.end,
            "field": self.field,
            "severity": self.severity,
            "hint": self.hint,
        }


class ClauseKind(str, Enum):
    """Semantic type of a parsed query clause."""

    TERM = "term"
    FIELD = "field"
    HAS_LINK = "has_link"


@dataclass(frozen=True, slots=True)
class QueryClause:
    """A single match predicate inside a conjunction group."""

    kind: ClauseKind
    value: str = ""
    raw: str = ""
    field: str = ""
    negated: bool = False
    phrase: bool = False
    start: int = 0
    end: int = 0
    link_kind: str = ""
    before: float = 0.0
    boost: float = 1.0

    @property
    def key(self) -> str:
        """Stable identity used for deduplication."""
        return f"{self.kind.value}:{self.field}:{self.value}:{int(self.negated)}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "kind": self.kind.value,
            "value": self.value,
            "raw": self.raw,
            "field": self.field,
            "negated": self.negated,
            "phrase": self.phrase,
            "start": self.start,
            "end": self.end,
            "link_kind": self.link_kind,
            "before": self.before,
            "boost": self.boost,
        }


@dataclass(frozen=True, slots=True)
class AndGroup:
    """A conjunction of clauses; an OR of groups forms the parsed query."""

    clauses: tuple[QueryClause, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"clauses": [clause.as_dict() for clause in self.clauses]}


def query_fingerprint(text: str) -> str:
    """Return a stable short hash for a query expression."""
    normalized = " ".join(text.split()).casefold()
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).hexdigest()
    return digest[:12]


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """Disjunctive-normal-form query plus diagnostics and metadata."""

    text: str
    groups: tuple[AndGroup, ...] = (AndGroup(),)
    tokens: tuple[Token, ...] = ()
    issues: tuple[ParseIssue, ...] = ()
    fingerprint: str = ""

    @property
    def is_valid(self) -> bool:
        """Return whether parsing produced no error-severity issues."""
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def clauses(self) -> tuple[QueryClause, ...]:
        """Return every clause across all groups in stable order."""
        return tuple(clause for group in self.groups for clause in group.clauses)

    @property
    def fields(self) -> tuple[str, ...]:
        """Return distinct field names referenced by the query."""
        return tuple(sorted({clause.field for clause in self.clauses if clause.field}))

    @property
    def terms(self) -> tuple[str, ...]:
        """Return distinct positive free-text terms."""
        return tuple(
            dict.fromkeys(
                clause.value
                for clause in self.clauses
                if clause.kind is ClauseKind.TERM and not clause.negated
            )
        )

    @property
    def error_codes(self) -> tuple[str, ...]:
        """Return distinct error codes in stable order."""
        return tuple(
            sorted({issue.code.value for issue in self.issues if issue.severity == "error"})
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "text": self.text,
            "valid": self.is_valid,
            "fingerprint": self.fingerprint,
            "groups": [group.as_dict() for group in self.groups],
            "tokens": [token.as_dict() for token in self.tokens],
            "issues": [issue.as_dict() for issue in self.issues],
        }


class FacetField(str, Enum):
    """Fields that can be extracted as facets from search results."""

    KIND = "kind"
    TAG = "tag"
    SEVERITY = "severity"
    STATUS = "status"
    HAS_LINK = "has_link"
    OWNER = "owner"

    @classmethod
    def parse(cls, value: str) -> FacetField | None:
        """Parse a facet field name."""
        normalized = value.strip().casefold()
        for member in cls:
            if member.value == normalized:
                return member
        return None


DEFAULT_FACET_FIELDS: tuple[str, ...] = (
    FacetField.KIND.value,
    FacetField.STATUS.value,
    FacetField.SEVERITY.value,
    FacetField.TAG.value,
    FacetField.HAS_LINK.value,
)


@dataclass(frozen=True, slots=True)
class FacetCount:
    """One facet value and its document count."""

    value: str
    count: int
    selected: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"value": self.value, "count": self.count, "selected": self.selected}


@dataclass(frozen=True, slots=True)
class FacetResult:
    """Counts for one facet field."""

    field: str
    values: tuple[FacetCount, ...] = ()
    total: int = 0
    missing: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "field": self.field,
            "values": [value.as_dict() for value in self.values],
            "total": self.total,
            "missing": self.missing,
        }


class ClusterStrategy(str, Enum):
    """Supported result-clustering strategies."""

    NONE = "none"
    FIELD = "field"
    SIMILARITY = "similarity"

    @classmethod
    def parse(cls, value: str) -> ClusterStrategy:
        """Parse a strategy name, falling back to field grouping."""
        normalized = value.strip().casefold()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.FIELD


@dataclass(frozen=True, slots=True)
class ClusterGroup:
    """A group of related search hits."""

    key: str
    label: str
    refs: tuple[str, ...] = ()
    count: int = 0
    score: float = 0.0
    strategy: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "label": self.label,
            "refs": list(self.refs),
            "count": self.count,
            "score": round(self.score, 6),
            "strategy": self.strategy,
        }


class PivotRole(str, Enum):
    """Why a pivot is being suggested."""

    OWNS = "owns"
    EVIDENCES = "evidences"
    DERIVES = "derives"
    REFERENCES = "references"
    RELATES = "relates"
    CONTAINS = "contains"
    SIBLING = "sibling"
    REPORT = "report"


@dataclass(frozen=True, slots=True)
class PivotSuggestion:
    """A cross-entity navigation suggestion."""

    ref: str
    kind: str
    label: str
    role: str
    reason: str
    score: float
    link_kind: str = ""
    query: str = ""
    depth: int = 1

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": self.ref,
            "kind": self.kind,
            "label": self.label,
            "role": self.role,
            "reason": self.reason,
            "score": round(self.score, 6),
            "link_kind": self.link_kind,
            "query": self.query,
            "depth": self.depth,
        }


@dataclass(frozen=True, slots=True)
class Highlight:
    """A matched span inside a document field."""

    start: int
    end: int
    value: str
    field: str = "summary"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "start": self.start,
            "end": self.end,
            "value": self.value,
            "field": self.field,
        }


@dataclass(frozen=True, slots=True)
class Fragment:
    """A short snippet around the first match in a document field."""

    text: str
    highlights: tuple[Highlight, ...] = ()
    field: str = "summary"
    prefix: bool = False
    suffix: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "text": self.text,
            "highlights": [item.as_dict() for item in self.highlights],
            "field": self.field,
            "prefix": self.prefix,
            "suffix": self.suffix,
        }


@dataclass(frozen=True, slots=True)
class IndexDocument:
    """A searchable projection of a universal entity record."""

    ref: str
    kind: str
    title: str
    summary: str = ""
    tags: tuple[str, ...] = ()
    status: str = EntityStatus.DRAFT.value
    severity: str = ""
    owner: str = ""
    updated_at: float = 0.0
    has_links: bool = False
    link_degree: int = 0
    link_kinds: tuple[str, ...] = ()
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> frozenset[str]:
        """Return case-folded tokens used for term matching."""
        pieces = [self.title, self.summary, *self.tags, self.owner]
        result: set[str] = set()
        for piece in pieces:
            for raw in piece.casefold().split():
                token = "".join(char for char in raw if char.isalnum() or char in "_-/#.")
                if token:
                    result.add(token)
        return frozenset(result)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": self.ref,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "tags": list(self.tags),
            "status": self.status,
            "severity": self.severity,
            "owner": self.owner,
            "updated_at": self.updated_at,
            "has_links": self.has_links,
            "link_degree": self.link_degree,
            "link_kinds": list(self.link_kinds),
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RankDetails:
    """Explainable components of a relevance score."""

    total: float
    components: dict[str, float] = field(default_factory=dict)
    matched_terms: tuple[str, ...] = ()
    coverage: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "total": round(self.total, 6),
            "components": {key: round(value, 6) for key, value in self.components.items()},
            "matched_terms": list(self.matched_terms),
            "coverage": round(self.coverage, 6),
        }


@dataclass(frozen=True, slots=True)
class RankedHit:
    """One ranked search result with a fragment and explanation."""

    doc: IndexDocument
    score: float
    details: RankDetails
    fragment: Fragment

    @property
    def ref(self) -> str:
        """Canonical entity reference shortcut."""
        return self.doc.ref

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "document": self.doc.as_dict(),
            "score": round(self.score, 6),
            "score_details": self.details.as_dict(),
            "fragment": self.fragment.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SavedSearch:
    """A named, reusable query expression."""

    id: str
    name: str
    query: str
    description: str = ""
    tags: tuple[str, ...] = ()
    pinned: bool = False
    use_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "name": self.name,
            "query": self.query,
            "description": self.description,
            "tags": list(self.tags),
            "pinned": self.pinned,
            "use_count": self.use_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class SavedFacetSet:
    """A named selection of facet fields."""

    id: str
    name: str
    fields: tuple[str, ...] = ()
    description: str = ""
    created_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "name": self.name,
            "fields": list(self.fields),
            "description": self.description,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class QueryTemplate:
    """A parameterized query pattern with typed placeholders."""

    id: str
    name: str
    pattern: str
    description: str = ""
    placeholders: tuple[str, ...] = ()
    category: str = "general"
    example: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "name": self.name,
            "pattern": self.pattern,
            "description": self.description,
            "placeholders": list(self.placeholders),
            "category": self.category,
            "example": self.example,
        }


@dataclass(frozen=True, slots=True)
class IndexState:
    """A succinct snapshot of the incremental search index."""

    generation: int
    documents: int
    tokens: int
    dirty: int
    by_kind: dict[str, int] = field(default_factory=dict)
    last_action: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "generation": self.generation,
            "documents": self.documents,
            "tokens": self.tokens,
            "dirty": self.dirty,
            "by_kind": dict(self.by_kind),
            "last_action": self.last_action,
        }
