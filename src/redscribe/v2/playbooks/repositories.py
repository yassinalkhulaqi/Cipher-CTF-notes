"""In-memory repositories with stable keys and snapshot support."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from redscribe.v2.playbooks.errors import (
    DuplicateKeyError,
    NotFoundError,
    RepositoryError,
    UnknownSnippetError,
    UnknownTemplateError,
)
from redscribe.v2.playbooks.types import (
    Playbook,
    RunState,
    SnippetRecord,
    TemplateRecord,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RepositoryStats:
    """Summary of one repository."""

    name: str
    total: int
    keys: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "total": self.total, "keys": list(self.keys)}


class Repository(Generic[T]):
    """A key-indexed collection with deterministic ordering."""

    def __init__(
        self,
        name: str,
        key_fn: Callable[[T], str],
        id_fn: Callable[[T], int],
    ) -> None:
        self.name = name
        self._key_fn = key_fn
        self._id_fn = id_fn
        self._items: dict[str, T] = {}

    def __len__(self) -> int:
        return len(self._items)

    @property
    def items(self) -> tuple[T, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def keys(self) -> tuple[str, ...]:
        """Return all stored keys."""
        return tuple(sorted(self._items))

    def key_of(self, item: T) -> str:
        """Return the normalized key for an item."""
        return self._key_fn(item).strip().casefold()

    def id_of(self, item: T) -> int:
        """Return the numeric id for an item."""
        return self._id_fn(item)

    def next_id(self) -> int:
        """Return the next free numeric id."""
        return max((self._id_fn(item) for item in self._items.values()), default=0) + 1

    def get(self, key: str) -> T:
        """Return an item by key or raise."""
        item = self.find(key)
        if item is None:
            raise NotFoundError(f"{self.name} not found: {key}", details={"key": key})
        return item

    def find(self, key: str) -> T | None:
        """Return an item by key or ``None``."""
        return self._items.get(str(key).strip().casefold())

    def contains(self, key: str) -> bool:
        """Return whether a key exists."""
        return str(key).strip().casefold() in self._items

    def add(self, item: T, *, assign_id: bool = False, validate: bool = True) -> T:
        """Insert one item, optionally assigning a fresh id."""
        normalized = self._with_id(item, self.next_id()) if assign_id else item
        key = self.key_of(normalized)
        if not key:
            raise RepositoryError(f"{self.name} key cannot be empty")
        if key in self._items:
            raise DuplicateKeyError(f"{self.name} already exists: {key}", details={"key": key})
        if validate:
            self.validate(normalized)
        self._items[key] = normalized
        return normalized

    def put(self, item: T, *, validate: bool = True) -> T:
        """Insert or replace one item."""
        key = self.key_of(item)
        if not key:
            raise RepositoryError(f"{self.name} key cannot be empty")
        if validate:
            self.validate(item)
        self._items[key] = item
        return item

    def update(self, key: str, item: T) -> T:
        """Replace an existing item while preserving its key."""
        normalized_key = str(key).strip().casefold()
        if normalized_key not in self._items:
            raise RepositoryError(f"{self.name} not found: {key}", details={"key": key})
        updated = self._with_key(item, normalized_key)
        self.validate(updated)
        self._items[normalized_key] = updated
        return updated

    def remove(self, key: str) -> T:
        """Remove and return an item."""
        normalized_key = str(key).strip().casefold()
        if normalized_key not in self._items:
            raise RepositoryError(f"{self.name} not found: {key}", details={"key": key})
        return self._items.pop(normalized_key)

    def replace_all(self, items: list[T], *, validate: bool = True) -> None:
        """Replace the whole repository atomically."""
        staged: dict[str, T] = {}
        for item in items:
            key = self.key_of(item)
            if not key or key in staged:
                raise RepositoryError(f"Duplicate or empty {self.name} key: {key}")
            if validate:
                self.validate(item)
            staged[key] = item
        self._items = staged

    def filter(self, predicate: Callable[[T], bool]) -> list[T]:
        """Return all items matching a predicate."""
        return [item for item in self.items if predicate(item)]

    def search(self, query: str = "", *, tags: tuple[str, ...] = (), limit: int = 50) -> list[T]:
        """Rank items by textual relevance and tag overlap."""
        needle = query.strip().casefold()
        wanted = {tag.strip().casefold() for tag in tags if tag.strip()}
        scored: list[tuple[int, T]] = []
        for item in self.items:
            data = self.as_dict(item)
            haystack = self.search_text(item, data).casefold()
            record_tags = self.tags_of(item)
            score = 0
            if needle:
                if self.key_of(item).startswith(needle):
                    score += 6
                if needle in haystack:
                    score += 2
            if wanted:
                overlap = wanted.intersection({tag.casefold() for tag in record_tags})
                if not overlap:
                    continue
                score += 2 * len(overlap)
            if (needle or wanted) and score == 0:
                continue
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], self.key_of(pair[1])))
        return [item for _, item in scored[:limit]]

    def stats(self) -> RepositoryStats:
        """Return repository statistics."""
        return RepositoryStats(self.name, len(self._items), self.keys())

    def snapshot(self) -> list[dict[str, Any]]:
        """Serialize all items."""
        return [self.as_dict(item) for item in self.items]

    def restore(self, payload: Any, parser: Callable[[Any], T]) -> None:
        """Restore items from serialized snapshots."""
        if not isinstance(payload, list):
            raise RepositoryError(f"{self.name} snapshot must be a list")
        self.replace_all([parser(item) for item in payload], validate=False)

    def validate(self, item: T) -> None:
        """Hook for subclass validation."""
        del item

    def as_dict(self, item: T) -> dict[str, Any]:
        """Hook for subclass serialization."""
        return {"key": self.key_of(item), "id": self._id_fn(item)}

    def search_text(self, item: T, data: dict[str, Any]) -> str:
        """Hook for subclass search indexing."""
        return " ".join(str(value) for value in data.values() if isinstance(value, str))

    def tags_of(self, item: T) -> tuple[str, ...]:
        """Hook for subclass tag indexing."""
        del item
        return ()

    def _with_id(self, item: T, new_id: int) -> T:
        return self._with(item, id=new_id)

    def _with_key(self, item: T, new_key: str) -> T:
        return self._with(item, key=new_key)

    def _with(self, item: T, **changes: Any) -> T:
        method = getattr(item, "with_changes", None)
        if not callable(method):
            raise RepositoryError(f"{self.name} items must support with_changes")
        updater: Callable[..., T] = method
        return updater(**changes)


class PlaybookRepository(Repository[Playbook]):
    """Repository for versioned playbooks."""

    def __init__(self) -> None:
        super().__init__("playbook", lambda item: item.key, lambda item: item.id)

    def validate(self, item: Playbook) -> None:
        from redscribe.v2.playbooks.validation import ensure_valid, validate_playbook

        ensure_valid(validate_playbook(item), "Playbook validation failed")

    def as_dict(self, item: Playbook) -> dict[str, Any]:
        return item.as_dict()

    def tags_of(self, item: Playbook) -> tuple[str, ...]:
        return tuple(item.tags)


class SnippetRepository(Repository[SnippetRecord]):
    """Repository for snippet records."""

    def __init__(self) -> None:
        super().__init__("snippet", lambda item: item.key, lambda item: item.id)

    def get(self, key: str) -> SnippetRecord:
        try:
            return super().get(key)
        except NotFoundError as exc:
            raise UnknownSnippetError(str(exc), details=exc.details) from exc

    def validate(self, item: SnippetRecord) -> None:
        from redscribe.v2.playbooks.validation import ensure_valid, validate_snippet

        ensure_valid(validate_snippet(item), "Snippet validation failed")

    def as_dict(self, item: SnippetRecord) -> dict[str, Any]:
        return item.as_dict()

    def tags_of(self, item: SnippetRecord) -> tuple[str, ...]:
        return item.tags


class TemplateRepository(Repository[TemplateRecord]):
    """Repository for template records."""

    def __init__(self) -> None:
        super().__init__("template", lambda item: item.key, lambda item: item.id)

    def get(self, key: str) -> TemplateRecord:
        try:
            return super().get(key)
        except NotFoundError as exc:
            raise UnknownTemplateError(str(exc), details=exc.details) from exc

    def as_dict(self, item: TemplateRecord) -> dict[str, Any]:
        return item.as_dict()

    def tags_of(self, item: TemplateRecord) -> tuple[str, ...]:
        return item.tags


class RunRepository(Repository[RunState]):
    """Repository for run snapshots keyed by numeric id."""

    def __init__(self) -> None:
        super().__init__("run", lambda item: str(item.id), lambda item: item.id)

    def as_dict(self, item: RunState) -> dict[str, Any]:
        return item.as_dict()

    def next_id(self) -> int:
        return max((item.id for item in self._items.values()), default=0) + 1

    def by_playbook(self, key: str) -> list[RunState]:
        """Return runs for one playbook, newest first."""
        return sorted(
            (item for item in self.items if item.playbook_key == key),
            key=lambda item: item.id,
            reverse=True,
        )
