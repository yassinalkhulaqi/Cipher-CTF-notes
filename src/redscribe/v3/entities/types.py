"""Universal entity identity and reference contracts for RedScribe V3.

Every feature in V3 speaks in terms of :class:`EntityRef` values rather than
feature-specific foreign keys. This is the seam that lets a finding reference a
note, an evidence record, or a report section without importing those features.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

ENTITY_NOTE = "note"
ENTITY_FOLDER = "folder"
ENTITY_TARGET = "target"
ENTITY_FINDING = "finding"
ENTITY_EVIDENCE = "evidence"
ENTITY_PLAYBOOK = "playbook"
ENTITY_RUN = "run"
ENTITY_REPORT = "report"
ENTITY_SECTION = "section"
ENTITY_ACTIVITY = "activity"
ENTITY_EXTENSION = "extension"
ENTITY_SNIPPET = "snippet"

ENTITY_KINDS: tuple[str, ...] = (
    ENTITY_NOTE,
    ENTITY_FOLDER,
    ENTITY_TARGET,
    ENTITY_FINDING,
    ENTITY_EVIDENCE,
    ENTITY_PLAYBOOK,
    ENTITY_RUN,
    ENTITY_REPORT,
    ENTITY_SECTION,
    ENTITY_ACTIVITY,
    ENTITY_EXTENSION,
    ENTITY_SNIPPET,
)


class EntityKind(str, Enum):
    """Stable kind discriminator used by the universal resolver and graph."""

    NOTE = ENTITY_NOTE
    FOLDER = ENTITY_FOLDER
    TARGET = ENTITY_TARGET
    FINDING = ENTITY_FINDING
    EVIDENCE = ENTITY_EVIDENCE
    PLAYBOOK = ENTITY_PLAYBOOK
    RUN = ENTITY_RUN
    REPORT = ENTITY_REPORT
    SECTION = ENTITY_SECTION
    ACTIVITY = ENTITY_ACTIVITY
    EXTENSION = ENTITY_EXTENSION
    SNIPPET = ENTITY_SNIPPET

    @classmethod
    def parse(cls, value: str) -> EntityKind:
        """Parse a kind string with a stable error message."""
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unknown entity kind: {value}")


class EntityStatus(str, Enum):
    """Lifecycle state shared by all first-class entities."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class EntityId:
    """A typed, validated identifier for any first-class entity."""

    kind: EntityKind
    value: str

    def __post_init__(self) -> None:
        if not self.value or len(self.value) > 128:
            raise ValueError("Entity id value must be 1-128 characters")
        if any(char.isspace() for char in self.value):
            raise ValueError("Entity id value cannot contain whitespace")

    @classmethod
    def parse(cls, raw: str) -> EntityId:
        """Parse a ``kind:value`` identifier."""
        if ":" not in raw:
            raise ValueError(f"Invalid entity id: {raw}")
        kind_text, value = raw.split(":", 1)
        return cls(EntityKind.parse(kind_text), value)

    def __str__(self) -> str:
        """Render the stable wire form."""
        return f"{self.kind.value}:{self.value}"

    def same_kind(self, other: EntityId) -> bool:
        """Return whether two ids share a kind."""
        return self.kind is other.kind

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation."""
        return {"kind": self.kind.value, "value": self.value, "ref": str(self)}


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A lightweight pointer to an entity, with an optional human label."""

    entity_id: EntityId
    label: str = ""

    @classmethod
    def of(cls, kind: EntityKind | str, value: str, label: str = "") -> EntityRef:
        """Build a reference from a kind and a raw value."""
        parsed = kind if isinstance(kind, EntityKind) else EntityKind.parse(kind)
        return cls(EntityId(parsed, value), label)

    @property
    def kind(self) -> EntityKind:
        """Kind of the referenced entity."""
        return self.entity_id.kind

    def __str__(self) -> str:
        """Render the canonical reference string."""
        return str(self.entity_id)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        payload: dict[str, Any] = self.entity_id.as_dict()
        payload["label"] = self.label
        return payload


