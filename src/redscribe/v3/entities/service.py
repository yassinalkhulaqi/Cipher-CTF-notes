"""Application service for universal entity records and links."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.ids import new_id
from redscribe.v3.entities.links import DuplicateLinkError, LinkGraph
from redscribe.v3.entities.types import (
    EntityId,
    EntityKind,
    EntityLink,
    EntityRecord,
    EntityRef,
    EntityStatus,
    LinkKind,
)

ChangeCallback = Callable[[str, EntityRecord], None]


class EntityNotFoundError(KeyError):
    """Raised when an entity id is unknown."""


class EntityService:
    """Store and query entity records with universal links.

    The service is deliberately storage-agnostic: callers persist snapshots with
    their own repository. That keeps every V3 feature independent of SQLite
    while still sharing one identity and relationship model.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._records: dict[str, EntityRecord] = {}
        self._graph = LinkGraph()
        self._listeners: list[ChangeCallback] = []

    def subscribe(self, callback: ChangeCallback) -> None:
        """Register a change listener."""
        self._listeners.append(callback)

    def _notify(self, action: str, record: EntityRecord) -> None:
        """Notify listeners about a change."""
        for callback in tuple(self._listeners):
            callback(action, record)

    def create(
        self,
        kind: EntityKind | str,
        *,
        title: str,
        summary: str = "",
        tags: tuple[str, ...] = (),
        owner: str = "",
        value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EntityRecord:
        """Create and store a new entity record."""
        entity_id = (
            new_id(kind, prefix=title)
            if value is None
            else EntityId(
                kind if isinstance(kind, EntityKind) else EntityKind.parse(kind),
                value,
            )
        )
        timestamp = self._clock.now_timestamp()
        record = EntityRecord(
            entity_id=entity_id,
            title=title,
            summary=summary,
            tags=tags,
            owner=owner,
            created_at=timestamp,
            updated_at=timestamp,
            metadata=dict(metadata or {}),
        )
        self._records[str(entity_id)] = record
        self._notify("created", record)
        return record

    def get(self, entity_id: EntityId) -> EntityRecord:
        """Return a record or raise :class:`EntityNotFoundError`."""
        record = self._records.get(str(entity_id))
        if record is None:
            raise EntityNotFoundError(f"Unknown entity: {entity_id}")
        return record

    def find(self, raw: str) -> EntityRecord | None:
        """Look up a record by its canonical string form."""
        return self._records.get(raw)

    def update(
        self,
        entity_id: EntityId,
        *,
        title: str | None = None,
        summary: str | None = None,
        status: EntityStatus | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> EntityRecord:
        """Update a record and return the new immutable version."""
        existing = self.get(entity_id)
        updated = existing.with_updates(
            title=title,
            summary=summary,
            status=status,
            tags=tags,
            timestamp=self._clock.now_timestamp(),
        )
        self._records[str(entity_id)] = updated
        self._notify("updated", updated)
        return updated

    def remove(self, entity_id: EntityId) -> None:
        """Mark an entity deleted without dropping its links."""
        record = self.get(entity_id)
        archived = record.with_updates(
            status=EntityStatus.DELETED,
            timestamp=self._clock.now_timestamp(),
        )
        self._records[str(entity_id)] = archived
        self._notify("deleted", archived)

    def link(
        self,
        source: EntityId,
        target: EntityId,
        *,
        kind: LinkKind = LinkKind.RELATES,
        label: str = "",
        weight: float = 1.0,
    ) -> EntityLink:
        """Create a typed link after validating both endpoints."""
        self.get(source)
        self.get(target)
        link = EntityLink(source=source, target=target, kind=kind, label=label, weight=weight)
        self._graph.add(link)
        return link

    def unlink(self, link: EntityLink) -> bool:
        """Remove a typed link if present."""
        return self._graph.remove(link)

    def graph(self) -> LinkGraph:
        """Return the shared link graph."""
        return self._graph

    def refs(self, kind: EntityKind | None = None) -> tuple[EntityRef, ...]:
        """Return references to all records, optionally filtered by kind."""
        records = (
            record
            for record in self._records.values()
            if kind is None or record.entity_id.kind is kind
        )
        return tuple(
            EntityRef(record.entity_id, record.title)
            for record in sorted(records, key=lambda item: str(item.entity_id))
        )

    def search(self, text: str, *, kind: EntityKind | None = None) -> tuple[EntityRecord, ...]:
        """Case-insensitive substring search over titles and summaries."""
        needle = text.strip().casefold()
        if not needle:
            return ()
        return tuple(
            record
            for record in self._records.values()
            if (kind is None or record.entity_id.kind is kind)
            and (
                needle in record.title.casefold()
                or needle in record.summary.casefold()
                or any(needle in tag.casefold() for tag in record.tags)
            )
        )

    def tag_counts(self) -> dict[str, int]:
        """Return case-folded tag usage counts."""
        counter: Counter[str] = Counter()
        for record in self._records.values():
            counter.update(record.tag_set)
        return dict(sorted(counter.items()))

    def stats(self) -> dict[str, int]:
        """Return a summary of the current store."""
        by_kind = Counter(record.entity_id.kind.value for record in self._records.values())
        return {
            "entities": len(self._records),
            "links": len(self._graph),
            **{f"kind_{key}": value for key, value in by_kind.items()},
        }

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot of records and links."""
        return {
            "records": [record.as_dict() for record in self._records.values()],
            "links": [link.as_dict() for link in self._graph.links()],
        }

    @staticmethod
    def duplicate_error() -> type[DuplicateLinkError]:
        """Expose the link error type to callers without importing internals."""
        return DuplicateLinkError
