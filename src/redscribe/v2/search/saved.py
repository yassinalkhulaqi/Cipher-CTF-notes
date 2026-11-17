"""Persistence and validation for named search queries."""

from __future__ import annotations

import builtins
import secrets
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.search.models import MAX_QUERY_LENGTH, SavedQuery, utc_now

SAVED_QUERY_KEY = "v2.search.saved_queries"
MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 240
MAX_TAG_LENGTH = 40
MAX_SAVED_QUERIES = 200


def validate_saved_query(name: str, query: str) -> tuple[str, str]:
    """Validate and normalize a saved query name and expression."""
    cleaned_name = " ".join(name.split())
    cleaned_query = query.strip()
    if not cleaned_name:
        raise ValueError("Saved query name is required")
    if len(cleaned_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Saved query name exceeds {MAX_NAME_LENGTH} characters")
    if not cleaned_query:
        raise ValueError("Saved query expression is required")
    if len(cleaned_query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Saved query exceeds {MAX_QUERY_LENGTH} characters")
    return cleaned_name, cleaned_query


def normalize_tags(values: Iterable[str] | str) -> tuple[str, ...]:
    """Normalize a tag list or comma-separated string into unique tags."""
    raw = values.split(",") if isinstance(values, str) else list(values)
    result: list[str] = []
    for value in raw:
        tag = " ".join(str(value).split())
        if not tag or len(tag) > MAX_TAG_LENGTH:
            continue
        if tag.casefold() not in {item.casefold() for item in result}:
            result.append(tag)
    return tuple(result[:12])


class SavedQueryStore:
    """Store saved queries in a vault setting without altering the schema."""

    def __init__(self, vault: Vault, *, clock: Callable[[], str] = utc_now) -> None:
        self._vault = vault
        self._clock = clock

    def _load(self) -> list[SavedQuery]:
        payload: Any = self._vault.get_json_setting(SAVED_QUERY_KEY, [])
        if not isinstance(payload, list):
            return []
        items: list[SavedQuery] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(SavedQuery.from_dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
        return items

    def _save(self, items: Sequence[SavedQuery]) -> None:
        self._vault.set_json_setting(
            SAVED_QUERY_KEY,
            [item.as_dict() for item in items[:MAX_SAVED_QUERIES]],
        )

    def list(
        self,
        *,
        search: str = "",
        tag: str = "",
        limit: int = 50,
    ) -> list[SavedQuery]:
        """List saved queries with optional name and tag filtering."""
        items = self._load()
        needle = search.strip().casefold()
        tag_needle = tag.strip().casefold()
        if needle:
            items = [
                item
                for item in items
                if needle in item.name.casefold() or needle in item.query.casefold()
            ]
        if tag_needle:
            items = [
                item for item in items if tag_needle in {value.casefold() for value in item.tags}
            ]
        items.sort(
            key=lambda item: (
                not item.pinned,
                -item.use_count,
                item.updated_at,
                item.name.casefold(),
            )
        )
        return items[: max(0, limit)]

    def get(self, saved_id: str) -> SavedQuery | None:
        for item in self._load():
            if item.id == saved_id:
                return item
        return None

    def create(
        self,
        name: str,
        query: str,
        *,
        description: str = "",
        tags: Iterable[str] | str = (),
        pinned: bool = False,
        saved_id: str | None = None,
    ) -> SavedQuery:
        """Create and persist one saved query."""
        clean_name, clean_query = validate_saved_query(name, query)
        items = self._load()
        identifier = saved_id or f"sq_{secrets.token_hex(6)}"
        if any(item.id == identifier for item in items):
            raise ValueError(f"Saved query id already exists: {identifier}")
        now = self._clock()
        item = SavedQuery(
            id=identifier,
            name=clean_name,
            query=clean_query,
            description=" ".join(description.split())[:MAX_DESCRIPTION_LENGTH],
            tags=normalize_tags(tags),
            created_at=now,
            updated_at=now,
            pinned=pinned,
        )
        items.append(item)
        self._save(items)
        return item

    def update(
        self,
        saved_id: str,
        *,
        name: str | None = None,
        query: str | None = None,
        description: str | None = None,
        tags: Iterable[str] | str | None = None,
        pinned: bool | None = None,
    ) -> SavedQuery | None:
        """Update selected fields of one saved query."""
        items = self._load()
        for index, item in enumerate(items):
            if item.id != saved_id:
                continue
            clean_name, clean_query = validate_saved_query(
                item.name if name is None else name,
                item.query if query is None else query,
            )
            updated = SavedQuery(
                id=item.id,
                name=clean_name,
                query=clean_query,
                description=(
                    item.description
                    if description is None
                    else " ".join(description.split())[:MAX_DESCRIPTION_LENGTH]
                ),
                tags=item.tags if tags is None else normalize_tags(tags),
                created_at=item.created_at,
                updated_at=self._clock(),
                use_count=item.use_count,
                pinned=item.pinned if pinned is None else pinned,
            )
            items[index] = updated
            self._save(items)
            return updated
        return None

    def delete(self, saved_id: str) -> bool:
        """Delete one saved query by id."""
        items = self._load()
        remaining = [item for item in items if item.id != saved_id]
        if len(remaining) == len(items):
            return False
        self._save(remaining)
        return True

    def record_use(self, saved_id: str) -> SavedQuery | None:
        """Increment the use counter and refresh the update timestamp."""
        items = self._load()
        for index, item in enumerate(items):
            if item.id != saved_id:
                continue
            updated = SavedQuery(
                **{
                    **item.as_dict(),
                    "use_count": item.use_count + 1,
                    "updated_at": self._clock(),
                }
            )
            items[index] = updated
            self._save(items)
            return updated
        return None

    def duplicate(self, saved_id: str, *, name: str | None = None) -> SavedQuery | None:
        """Clone one saved query under a new name."""
        item = self.get(saved_id)
        if item is None:
            return None
        return self.create(
            name or f"{item.name} copy",
            item.query,
            description=item.description,
            tags=item.tags,
            pinned=False,
        )

    def toggle_pin(self, saved_id: str) -> SavedQuery | None:
        """Toggle the pinned flag of one saved query."""
        item = self.get(saved_id)
        if item is None:
            return None
        return self.update(saved_id, pinned=not item.pinned)

    def import_items(
        self,
        payload: Iterable[Mapping[str, Any]],
        *,
        replace: bool = False,
    ) -> int:
        """Import serialized saved queries, skipping malformed records."""
        imported: list[SavedQuery] = []
        for raw in payload:
            try:
                item = SavedQuery.from_dict(raw)
                validate_saved_query(item.name, item.query)
            except (KeyError, TypeError, ValueError):
                continue
            imported.append(item)
        items = [] if replace else self._load()
        known = {item.id for item in items}
        for item in imported:
            if item.id in known:
                item = SavedQuery(**{**item.as_dict(), "id": f"sq_{secrets.token_hex(6)}"})
            items.append(item)
            known.add(item.id)
        self._save(items)
        return len(imported)

    def export_payload(self) -> builtins.list[dict[str, Any]]:
        """Return a portable JSON payload for all saved queries."""
        return [item.as_dict() for item in self._load()]


def saved_query_summary(item: SavedQuery) -> dict[str, Any]:
    """Return the compact representation used by suggestion lists."""
    return {
        "id": item.id,
        "name": item.name,
        "query": item.query,
        "tags": list(item.tags),
        "pinned": item.pinned,
    }