LINK_CONTAINS = "contains"
LINK_RELATES = "relates"
LINK_EVIDENCES = "evidences"
LINK_DERIVES = "derives"
LINK_REFERENCES = "references"
LINK_DUPLICATES = "duplicates"
LINK_SUPERSEDES = "supersedes"

LINK_KINDS: tuple[str, ...] = (
    LINK_CONTAINS,
    LINK_RELATES,
    LINK_EVIDENCES,
    LINK_DERIVES,
    LINK_REFERENCES,
    LINK_DUPLICATES,
    LINK_SUPERSEDES,
)


class LinkKind(str, Enum):
    """Semantic relationship between two entities."""

    CONTAINS = LINK_CONTAINS
    RELATES = LINK_RELATES
    EVIDENCES = LINK_EVIDENCES
    DERIVES = LINK_DERIVES
    REFERENCES = LINK_REFERENCES
    DUPLICATES = LINK_DUPLICATES
    SUPERSEDES = LINK_SUPERSEDES

    @classmethod
    def parse(cls, value: str) -> LinkKind:
        """Parse a link kind string."""
        normalized = value.strip().casefold()
        for link in cls:
            if link.value == normalized:
                return link
        raise ValueError(f"Unknown link kind: {value}")

    @property
    def is_directed(self) -> bool:
        """Whether the relationship has a meaningful direction."""
        return self not in (LinkKind.RELATES, LinkKind.DUPLICATES)


@dataclass(frozen=True, slots=True)
class EntityLink:
    """A typed, optional-labeled edge between two entities."""

    source: EntityId
    target: EntityId
    kind: LinkKind = LinkKind.RELATES
    label: str = ""
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.weight < 0 or self.weight > 1:
            raise ValueError("Link weight must be between 0 and 1")

    @property
    def key(self) -> tuple[str, str, str]:
        """Identity tuple used for deduplication."""
        return (str(self.source), str(self.target), self.kind.value)

    def reversed(self) -> EntityLink:
        """Return the same link with source and target swapped."""
        return EntityLink(
            source=self.target,
            target=self.source,
            kind=self.kind,
            label=self.label,
            weight=self.weight,
            metadata=dict(self.metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": str(self.source),
            "target": str(self.target),
            "kind": self.kind.value,
            "label": self.label,
            "weight": self.weight,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """The canonical record stored for a first-class entity."""

    entity_id: EntityId
    title: str
    status: EntityStatus = EntityStatus.DRAFT
    tags: tuple[str, ...] = ()
    summary: str = ""
    owner: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Entity title cannot be blank")
        if self.version < 1:
            raise ValueError("Entity version must be at least 1")

    @property
    def tag_set(self) -> frozenset[str]:
        """Case-folded tag set for fast comparisons."""
        return frozenset(tag.casefold() for tag in self.tags)

    def with_updates(
        self,
        *,
        title: str | None = None,
        summary: str | None = None,
        status: EntityStatus | None = None,
        tags: tuple[str, ...] | None = None,
        timestamp: float | None = None,
    ) -> EntityRecord:
        """Return a new record with updated fields and an incremented version."""
        return EntityRecord(
            entity_id=self.entity_id,
            title=self.title if title is None else title,
            summary=self.summary if summary is None else summary,
            status=self.status if status is None else status,
            tags=self.tags if tags is None else tags,
            owner=self.owner,
            created_at=self.created_at,
            updated_at=self.updated_at if timestamp is None else timestamp,
            version=self.version + 1,
            metadata=dict(self.metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "entity_id": str(self.entity_id),
            "kind": self.entity_id.kind.value,
            "title": self.title,
            "status": self.status.value,
            "tags": list(self.tags),
            "summary": self.summary,
            "owner": self.owner,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "metadata": dict(self.metadata),
        }
