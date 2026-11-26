"""In-memory, SQLite-ready persistence for capture items.

:class:`InboxStore` owns the identity index, content-hash index, insertion
order, filtering, and JSON portability for the inbox. It is deliberately backed
by plain dictionaries so it can be swapped for a SQL adapter later without
changing the service or API layers: all public methods speak in validated
:class:`CaptureItem` values and JSON-safe dictionaries.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence

from redscribe.v4.inbox.types import (
    CaptureItem,
    CaptureSource,
    TriageState,
    compute_content_hash,
    normalize_tag,
)

MAX_IMPORT_ITEMS = 5000


class StorageError(Exception):
    """Base class for store consistency and conflict errors."""


class DuplicateItemError(StorageError):
    """Raised when an id or content hash is already present."""

    def __init__(self, value: str, field: str) -> None:
        super().__init__(f"duplicate {field}: {value}")
        self.value = value
        self.field = field


class InboxImportError(StorageError):
    """Raised when an import payload is malformed or conflicts with the store."""


class InboxStore:
    """An ordered, indexed collection of validated capture items."""

    def __init__(self, items: Iterable[CaptureItem] = ()) -> None:
        self._items: dict[str, CaptureItem] = {}
        self._by_hash: dict[str, str] = {}
        self._order: list[str] = []
        for item in items:
            self.insert(item)

    def insert(self, item: CaptureItem) -> None:
        """Insert one item, rejecting duplicate ids and content hashes."""
        if not isinstance(item, CaptureItem):
            raise TypeError("item must be a CaptureItem")
        if item.id in self._items:
            raise DuplicateItemError(item.id, "id")
        if item.content_hash in self._by_hash:
            raise DuplicateItemError(item.content_hash, "content_hash")
        self._items[item.id] = item
        self._by_hash[item.content_hash] = item.id
        self._order.append(item.id)

    def get(self, item_id: str) -> CaptureItem | None:
        """Return an item by id, or ``None`` when absent."""
        return self._items.get(item_id)

    def require(self, item_id: str) -> CaptureItem:
        """Return an item by id or raise :class:`StorageError`."""
        item = self._items.get(item_id)
        if item is None:
            raise StorageError(f"no capture with id: {item_id}")
        return item

    def update(self, item: CaptureItem) -> None:
        """Replace an existing item and keep both indexes in sync."""
        if not isinstance(item, CaptureItem):
            raise TypeError("item must be a CaptureItem")
        previous = self._items.get(item.id)
        if previous is None:
            raise StorageError(f"cannot update missing capture: {item.id}")
        owner = self._by_hash.get(item.content_hash)
        if owner is not None and owner != item.id:
            raise DuplicateItemError(item.content_hash, "content_hash")
        self._by_hash.pop(previous.content_hash, None)
        self._items[item.id] = item
        self._by_hash[item.content_hash] = item.id

    def delete(self, item_id: str) -> bool:
        """Delete an item and its index entries; return whether it existed."""
        item = self._items.pop(item_id, None)
        if item is None:
            return False
        self._by_hash.pop(item.content_hash, None)
        self._order = [value for value in self._order if value != item_id]
        return True

    def find_by_hash(self, digest: str) -> CaptureItem | None:
        """Find an item by its normalized content hash."""
        owner = self._by_hash.get(digest)
        return self._items.get(owner) if owner else None

    def list(
        self,
        state: TriageState | None = None,
        source: CaptureSource | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> tuple[CaptureItem, ...]:
        """Return items matching all supplied filters, newest first."""
        canonical_tag = normalize_tag(tag) if tag else None
        needle = query.strip().casefold() if query else ""
        matches: list[CaptureItem] = []
        for item in self._items.values():
            if state is not None and item.state is not state:
                continue
            if source is not None and item.source is not source:
                continue
            if canonical_tag is not None and canonical_tag not in item.tags:
                continue
            if needle and needle not in item.raw.casefold() and needle not in item.tag_line:
                continue
            matches.append(item)
        return tuple(sorted(matches, key=lambda item: (item.created_at, item.id), reverse=True))

    def ids(self) -> tuple[str, ...]:
        """Return ids in insertion order."""
        return tuple(self._order)

    def all(self) -> tuple[CaptureItem, ...]:
        """Return all items in creation order, newest first."""
        return self.list()

    def rebuild_index(self) -> int:
        """Rebuild both indexes from the item map and return the item count."""
        by_hash: dict[str, str] = {}
        for item_id, item in self._items.items():
            digest = compute_content_hash(item.raw)
            if item.content_hash != digest:
                raise StorageError(f"stored hash is stale for {item_id}")
            if digest in by_hash:
                raise DuplicateItemError(digest, "content_hash")
            by_hash[digest] = item_id
        self._by_hash = by_hash
        self._order = [
            item_id
            for item_id, _ in sorted(
                self._items.items(),
                key=lambda pair: (pair[1].created_at, pair[0]),
            )
        ]
        return len(self._items)

    def index_report(self) -> dict[str, int]:
        """Return index sizes for diagnostics and consistency checks."""
        return {
            "items": len(self._items),
            "hashes": len(self._by_hash),
            "order": len(self._order),
        }

    def is_consistent(self) -> bool:
        """Check that every item is indexed exactly once in both indexes."""
        if set(self._items) != set(self._order) or len(set(self._order)) != len(self._order):
            return False
        if len(self._by_hash) != len(self._items):
            return False
        for item_id, item in self._items.items():
            if self._by_hash.get(item.content_hash) != item_id:
                return False
        return True

    def export_json(self) -> str:
        """Serialize all items and a format version to JSON."""
        payload = {
            "version": 1,
            "items": [item.to_dict() for item in self.list()],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def import_json(self, text: str) -> int:
        """Import JSON items, skipping exact duplicates and rejecting conflicts."""
        if not isinstance(text, str) or not text.strip():
            raise InboxImportError("import payload must be a non-empty JSON string")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InboxImportError("import payload is not valid JSON") from exc
        raw_items: Sequence[Mapping[str, object]]
        if isinstance(payload, dict) and "items" in payload:
            if payload.get("version", 1) != 1:
                raise InboxImportError("unsupported import version")
            candidate = payload["items"]
            if not isinstance(candidate, list):
                raise InboxImportError("items must be a list")
            raw_items = candidate
        elif isinstance(payload, list):
            raw_items = payload
        else:
            raise InboxImportError("import payload must contain an items list")
        if len(raw_items) > MAX_IMPORT_ITEMS:
            raise InboxImportError(f"import exceeds {MAX_IMPORT_ITEMS} items")
        staged: list[CaptureItem] = []
        for entry in raw_items:
            if not isinstance(entry, dict):
                raise InboxImportError("each imported item must be an object")
            staged.append(CaptureItem.from_dict(entry))
        inserted = 0
        for item in staged:
            existing = self._items.get(item.id)
            if existing is not None:
                if existing.to_dict() == item.to_dict():
                    continue
                raise InboxImportError(f"conflicting id on import: {item.id}")
            duplicate = self.find_by_hash(item.content_hash)
            if duplicate is not None:
                continue
            self.insert(item)
            inserted += 1
        return inserted

    def clear(self) -> None:
        """Remove all captured items."""
        self._items.clear()
        self._by_hash.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._items


__all__ = [
    "MAX_IMPORT_ITEMS",
    "DuplicateItemError",
    "InboxImportError",
    "InboxStore",
    "StorageError",
]
