"""Value types for the v4 structured query language.

The query language is data-only: expressions are parsed into immutable tokens,
saved queries are plain records, and facets/clusters are read models. Nothing
in this package evaluates shell code, imports modules, or performs I/O beyond
the in-memory adapters in :mod:`redscribe.v4.query.storage`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from dataclasses import field as dc_field
from enum import Enum

from redscribe.v4.contracts import ApiError, Capability, ErrorCode, is_entity_id, new_entity_id
from redscribe.v4.events import utc_now

MAX_EXPRESSION_LENGTH = 500
MAX_NAME_LENGTH = 80
MAX_FACET_VALUES = 50
MAX_CLUSTER_SAMPLES = 5
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 500
UNKNOWN_CLUSTER_KEY = "(unknown)"

_NORMALIZE_RE = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s]+""")


class QueryError(ValueError):
    """Base class for domain-level query failures."""

    code: ErrorCode = ErrorCode.INVALID_INPUT

    def __init__(
        self,
        message: str,
        *,
        position: int | None = None,
        details: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.position = position
        self.details: tuple[str, ...] = tuple(details)

    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.message} at position {self.position}"

    def to_api_error(self) -> ApiError:
        """Convert the domain error into the shared v4 API error shape."""
        details = list(self.details)
        if self.position is not None:
            details.append(f"position={self.position}")
        return ApiError(code=self.code, message=self.message, details=tuple(details))


class QuerySyntaxError(QueryError):
    """Raised when an expression cannot be parsed."""

    def __init__(
        self,
        message: str,
        position: int,
        *,
        details: Sequence[str] = (),
    ) -> None:
        super().__init__(message, position=position, details=details)


class QueryNotFoundError(QueryError):
    """Raised when a saved query id is unknown."""

    code = ErrorCode.NOT_FOUND

    def __init__(self, query_id: str) -> None:
        super().__init__(
            f"unknown saved query: {query_id}",
            details=(f"id={query_id}",),
        )
        self.query_id = query_id


class DuplicateQueryNameError(QueryError):
    """Raised when a saved-query name is already taken."""

    code = ErrorCode.CONFLICT

    def __init__(self, name: str) -> None:
        super().__init__(f"query name already exists: {name}", details=(f"name={name}",))
        self.name = name


class QueryCapacityError(QueryError):
    """Raised when the saved-query store is full."""

    code = ErrorCode.UNAVAILABLE

    def __init__(self, capacity: int) -> None:
        super().__init__(
            f"query store capacity reached: {capacity}",
            details=(f"capacity={capacity}",),
        )
        self.capacity = capacity


class FieldName(str, Enum):
    """Fields a structured clause may target."""

    TITLE = "title"
    BODY = "body"
    TAG = "tag"
    KIND = "kind"
    STATUS = "status"
    FLAG = "flag"
    TARGET = "target"
    AUTHOR = "author"

    @classmethod
    def parse(cls, value: str) -> FieldName | None:
        """Return the matching field, or ``None`` for an unknown name."""
        normalized = value.strip().casefold()
        for member in cls:
            if member.value == normalized:
                return member
        return None

    @classmethod
    def require(cls, value: str, position: int = 0) -> FieldName:
        """Parse a field or raise a positioned syntax error."""
        parsed = cls.parse(value)
        if parsed is None:
            raise QuerySyntaxError(f"unknown field: {value}", position, details=(f"field={value}",))
        return parsed

    @property
    def label(self) -> str:
        return FIELD_LABELS[self.value]

    @property
    def suggested_operators(self) -> tuple[Operator, ...]:
        """Operators offered as UI hints for this field."""
        if self in (FieldName.TITLE, FieldName.BODY, FieldName.AUTHOR):
            return (Operator.CONTAINS, Operator.EQ, Operator.STARTS_WITH, Operator.NEQ)
        if self in (FieldName.TAG, FieldName.TARGET):
            return (Operator.IN, Operator.EQ, Operator.NEQ, Operator.CONTAINS)
        return (Operator.EQ, Operator.NEQ, Operator.IN)


FIELD_LABELS: dict[str, str] = {
    FieldName.TITLE.value: "Title",
    FieldName.BODY.value: "Body",
    FieldName.TAG.value: "Tag",
    FieldName.KIND.value: "Kind",
    FieldName.STATUS.value: "Status",
    FieldName.FLAG.value: "Flag",
    FieldName.TARGET.value: "Target",
    FieldName.AUTHOR.value: "Author",
}


