"""In-memory repositories with JSON snapshot persistence for engagements."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Generic, TypeVar

from redscribe.v2.engagements.models import (
    Activity,
    Asset,
    AssetKind,
    Credential,
    Engagement,
    Entity,
    Finding,
    ScopeRule,
    Service,
    Target,
    TargetKind,
)

EntityT = TypeVar("EntityT", bound=Entity)

SNAPSHOT_VERSION = 1


class RepositoryError(ValueError):
    """Raised when a repository operation cannot be completed."""


class Repository(Generic[EntityT]):
    """Ordered, id-assigned storage for one entity type."""

    def __init__(self, name: str, model_type: type[EntityT]) -> None:
        self.name = name
        self.model_type = model_type
        self._items: dict[int, EntityT] = {}
        self._next_id = 1

    @property
    def next_id(self) -> int:
        return self._next_id

    def all(self) -> list[EntityT]:
        """Return all stored entities ordered by id."""
        return [self._items[key] for key in sorted(self._items)]

    def get(self, entity_id: int) -> EntityT | None:
        """Return one entity by id."""
        return self._items.get(entity_id)

    def require(self, entity_id: int) -> EntityT:
        """Return one entity by id or raise."""
        entity = self._items.get(entity_id)
        if entity is None:
            raise RepositoryError(f"{self.name} {entity_id} does not exist")
        return entity

    def exists(self, entity_id: int) -> bool:
        """Return whether an id is present."""
        return entity_id in self._items

    def count(self) -> int:
        """Return the number of stored entities."""
        return len(self._items)

    def where(self, predicate: Callable[[EntityT], bool]) -> list[EntityT]:
        """Return entities matching a predicate."""
        return [entity for entity in self.all() if predicate(entity)]

    def first_where(self, predicate: Callable[[EntityT], bool]) -> EntityT | None:
        """Return the first entity matching a predicate."""
        for entity in self.all():
            if predicate(entity):
                return entity
        return None

    def add(self, entity: EntityT, *, entity_id: int | None = None) -> EntityT:
        """Store a new entity with an assigned id."""
        assigned = entity_id if entity_id is not None else self._next_id
        if assigned <= 0:
            raise RepositoryError("Entity ids must be positive")
        if assigned in self._items:
            raise RepositoryError(f"{self.name} {assigned} already exists")
        payload = entity.as_dict()
        payload["id"] = assigned
        stored = self.model_type.from_dict(payload)
        self._items[assigned] = stored
        if assigned >= self._next_id:
            self._next_id = assigned + 1
        return stored

    def update(self, entity_id: int, changes: Mapping[str, Any]) -> EntityT:
        """Replace an entity with field overrides applied."""
        existing = self.require(entity_id)
        payload = existing.as_dict()
        payload.update(changes)
        payload["id"] = entity_id
        stored = self.model_type.from_dict(payload)
        self._items[entity_id] = stored
        return stored

    def delete(self, entity_id: int) -> EntityT:
        """Remove and return an entity by id."""
        entity = self.require(entity_id)
        del self._items[entity_id]
        return entity

    def clear(self) -> None:
        """Remove all entities and reset the id sequence."""
        self._items.clear()
        self._next_id = 1

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a JSON-ready copy of all entities."""
        return [entity.as_dict() for entity in self.all()]

    def restore(self, values: Iterable[Mapping[str, Any]]) -> None:
        """Replace repository content from a serialized snapshot."""
        self.clear()
        for value in values:
            self.add(self.model_type.from_dict(value))

    def filter_by_engagement(self, engagement_id: int) -> list[EntityT]:
        """Return entities belonging to one engagement."""
        return self.where(lambda entity: entity.engagement_id == engagement_id)


class EngagementStore:
    """Aggregate root that owns every engagement repository."""

    def __init__(self) -> None:
        self.engagements = Repository("engagements", Engagement)
        self.scope_rules = Repository("scope_rules", ScopeRule)
        self.targets = Repository("targets", Target)
        self.assets = Repository("assets", Asset)
        self.services = Repository("services", Service)
        self.credentials = Repository("credentials", Credential)
        self.findings = Repository("findings", Finding)
        self.activities = Repository("activities", Activity)

    def repositories(self) -> dict[str, Repository[Any]]:
        """Return repositories keyed by their snapshot name."""
        return {
            "engagements": self.engagements,
            "scope_rules": self.scope_rules,
            "targets": self.targets,
            "assets": self.assets,
            "services": self.services,
            "credentials": self.credentials,
            "findings": self.findings,
            "activities": self.activities,
        }

    def clear(self) -> None:
        """Remove all data from every repository."""
        for repository in self.repositories().values():
            repository.clear()

    def snapshot(self) -> dict[str, Any]:
        """Serialize the complete store."""
        return {
            "version": SNAPSHOT_VERSION,
            "repositories": {
                name: repository.snapshot() for name, repository in self.repositories().items()
            },
        }

    def restore(self, data: Mapping[str, Any]) -> None:
        """Restore the complete store from a serialized snapshot."""
        version = data.get("version")
        if version != SNAPSHOT_VERSION:
            raise RepositoryError(f"Unsupported engagement snapshot version: {version!r}")
        raw_repositories = data.get("repositories")
        if not isinstance(raw_repositories, Mapping):
            raise RepositoryError("Engagement snapshot is missing repositories")
        repositories = self.repositories()
        for name, repository in repositories.items():
            values = raw_repositories.get(name, [])
            if not isinstance(values, list):
                raise RepositoryError(f"Invalid snapshot section: {name}")
            repository.restore([value for value in values if isinstance(value, Mapping)])

    def save(self, path: str | Path) -> None:
        """Write a canonical JSON snapshot to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self.snapshot(), ensure_ascii=False, indent=2, sort_keys=True)
        target.write_text(raw + "\n", encoding="utf-8")

    def load(self, path: str | Path) -> None:
        """Load a snapshot from disk, raising on malformed data."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryError(f"Cannot read engagement snapshot: {exc}") from exc
        if not isinstance(data, Mapping):
            raise RepositoryError("Engagement snapshot must be an object")
        self.restore(data)

    def stats(self) -> dict[str, int]:
        """Return entity counts for health checks."""
        return {name: repository.count() for name, repository in self.repositories().items()}


def seed_demo(store: EngagementStore) -> Engagement:
    """Populate a store with a small, deterministic demo engagement."""
    engagement = store.engagements.add(
        Engagement(
            key="demo-engagement",
            name="Demo Engagement",
            client="Example Corp",
            description="A demonstration engagement for the engagement core.",
            owner="redscribe",
            start_date="2026-01-05",
            end_date="2026-01-30",
            tags=["demo", "web"],
        )
    )
    target = store.targets.add(
        Target(
            engagement_id=engagement.id,
            value="demo.example.test",
            name="Demo Web",
            kind=TargetKind.DOMAIN,
        )
    )
    asset = store.assets.add(
        Asset(
            engagement_id=engagement.id,
            target_id=target.id,
            name="web-01",
            kind=AssetKind.SERVER,
            identifier="10.0.0.10",
        )
    )
    store.services.add(
        Service(
            engagement_id=engagement.id,
            target_id=target.id,
            asset_id=asset.id,
            name="https",
            port=443,
        )
    )
    store.findings.add(
        Finding(
            engagement_id=engagement.id,
            target_id=target.id,
            title="Demo finding",
            summary="A seeded finding used to exercise the dashboard.",
        )
    )
    return engagement
