"""Universal contracts shared by every v4 feature slice.

The v4 program needs one vocabulary for entities, API envelopes, errors, and
capabilities so that independently built features compose. These contracts are
data-only and dependency-free; they never execute user-supplied code.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

ENTITY_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,2}$")


class EntityKind(str, Enum):
    """Kinds of first-class object in a RedScribe vault."""

    NOTE = "note"
    FOLDER = "folder"
    TARGET = "target"
    FINDING = "finding"
    EVIDENCE = "evidence"
    PLAYBOOK = "playbook"
    RUN = "run"
    REPORT = "report"
    INBOX_ITEM = "inbox_item"
    CAPTURE = "capture"
    GRAPH_FILTER = "graph_filter"
    QUERY = "query"
    KEY = "key"

    @classmethod
    def parse(cls, value: str) -> EntityKind:
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unknown entity kind: {value}")

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class Capability(str, Enum):
    """Capability flags checked by API routes and UI affordances."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXPORT = "export"
    ENCRYPT = "encrypt"
    AUTOMATE = "automate"
    ADMIN = "admin"


def new_entity_id() -> str:
    """Return a fresh, lowercase, RFC-4122-style identifier."""
    return str(uuid.uuid4())


def is_entity_id(value: str) -> bool:
    return bool(ENTITY_ID_PATTERN.match(value))


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A typed reference to another entity."""

    kind: EntityKind
    id: str
    label: str = ""

    def __post_init__(self) -> None:
        if not self.id or not is_entity_id(self.id):
            raise ValueError(f"Invalid entity id: {self.id}")

    def to_dict(self) -> dict[str, str]:
        data = {"kind": self.kind.value, "id": self.id}
        if self.label:
            data["label"] = self.label
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityRef:
        return cls(
            kind=EntityKind.parse(str(data.get("kind", ""))),
            id=str(data.get("id", "")),
            label=str(data.get("label", "")),
        )


@dataclass(frozen=True, slots=True)
class EntityLink:
    """A directed, typed edge between two entities."""

    source: EntityRef
    target: EntityRef
    relation: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not SLUG_PATTERN.match(self.relation):
            raise ValueError(f"Invalid relation slug: {self.relation}")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"Weight out of range: {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "relation": self.relation,
            "weight": self.weight,
        }


class ErrorCode(str, Enum):
    """Stable machine-readable error codes for the v4 API."""

    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"

    @property
    def http_status(self) -> int:
        return {
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.INVALID_INPUT: 400,
            ErrorCode.CONFLICT: 409,
            ErrorCode.FORBIDDEN: 403,
            ErrorCode.UNAVAILABLE: 503,
            ErrorCode.INTERNAL: 500,
        }[self]


@dataclass(frozen=True, slots=True)
class ApiError(Exception):
    """A structured API error."""

    code: ErrorCode
    message: str
    details: tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": list(self.details),
            }
        }


@dataclass(frozen=True, slots=True)
class PageMeta:
    """Cursor pagination metadata."""

    request_id: str
    version: str = "v4"
    page: int = 1
    page_size: int = 50
    etag: str = ""
    next_cursor: str = ""

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if not 1 <= self.page_size <= 500:
            raise ValueError("page_size must be between 1 and 500")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "version": self.version,
            "page": self.page,
            "page_size": self.page_size,
            "etag": self.etag,
            "next_cursor": self.next_cursor,
        }


def ok(data: Any, meta: PageMeta) -> dict[str, Any]:
    """Build a successful v4 envelope."""
    return {"data": data, "meta": meta.to_dict()}


def fail(error: ApiError) -> dict[str, Any]:
    """Build a failing v4 envelope."""
    return error.to_dict()


class EnvelopeDecoder:
    """Decode v4 envelopes with strict validation."""

    def __init__(self, expected_version: str = "v4") -> None:
        self.expected_version = expected_version

    def decode(self, payload: dict[str, Any]) -> Any:
        if "error" in payload:
            error = payload["error"]
            raise ApiError(
                code=ErrorCode(str(error.get("code", ErrorCode.INTERNAL.value))),
                message=str(error.get("message", "unknown error")),
                details=tuple(str(item) for item in error.get("details", [])),
            )
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            raise ApiError(ErrorCode.INVALID_INPUT, "missing meta in envelope")
        if meta.get("version") != self.expected_version:
            raise ApiError(ErrorCode.CONFLICT, f"unexpected version: {meta.get('version')}")
        return payload.get("data")


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    """An immutable set of granted capabilities."""

    granted: frozenset[Capability] = field(default_factory=frozenset)

    def allows(self, capability: Capability) -> bool:
        return capability in self.granted

    def require(self, capability: Capability) -> None:
        if not self.allows(capability):
            raise ApiError(ErrorCode.FORBIDDEN, f"missing capability: {capability.value}")

    @classmethod
    def full(cls) -> CapabilitySet:
        return cls(granted=frozenset(Capability))
