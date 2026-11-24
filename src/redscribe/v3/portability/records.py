"""Portable entity snapshots built on the universal V3 entity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.entities.types import EntityId, EntityRecord, EntityStatus, LinkKind
from redscribe.v3.entities.types import EntityLink as V3EntityLink
from redscribe.v3.portability.canonical import digest_entity, digest_value
from redscribe.v3.portability.errors import BundleError
from redscribe.v3.portability.vectors import VersionVector

ENTITY_FIELDS: tuple[str, ...] = (
    "title",
    "summary",
    "status",
    "tags",
    "body",
    "deleted",
)


@dataclass(frozen=True, slots=True)
class PortableEntity:
    """A versioned, portable snapshot of a universal entity record.

    This is a transport DTO around :class:`EntityRecord`; it deliberately does
    not redefine entity identity, status, or links.
    """

    record: EntityRecord
    vector: VersionVector
    body: str = ""
    deleted: bool = False

    @property
    def ref(self) -> str:
        """Canonical entity reference used as the merge key."""
        return str(self.record.entity_id)

    @property
    def family(self) -> str:
        """Entity family (kind) used for grouped three-way merges."""
        return self.record.entity_id.kind.value

    @property
    def title(self) -> str:
        """Display title of the underlying record."""
        return self.record.title

    @property
    def version(self) -> int:
        """Record version counter."""
        return self.record.version

    def field_values(self) -> dict[str, Any]:
        """Return the comparable merge fields of the snapshot."""
        return {
            "title": self.record.title,
            "summary": self.record.summary,
            "status": self.record.status.value,
            "tags": list(self.record.tags),
            "body": self.body,
            "deleted": self.deleted,
        }

    def fingerprint(self) -> str:
        """Return a stable digest over the full snapshot."""
        return digest_entity(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "record": self.record.as_dict(),
            "vector": self.vector.as_dict(),
            "body": self.body,
            "deleted": self.deleted,
        }

    def apply_fields(self, values: dict[str, Any], *, vector: VersionVector) -> PortableEntity:
        """Return a copy with selected merge fields replaced."""
        status_value = values.get("status", self.record.status.value)
        try:
            status = EntityStatus(str(status_value))
        except ValueError as error:
            raise BundleError(f"Unknown entity status: {status_value}") from error
        tags_value = values.get("tags", list(self.record.tags))
        if not isinstance(tags_value, (list, tuple)):
            raise BundleError("Entity tags must be a list")
        updated = EntityRecord(
            entity_id=self.record.entity_id,
            title=str(values.get("title", self.record.title)),
            summary=str(values.get("summary", self.record.summary)),
            status=status,
            tags=tuple(str(tag) for tag in tags_value),
            owner=self.record.owner,
            created_at=self.record.created_at,
            updated_at=self.record.updated_at,
            version=self.record.version + 1,
            metadata=dict(self.record.metadata),
        )
        return PortableEntity(
            record=updated,
            vector=vector,
            body=str(values.get("body", self.body)),
            deleted=bool(values.get("deleted", self.deleted)),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PortableEntity:
        """Rebuild a portable entity from its serialized form."""
        try:
            raw_record = payload["record"]
            entity_id = EntityId.parse(str(raw_record["entity_id"]))
            status = EntityStatus(str(raw_record.get("status", EntityStatus.DRAFT.value)))
            record = EntityRecord(
                entity_id=entity_id,
                title=str(raw_record["title"]),
                status=status,
                tags=tuple(str(tag) for tag in raw_record.get("tags", ())),
                summary=str(raw_record.get("summary", "")),
                owner=str(raw_record.get("owner", "")),
                created_at=float(raw_record.get("created_at", 0.0)),
                updated_at=float(raw_record.get("updated_at", 0.0)),
                version=int(raw_record.get("version", 1)),
                metadata=dict(raw_record.get("metadata", {})),
            )
            return cls(
                record=record,
                vector=VersionVector.from_dict(payload.get("vector")),
                body=str(payload.get("body", "")),
                deleted=bool(payload.get("deleted", False)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BundleError("Malformed portable entity") from error


def link_as_dict(link: V3EntityLink) -> dict[str, Any]:
    """Serialize a universal entity link for a bundle."""
    return link.as_dict()


def link_from_dict(payload: dict[str, Any]) -> V3EntityLink:
    """Rebuild a universal entity link from bundle data."""
    try:
        return V3EntityLink(
            source=EntityId.parse(str(payload["source"])),
            target=EntityId.parse(str(payload["target"])),
            kind=LinkKind.parse(str(payload.get("kind", LinkKind.RELATES.value))),
            label=str(payload.get("label", "")),
            weight=float(payload.get("weight", 1.0)),
            metadata=dict(payload.get("metadata", {})),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BundleError("Malformed portable link") from error


def index_entities(entities: tuple[PortableEntity, ...]) -> dict[str, PortableEntity]:
    """Index portable entities by canonical reference."""
    return {entity.ref: entity for entity in entities}


def stable_entities(entities: tuple[PortableEntity, ...]) -> tuple[PortableEntity, ...]:
    """Return entities sorted by canonical reference."""
    return tuple(sorted(entities, key=lambda entity: entity.ref))


def stable_links(links: tuple[V3EntityLink, ...]) -> tuple[V3EntityLink, ...]:
    """Return links sorted by their universal identity key."""
    return tuple(sorted(links, key=lambda link: link.key))


def link_payload(link: V3EntityLink) -> str:
    """Return a short digest label for a link, useful in conflict views."""
    return digest_value(link.as_dict())[:12]