class Operator(str, Enum):
    """Comparison operators supported by clause expressions."""

    EQ = "="
    NEQ = "!="
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GT = ">"
    LT = "<"
    IN = "in"

    @classmethod
    def parse(cls, value: str) -> Operator | None:
        """Parse an operator spelling, including friendly aliases."""
        normalized = value.strip().casefold()
        normalized = OPERATOR_ALIASES.get(normalized, normalized)
        for member in cls:
            if member.value == normalized:
                return member
        return None

    @classmethod
    def require(cls, value: str, position: int = 0) -> Operator:
        parsed = cls.parse(value)
        if parsed is None:
            raise QuerySyntaxError(
                f"unknown operator: {value}", position, details=(f"operator={value}",)
            )
        return parsed

    @property
    def is_set(self) -> bool:
        return self is Operator.IN

    @property
    def is_relational(self) -> bool:
        return self in (Operator.GT, Operator.LT)

    @property
    def label(self) -> str:
        return OPERATOR_LABELS[self.value]


OPERATOR_ALIASES: dict[str, str] = {
    "==": "=",
    "!": "!=",
    "<>": "!=",
    ">=": ">",
    "<=": "<",
    "startswith": "starts_with",
    "sw": "starts_with",
    "has": "contains",
    "oneof": "in",
}

OPERATOR_LABELS: dict[str, str] = {
    Operator.EQ.value: "equals",
    Operator.NEQ.value: "does not equal",
    Operator.CONTAINS.value: "contains",
    Operator.STARTS_WITH.value: "starts with",
    Operator.GT.value: "greater than",
    Operator.LT.value: "less than",
    Operator.IN.value: "is one of",
}


class BooleanOp(str, Enum):
    """Boolean connectors between clauses."""

    AND = "and"
    OR = "or"
    NOT = "not"

    @classmethod
    def parse(cls, value: str) -> BooleanOp | None:
        normalized = value.strip().casefold()
        for member in cls:
            if member.value == normalized:
                return member
        return None

    @property
    def precedence(self) -> int:
        return {BooleanOp.OR: 1, BooleanOp.AND: 2, BooleanOp.NOT: 3}[self]


def normalize_expression(raw: str) -> str:
    """Collapse whitespace and normalize keywords without touching quoted text."""
    parts = _NORMALIZE_RE.findall(raw.strip())
    normalized: list[str] = []
    for part in parts:
        upper = part.upper()
        if upper in ("AND", "OR", "NOT"):
            normalized.append(upper)
            continue
        if ":" in part:
            name, _, tail = part.partition(":")
            field_name = FieldName.parse(name)
            if field_name is not None:
                normalized.append(f"{field_name.value}:{tail}")
                continue
        normalized.append(part)
    return " ".join(normalized)


def coerce_text(value: object) -> str:
    """Render a document field value as stable, case-foldable text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def coerce_values(value: object) -> tuple[str, ...]:
    """Flatten scalar or collection field values into a tuple of text."""
    if isinstance(value, Mapping):
        return tuple(coerce_text(item) for item in value.values() if item is not None)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(coerce_text(item) for item in value if item is not None)
    text = coerce_text(value)
    return (text,) if text else ()


def sequence_of(value: object) -> tuple[object, ...]:
    """Return ``value`` as a tuple when it is a JSON-style array."""
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def as_int(value: object, default: int = 0) -> int:
    """Coerce a JSON scalar to an integer without raising."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return default


