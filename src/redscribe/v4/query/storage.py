"""In-memory persistence adapters for saved queries.

``QueryStore`` keeps a single authoritative id map plus a case-insensitive name
index. It is SQLite-ready in the sense that every mutation is expressed as an
explicit index update rather than relying on mutable shared objects, and the
JSON export/import round-trip is deterministic and sorted.
"""

from __future__ import annotations

import builtins
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace

from redscribe.v4.query.types import (
    DuplicateQueryNameError,
    QueryCapacityError,
    QueryError,
    QueryNotFoundError,
    SavedQuery,
    sequence_of,
)

STORE_VERSION = 1


def _name_key(name: str) -> str:
    return name.strip().casefold()


class QueryStore:
    """CRUD store with a case-insensitive unique-name index."""

    def __init__(self, capacity: int = 500) -> None:
        if capacity < 1:
            raise QueryError("capacity must be >= 1")
        self.capacity = capacity
        self._by_id: dict[str, SavedQuery] = {}
        self._by_name: dict[str, str] = {}
        self._order: builtins.list[str] = []

    def put(self, query: SavedQuery) -> SavedQuery:
        """Insert or update a query, enforcing uniqueness and capacity."""
        key = _name_key(query.name)
        owner = self._by_name.get(key)
        if owner is not None and owner != query.id:
            raise DuplicateQueryNameError(query.name)
        existing = self._by_id.get(query.id)
        is_new = existing is None
        if is_new and len(self._by_id) >= self.capacity:
            raise QueryCapacityError(self.capacity)
        if existing is not None and _name_key(existing.name) != key:
            self._by_name.pop(_name_key(existing.name), None)
        if is_new:
            self._order.append(query.id)
        self._by_id[query.id] = query
        self._by_name[key] = query.id
        return query

    def get(self, query_id: str) -> SavedQuery | None:
        return self._by_id.get(query_id)

    def require(self, query_id: str) -> SavedQuery:
        query = self.get(query_id)
        if query is None:
            raise QueryNotFoundError(query_id)
        return query

    def delete(self, query_id: str) -> bool:
        """Delete by id. Returns ``False`` when the id is unknown."""
        query = self._by_id.pop(query_id, None)
        if query is None:
            return False
        self._by_name.pop(_name_key(query.name), None)
        self._order = [item for item in self._order if item != query_id]
        return True

    def rename(self, query_id: str, name: str) -> SavedQuery:
        """Rename a query while keeping the name index consistent."""
        query = self.require(query_id)
        return self.put(replace(query, name=name))

    def list(self) -> tuple[SavedQuery, ...]:
        """Return queries ordered deterministically by creation time and name."""
        queries = list(self._by_id.values())
        return tuple(sorted(queries, key=lambda item: (item.created_at, item.name, item.id)))

    def recent(self, limit: int = 5) -> tuple[SavedQuery, ...]:
        """Return the most recently created queries."""
        if limit < 0:
            raise QueryError("limit must be >= 0")
        ordered = sorted(
            self._by_id.values(),
            key=lambda item: (item.created_at, item.name, item.id),
            reverse=True,
        )
        return tuple(ordered[:limit])

    def insertion_order(self) -> tuple[SavedQuery, ...]:
        """Return queries in the order they were first stored."""
        return tuple(self._by_id[item] for item in self._order)

    def names(self) -> tuple[str, ...]:
        return tuple(query.name for query in self.list())

    def ids(self) -> tuple[str, ...]:
        return tuple(self._order)

    def has(self, name: str) -> bool:
        return _name_key(name) in self._by_name

    def count(self) -> int:
        return len(self._by_id)

    def clear(self) -> None:
        self._by_id.clear()
        self._by_name.clear()
        self._order.clear()

    def snapshot(self) -> dict[str, object]:
        """Return a plain-data snapshot suitable for another adapter."""
        return {
            "version": STORE_VERSION,
            "capacity": self.capacity,
            "queries": [query.to_dict() for query in self.insertion_order()],
        }

    def restore(self, snapshot: Mapping[str, object]) -> int:
        """Replace store contents from a validated snapshot."""
        version = int(str(snapshot.get("version", STORE_VERSION)))
        if version != STORE_VERSION:
            raise QueryError(f"unsupported snapshot version: {version}")
        capacity = int(str(snapshot.get("capacity", self.capacity)))
        if capacity < 1:
            raise QueryError("snapshot capacity must be >= 1")
        queries = self._decode_queries(snapshot.get("queries", []))
        if len(queries) > capacity:
            raise QueryError("snapshot exceeds its declared capacity")
        self.clear()
        self.capacity = capacity
        for query in queries:
            self.put(query)
        return len(queries)

    def export_json(self) -> str:
        """Serialize the store with stable key ordering."""
        return json.dumps(self.snapshot(), indent=2, sort_keys=True)

    def import_json(self, text: str, *, replace: bool = False) -> int:
        """Import queries from JSON, optionally replacing current contents."""
        try:
            payload: object = json.loads(text)
        except json.JSONDecodeError as exc:
            raise QueryError("malformed query store JSON", details=(str(exc),)) from exc
        if not isinstance(payload, Mapping):
            raise QueryError("query store JSON must be an object")
        if replace:
            self.clear()
        queries = self._decode_queries(payload.get("queries", []))
        for query in queries:
            self.put(query)
        return len(queries)

    @staticmethod
    def _decode_queries(value: object) -> builtins.list[SavedQuery]:
        decoded: builtins.list[SavedQuery] = []
        for item in sequence_of(value):
            if not isinstance(item, Mapping):
                raise QueryError("each saved query must be a JSON object")
            decoded.append(SavedQuery.from_dict(item))
        if len({_name_key(query.name) for query in decoded}) != len(decoded):
            raise DuplicateQueryNameError("duplicate name in imported data")
        if len({query.id for query in decoded}) != len(decoded):
            raise QueryError("duplicate id in imported data")
        return decoded

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, query_id: object) -> bool:
        return isinstance(query_id, str) and query_id in self._by_id


class QueryStoreView:
    """Read-only projection of a store, useful for API responses."""

    def __init__(self, store: QueryStore) -> None:
        self.store = store

    def all(self) -> tuple[dict[str, str], ...]:
        return tuple(query.to_dict() for query in self.store.list())

    def by_name(self, name: str) -> dict[str, str] | None:
        for query in self.store.list():
            if _name_key(query.name) == _name_key(name):
                return query.to_dict()
        return None

    def page(self, offset: int, size: int) -> tuple[dict[str, str], ...]:
        """Return a bounded slice of serialized queries."""
        if offset < 0 or size < 1:
            raise QueryError("invalid page bounds")
        values = self.all()
        return values[offset : offset + size]


def merge_stores(sources: Sequence[QueryStore], capacity: int = 500) -> QueryStore:
    """Merge several stores, skipping names already claimed by earlier sources."""
    merged = QueryStore(capacity)
    for source in sources:
        for query in source.insertion_order():
            if merged.has(query.name):
                continue
            merged.put(
                SavedQuery(
                    id=query.id,
                    name=query.name,
                    expression=query.expression,
                    created_at=query.created_at,
                )
            )
    return merged
