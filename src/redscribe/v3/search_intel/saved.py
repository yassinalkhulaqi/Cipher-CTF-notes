"""In-memory persistence and validation for saved searches and facet sets."""

from __future__ import annotations

import builtins
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.search_intel.types import (
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_TAG_LENGTH,
    SavedFacetSet,
    SavedSearch,
)

MAX_SAVED_ITEMS = 200


def validate_saved_search(name: str, query: str) -> tuple[str, str]:
    """Validate and normalize a saved search name and expression."""
    clean_name = " ".join(str(name).split())
    clean_query = str(query).strip()
    if not clean_name:
        raise ValueError("Saved search name is required")
    if len(clean_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Saved search name exceeds {MAX_NAME_LENGTH} characters")
    if not clean_query:
        raise ValueError("Saved search query is required")
    if len(clean_query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Saved search query exceeds {MAX_QUERY_LENGTH} characters")
    return clean_name, clean_query


def validate_facet_set(name: str, fields: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    """Validate a facet set name and field list."""
    clean_name = " ".join(str(name).split())
    if not clean_name:
        raise ValueError("Facet set name is required")
    if len(clean_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Facet set name exceeds {MAX_NAME_LENGTH} characters")
    if not fields:
        raise ValueError("Facet set needs at least one field")
    cleaned = tuple(dict.fromkeys(" ".join(str(field).split()).casefold() for field in fields))
    cleaned = tuple(field for field in cleaned if field)
    if not cleaned:
        raise ValueError("Facet set needs at least one field")
    return clean_name, cleaned


def normalize_tags(values: Iterable[str] | str) -> tuple[str, ...]:
    """Normalize tags from a list or comma-separated string."""
    raw = values.split(",") if isinstance(values, str) else list(values)
    result: list[str] = []
    for value in raw:
        tag = " ".join(str(value).split())
        if not tag or len(tag) > MAX_TAG_LENGTH:
            continue
        if tag.casefold() not in {item.casefold() for item in result}:
            result.append(tag)
    return tuple(result[:12])


def make_item_id(prefix: str, *parts: str) -> str:
    """Build a deterministic id from stable content."""
    digest = hashlib.blake2b(
        "\x1f".join(parts).casefold().encode("utf-8"), digest_size=8
    ).hexdigest()
    return f"{prefix}_{digest[:12]}"


def sort_searches(items: Iterable[SavedSearch]) -> tuple[SavedSearch, ...]:
    """Order saved searches with pinned and frequently used items first."""
    return tuple(
        sorted(
            items,
            key=lambda item: (
                not item.pinned,
                -item.use_count,
                -item.updated_at,
                item.name.casefold(),
                item.id,
            ),
        )
    )


class SavedSearchStore:
    """CRUD store for named query expressions."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._items: dict[str, SavedSearch] = {}

    def create(
        self,
        name: str,
        query: str,
        *,
        description: str = "",
        tags: Iterable[str] | str = (),
        pinned: bool = False,
        saved_id: str | None = None,
    ) -> SavedSearch:
        """Create a saved search, rejecting duplicates by id."""
        clean_name, clean_query = validate_saved_search(name, query)
        item_id = saved_id or make_item_id("q", clean_name, clean_query)
        if item_id in self._items:
            raise ValueError(f"Saved search already exists: {item_id}")
        timestamp = self._clock.now_timestamp()
        item = SavedSearch(
            id=item_id,
            name=clean_name,
            query=clean_query,
            description=str(description).strip()[:MAX_DESCRIPTION_LENGTH],
            tags=normalize_tags(tags),
            pinned=pinned,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._items[item_id] = item
        return item

    def get(self, saved_id: str) -> SavedSearch | None:
        """Look up a saved search by id."""
        return self._items.get(saved_id)

    def list(
        self,
        *,
        search: str = "",
        tag: str = "",
        limit: int = 50,
    ) -> tuple[SavedSearch, ...]:
        """List saved searches with optional text and tag filters."""
        needle = search.strip().casefold()
        tag_needle = tag.strip().casefold()
        items = [
            item
            for item in self._items.values()
            if (not needle or needle in f"{item.name} {item.query} {item.description}".casefold())
            and (not tag_needle or tag_needle in {value.casefold() for value in item.tags})
        ]
        return sort_searches(items)[: max(0, limit)]

    def update(
        self,
        saved_id: str,
        *,
        name: str | None = None,
        query: str | None = None,
        description: str | None = None,
        tags: Iterable[str] | str | None = None,
        pinned: bool | None = None,
    ) -> SavedSearch:
        """Update a saved search and bump its updated timestamp."""
        existing = self.get(saved_id)
        if existing is None:
            raise KeyError(saved_id)
        clean_name = existing.name if name is None else " ".join(str(name).split())
        clean_query = existing.query if query is None else str(query).strip()
        clean_name, clean_query = validate_saved_search(clean_name, clean_query)
        updated = SavedSearch(
            id=existing.id,
            name=clean_name,
            query=clean_query,
            description=(
                existing.description
                if description is None
                else str(description).strip()[:MAX_DESCRIPTION_LENGTH]
            ),
            tags=existing.tags if tags is None else normalize_tags(tags),
            pinned=existing.pinned if pinned is None else pinned,
            use_count=existing.use_count,
            created_at=existing.created_at,
            updated_at=self._clock.now_timestamp(),
        )
        self._items[saved_id] = updated
        return updated

    def touch(self, saved_id: str) -> SavedSearch | None:
        """Increment the usage counter for a saved search."""
        existing = self.get(saved_id)
        if existing is None:
            return None
        updated = SavedSearch(
            id=existing.id,
            name=existing.name,
            query=existing.query,
            description=existing.description,
            tags=existing.tags,
            pinned=existing.pinned,
            use_count=existing.use_count + 1,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
        self._items[saved_id] = updated
        return updated

    def delete(self, saved_id: str) -> bool:
        """Delete a saved search, returning whether it existed."""
        return self._items.pop(saved_id, None) is not None

    def to_items(self) -> tuple[SavedSearch, ...]:
        """Return all saved searches in stable order."""
        return sort_searches(self._items.values())

    def to_dict(self) -> builtins.list[dict[str, Any]]:
        """Serialize the store."""
        return [item.as_dict() for item in self.to_items()[:MAX_SAVED_ITEMS]]

    def load(self, payload: Sequence[Any]) -> int:
        """Replace store contents from a serialized payload."""
        self._items.clear()
        return self.import_items(payload, replace=True)

    def import_items(
        self,
        payload: Sequence[Any],
        *,
        replace: bool = False,
    ) -> int:
        """Import saved searches, skipping malformed entries."""
        if replace:
            self._items.clear()
        imported = 0
        for raw in payload:
            if not isinstance(raw, Mapping):
                continue
            try:
                name, query = validate_saved_search(
                    str(raw.get("name", "")), str(raw.get("query", ""))
                )
                item_id = str(raw.get("id", "")) or make_item_id("q", name, query)
                item = SavedSearch(
                    id=item_id,
                    name=name,
                    query=query,
                    description=str(raw.get("description", ""))[:MAX_DESCRIPTION_LENGTH],
                    tags=normalize_tags(raw.get("tags", ())),
                    pinned=bool(raw.get("pinned", False)),
                    use_count=max(0, int(raw.get("use_count", 0))),
                    created_at=float(raw.get("created_at", 0.0)),
                    updated_at=float(raw.get("updated_at", 0.0)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._items[item.id] = item
            imported += 1
            if imported >= MAX_SAVED_ITEMS:
                break
        return imported

    def __len__(self) -> int:
        return len(self._items)


class SavedFacetSetStore:
    """CRUD store for named facet selections."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._items: dict[str, SavedFacetSet] = {}

    def create(
        self,
        name: str,
        fields: Sequence[str],
        *,
        description: str = "",
        set_id: str | None = None,
    ) -> SavedFacetSet:
        """Create a saved facet set."""
        clean_name, clean_fields = validate_facet_set(name, fields)
        item_id = set_id or make_item_id("f", clean_name, *clean_fields)
        if item_id in self._items:
            raise ValueError(f"Facet set already exists: {item_id}")
        item = SavedFacetSet(
            id=item_id,
            name=clean_name,
            fields=clean_fields,
            description=str(description).strip()[:MAX_DESCRIPTION_LENGTH],
            created_at=self._clock.now_timestamp(),
        )
        self._items[item_id] = item
        return item

    def get(self, set_id: str) -> SavedFacetSet | None:
        """Look up a facet set by id."""
        return self._items.get(set_id)

    def list(self, *, limit: int = 50) -> tuple[SavedFacetSet, ...]:
        """List facet sets in stable order."""
        items = sorted(
            self._items.values(),
            key=lambda item: (item.name.casefold(), item.id),
        )
        return tuple(items[: max(0, limit)])

    def delete(self, set_id: str) -> bool:
        """Delete a facet set."""
        return self._items.pop(set_id, None) is not None

    def to_dict(self) -> builtins.list[dict[str, Any]]:
        """Serialize the store."""
        return [item.as_dict() for item in self.list(limit=MAX_SAVED_ITEMS)]

    def load(self, payload: Sequence[Any]) -> int:
        """Replace store contents from a serialized payload."""
        self._items.clear()
        imported = 0
        for raw in payload:
            if not isinstance(raw, Mapping):
                continue
            try:
                name, fields = validate_facet_set(
                    str(raw.get("name", "")),
                    tuple(str(item) for item in raw.get("fields", ())),
                )
                item_id = str(raw.get("id", "")) or make_item_id("f", name, *fields)
                item = SavedFacetSet(
                    id=item_id,
                    name=name,
                    fields=fields,
                    description=str(raw.get("description", ""))[:MAX_DESCRIPTION_LENGTH],
                    created_at=float(raw.get("created_at", 0.0)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._items[item.id] = item
            imported += 1
        return imported

    def __len__(self) -> int:
        return len(self._items)