@dataclass(frozen=True, slots=True)
class QueryToken:
    """One parsed clause in a structured query."""

    field: FieldName
    operator: Operator = Operator.EQ
    value: str = ""
    values: tuple[str, ...] = ()
    boolean: BooleanOp | None = None
    negated: bool = False
    free_text: bool = False
    position: int = 0

    def __post_init__(self) -> None:
        if self.free_text:
            if not self.value.strip():
                raise QueryError("free-text token requires a non-empty value")
            return
        if self.operator.is_set:
            if not self.values:
                raise QueryError("the in operator requires at least one value")
            if any(not item for item in self.values):
                raise QueryError("in values must not be empty")
        elif not self.value:
            raise QueryError("clause requires a non-empty value")
        if len(self.terms) > MAX_FACET_VALUES:
            raise QueryError(f"too many clause values (max {MAX_FACET_VALUES})")

    @property
    def terms(self) -> tuple[str, ...]:
        return self.values if self.operator.is_set else (self.value,)

    @property
    def expression(self) -> str:
        """Render this token back into canonical query syntax."""
        prefix = ""
        if self.boolean is not None and self.boolean is not BooleanOp.NOT:
            prefix = f"{self.boolean.value.upper()} "
        if self.negated:
            prefix += "NOT "
        if self.free_text:
            return f'{prefix}"{self.value}"'
        if self.operator.is_set:
            arguments = ", ".join(self.values)
            body = f"{self.field.value}:{self.operator.value}({arguments})"
        elif self.operator is Operator.EQ:
            body = f'{self.field.value}:"{self.value}"'
        else:
            body = f'{self.field.value}:{self.operator.value}("{self.value}")'
        return f"{prefix}{body}"

    def with_boolean(self, boolean: BooleanOp | None) -> QueryToken:
        return replace(self, boolean=boolean)

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field.value,
            "operator": self.operator.value,
            "value": self.value,
            "values": list(self.values),
            "boolean": self.boolean.value if self.boolean is not None else None,
            "negated": self.negated,
            "free_text": self.free_text,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> QueryToken:
        boolean_raw = data.get("boolean")
        boolean = BooleanOp.parse(str(boolean_raw)) if boolean_raw is not None else None
        values = data.get("values", [])
        return cls(
            field=FieldName.require(str(data.get("field", ""))),
            operator=Operator.require(str(data.get("operator", Operator.EQ.value))),
            value=str(data.get("value", "")),
            values=tuple(str(item) for item in sequence_of(values)),
            boolean=boolean,
            negated=bool(data.get("negated", False)),
            free_text=bool(data.get("free_text", False)),
            position=as_int(data.get("position")),
        )


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """A parsed expression, its source text, and its canonical form."""

    tokens: tuple[QueryToken, ...] = ()
    raw: str = ""
    normalized: str = ""

    def __post_init__(self) -> None:
        if len(self.raw) > MAX_EXPRESSION_LENGTH:
            raise QueryError(
                f"expression exceeds {MAX_EXPRESSION_LENGTH} characters",
                details=(f"length={len(self.raw)}",),
            )
        if not self.normalized:
            object.__setattr__(self, "normalized", normalize_expression(self.raw))

    @property
    def is_empty(self) -> bool:
        return not self.tokens

    @property
    def token_count(self) -> int:
        return len(self.tokens)

    @property
    def fields(self) -> frozenset[FieldName]:
        return frozenset(token.field for token in self.tokens)

    @property
    def connectors(self) -> tuple[BooleanOp, ...]:
        return tuple(token.boolean for token in self.tokens if token.boolean is not None)

    @property
    def free_text_terms(self) -> tuple[str, ...]:
        return tuple(token.value for token in self.tokens if token.free_text)

    def describe(self) -> str:
        """Return a compact human-readable summary."""
        if self.is_empty:
            return "match all"
        return " ".join(token.expression for token in self.tokens)

    def to_dict(self) -> dict[str, object]:
        return {
            "tokens": [token.to_dict() for token in self.tokens],
            "raw": self.raw,
            "normalized": self.normalized,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ParsedQuery:
        raw = str(data.get("raw", ""))
        tokens_data = data.get("tokens", [])
        tokens = tuple(
            QueryToken.from_dict(item)
            for item in sequence_of(tokens_data)
            if isinstance(item, Mapping)
        )
        return cls(
            tokens=tokens,
            raw=raw,
            normalized=str(data.get("normalized", "")) or normalize_expression(raw),
        )


@dataclass(frozen=True, slots=True)
class FacetValue:
    """A single facet bucket with an optional user selection."""

    value: str
    count: int
    selected: bool = False

    def __post_init__(self) -> None:
        if not self.value:
            raise QueryError("facet value must not be empty")
        if self.count < 0:
            raise QueryError("facet count must be >= 0")

    def with_selected(self, selected: bool) -> FacetValue:
        return replace(self, selected=selected)

    def to_dict(self) -> dict[str, object]:
        return {"value": self.value, "count": self.count, "selected": self.selected}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> FacetValue:
        return cls(
            value=str(data.get("value", "")),
            count=as_int(data.get("count")),
            selected=bool(data.get("selected", False)),
        )


@dataclass(frozen=True, slots=True)
class FacetDefinition:
    """Faceted counts for one field over a result set."""

    field: FieldName
    label: str = ""
    values: tuple[FacetValue, ...] = dc_field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", FIELD_LABELS[self.field.value])
        if len(self.values) > MAX_FACET_VALUES:
            raise QueryError(f"too many facet values (max {MAX_FACET_VALUES})")
        seen: set[str] = set()
        for item in self.values:
            key = item.value.casefold()
            if key in seen:
                raise QueryError(f"duplicate facet value: {item.value}")
            seen.add(key)

    @property
    def total_count(self) -> int:
        return sum(item.count for item in self.values)

    @property
    def selected_values(self) -> tuple[str, ...]:
        return tuple(item.value for item in self.values if item.selected)

    def with_selection(self, selected: Sequence[str]) -> FacetDefinition:
        wanted = {item.casefold() for item in selected}
        return replace(
            self,
            values=tuple(
                item.with_selected(item.value.casefold() in wanted) for item in self.values
            ),
        )

    def top(self, limit: int) -> FacetDefinition:
        """Return a copy limited to the strongest buckets."""
        if limit < 1:
            raise QueryError("facet limit must be >= 1")
        return replace(self, values=self.values[:limit])

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field.value,
            "label": self.label,
            "values": [item.to_dict() for item in self.values],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> FacetDefinition:
        values_data = data.get("values", [])
        return cls(
            field=FieldName.require(str(data.get("field", ""))),
            label=str(data.get("label", "")),
            values=tuple(
                FacetValue.from_dict(item)
                for item in sequence_of(values_data)
                if isinstance(item, Mapping)
            ),
        )


@dataclass(frozen=True, slots=True)
class SavedQuery:
    """A named, persisted query expression."""

    id: str = dc_field(default_factory=new_entity_id)
    name: str = ""
    expression: str = ""
    created_at: str = dc_field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not is_entity_id(self.id):
            raise QueryError(f"invalid saved query id: {self.id}")
        name = self.name.strip()
        if not name:
            raise QueryError("saved query name must not be empty")
        if len(name) > MAX_NAME_LENGTH:
            raise QueryError(f"name exceeds {MAX_NAME_LENGTH} characters")
        object.__setattr__(self, "name", name)
        if not self.expression.strip():
            raise QueryError("saved query expression must not be empty")
        if len(self.expression) > MAX_EXPRESSION_LENGTH:
            raise QueryError(f"expression exceeds {MAX_EXPRESSION_LENGTH} characters")
        if not self.created_at:
            raise QueryError("created_at must not be empty")

    def rename(self, name: str) -> SavedQuery:
        return replace(self, name=name)

    def with_expression(self, expression: str) -> SavedQuery:
        return replace(self, expression=expression)

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "expression": self.expression,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SavedQuery:
        return cls(
            id=str(data.get("id", new_entity_id())),
            name=str(data.get("name", "")),
            expression=str(data.get("expression", "")),
            created_at=str(data.get("created_at", utc_now())),
        )


@dataclass(frozen=True, slots=True)
class ResultCluster:
    """A group of results sharing a value on one field."""

    key: str
    count: int
    sample_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key:
            raise QueryError("cluster key must not be empty")
        if self.count < 0:
            raise QueryError("cluster count must be >= 0")
        if len(self.sample_ids) > MAX_CLUSTER_SAMPLES:
            raise QueryError(f"too many cluster samples (max {MAX_CLUSTER_SAMPLES})")
        if len(self.sample_ids) > self.count:
            raise QueryError("sample_ids cannot exceed the cluster count")

    @property
    def sample_count(self) -> int:
        return len(self.sample_ids)

    def ratio(self, total: int) -> float:
        """Fraction of the overall result set held by this cluster."""
        if total <= 0:
            return 0.0
        return round(self.count / total, 4)

    def merge(self, other: ResultCluster) -> ResultCluster:
        if self.key != other.key:
            raise QueryError("cannot merge clusters with different keys")
        samples = list(self.sample_ids)
        for sample in other.sample_ids:
            if sample not in samples and len(samples) < MAX_CLUSTER_SAMPLES:
                samples.append(sample)
        return ResultCluster(self.key, self.count + other.count, tuple(samples))

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "count": self.count,
            "sample_ids": list(self.sample_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ResultCluster:
        samples = data.get("sample_ids", [])
        return cls(
            key=str(data.get("key", "")),
            count=as_int(data.get("count")),
            sample_ids=tuple(str(item) for item in sequence_of(samples)),
        )


QUERY_CAPABILITIES: dict[str, Capability] = {
    "search": Capability.READ,
    "list": Capability.READ,
    "get": Capability.READ,
    "save": Capability.WRITE,
    "rename": Capability.WRITE,
    "delete": Capability.DELETE,
    "export": Capability.EXPORT,
}

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "FIELD_LABELS",
    "MAX_CLUSTER_SAMPLES",
    "MAX_EXPRESSION_LENGTH",
    "MAX_FACET_VALUES",
    "MAX_NAME_LENGTH",
    "MAX_PAGE_SIZE",
    "OPERATOR_LABELS",
    "QUERY_CAPABILITIES",
    "UNKNOWN_CLUSTER_KEY",
    "BooleanOp",
    "DuplicateQueryNameError",
    "FacetDefinition",
    "FacetValue",
    "FieldName",
    "Operator",
    "ParsedQuery",
    "QueryCapacityError",
    "QueryError",
    "QueryNotFoundError",
    "QuerySyntaxError",
    "QueryToken",
    "ResultCluster",
    "SavedQuery",
    "as_int",
    "coerce_text",
    "coerce_values",
    "normalize_expression",
    "sequence_of",
]
