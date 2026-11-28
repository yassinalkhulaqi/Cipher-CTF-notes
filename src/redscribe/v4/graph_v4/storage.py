"""Persistence adapters for named v4 graph snapshots and saved filters.

The in-memory repository is the default; the SQLite repository has the same
protocol so a caller can swap adapters without touching the domain layer. All
payloads are plain JSON dictionaries and never include executable content.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast

from redscribe.v4.events import utc_now

from .types import (
    SNAPSHOT_NAME_PATTERN,
    GraphData,
    GraphFilter,
    GraphSnapshot,
    LayoutKind,
)

__all__ = [
    "GraphStore",
    "GraphStoreError",
    "InMemoryGraphRepository",
    "SnapshotRepository",
    "SqliteGraphRepository",
]


class GraphStoreError(ValueError):
    """Raised for invalid names, missing snapshots, or conflicting writes."""


def _checked_name(name: str) -> str:
    normalized = name.strip().casefold()
    if not SNAPSHOT_NAME_PATTERN.match(normalized):
        raise GraphStoreError(f"invalid snapshot name: {name}")
    return normalized


class SnapshotRepository(Protocol):
    """Storage contract shared by the in-memory and SQLite adapters."""

    def save(self, name: str, snapshot: GraphSnapshot) -> None: ...

    def load(self, name: str) -> GraphSnapshot | None: ...

    def delete(self, name: str) -> bool: ...

    def names(self) -> tuple[str, ...]: ...

    def save_filter(self, name: str, flt: GraphFilter) -> None: ...

    def load_filter(self, name: str) -> GraphFilter | None: ...

    def filter_names(self) -> tuple[str, ...]: ...


class InMemoryGraphRepository:
    """A deterministic, process-local repository."""

    def __init__(self) -> None:
        self._snapshots: dict[str, GraphSnapshot] = {}
        self._filters: dict[str, GraphFilter] = {}

    def save(self, name: str, snapshot: GraphSnapshot) -> None:
        self._snapshots[_checked_name(name)] = snapshot

    def load(self, name: str) -> GraphSnapshot | None:
        return self._snapshots.get(_checked_name(name))

    def delete(self, name: str) -> bool:
        return self._snapshots.pop(_checked_name(name), None) is not None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._snapshots))

    def save_filter(self, name: str, flt: GraphFilter) -> None:
        self._filters[_checked_name(name)] = flt

    def load_filter(self, name: str) -> GraphFilter | None:
        return self._filters.get(_checked_name(name))

    def filter_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._filters))

    def clear(self) -> None:
        self._snapshots.clear()
        self._filters.clear()


class SqliteGraphRepository:
    """A SQLite-backed repository using a caller-supplied connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS graph_snapshots ("
            "name TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS graph_filters ("
            "name TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self.connection.commit()

    def save(self, name: str, snapshot: GraphSnapshot) -> None:
        key = _checked_name(name)
        payload = json.dumps(snapshot.to_dict(), sort_keys=True)
        self.connection.execute(
            "INSERT OR REPLACE INTO graph_snapshots (name, payload, updated_at) VALUES (?, ?, ?)",
            (key, payload, snapshot.created_at),
        )
        self.connection.commit()

    def load(self, name: str) -> GraphSnapshot | None:
        row = self.connection.execute(
            "SELECT payload FROM graph_snapshots WHERE name = ?", (_checked_name(name),)
        ).fetchone()
        if row is None:
            return None
        return GraphSnapshot.from_dict(cast(dict[str, Any], json.loads(str(row[0]))))

    def delete(self, name: str) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM graph_snapshots WHERE name = ?", (_checked_name(name),)
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def names(self) -> tuple[str, ...]:
        rows = self.connection.execute("SELECT name FROM graph_snapshots ORDER BY name").fetchall()
        return tuple(str(row[0]) for row in rows)

    def save_filter(self, name: str, flt: GraphFilter) -> None:
        payload = json.dumps(flt.to_dict(), sort_keys=True)
        self.connection.execute(
            "INSERT OR REPLACE INTO graph_filters (name, payload) VALUES (?, ?)",
            (_checked_name(name), payload),
        )
        self.connection.commit()

    def load_filter(self, name: str) -> GraphFilter | None:
        row = self.connection.execute(
            "SELECT payload FROM graph_filters WHERE name = ?", (_checked_name(name),)
        ).fetchone()
        if row is None:
            return None
        return GraphFilter.from_dict(cast(dict[str, Any], json.loads(str(row[0]))))

    def filter_names(self) -> tuple[str, ...]:
        rows = self.connection.execute("SELECT name FROM graph_filters ORDER BY name").fetchall()
        return tuple(str(row[0]) for row in rows)


class GraphStore:
    """Application-facing snapshot store with validation and export helpers."""

    def __init__(
        self,
        repository: SnapshotRepository | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.repository = repository or InMemoryGraphRepository()
        self.clock = clock

    @property
    def names(self) -> tuple[str, ...]:
        return self.repository.names()

    def exists(self, name: str) -> bool:
        return self.repository.load(name) is not None

    def save(
        self,
        name: str,
        data: GraphData,
        flt: GraphFilter | None = None,
        layout: LayoutKind = LayoutKind.FORCE,
        tags: tuple[str, ...] = (),
    ) -> GraphSnapshot:
        key = _checked_name(name)
        if self.exists(key):
            raise GraphStoreError(f"snapshot already exists: {key}")
        snapshot = GraphSnapshot(
            name=key,
            data=data,
            filter=flt or GraphFilter(),
            layout=layout,
            created_at=self.clock(),
            tags=tags,
        )
        self.repository.save(key, snapshot)
        return snapshot

    def load(self, name: str) -> GraphSnapshot:
        snapshot = self.repository.load(_checked_name(name))
        if snapshot is None:
            raise GraphStoreError(f"snapshot not found: {name}")
        return snapshot

    def delete(self, name: str) -> bool:
        return self.repository.delete(_checked_name(name))

    def save_filter(self, name: str, flt: GraphFilter) -> GraphFilter:
        key = _checked_name(name)
        self.repository.save_filter(key, flt)
        return flt

    def load_filter(self, name: str) -> GraphFilter:
        flt = self.repository.load_filter(_checked_name(name))
        if flt is None:
            raise GraphStoreError(f"filter not found: {name}")
        return flt

    def filters(self) -> dict[str, GraphFilter]:
        return {
            name: flt
            for name in self.repository.filter_names()
            if (flt := self.repository.load_filter(name)) is not None
        }

    def export(self, name: str) -> dict[str, Any]:
        snapshot = self.load(name)
        payload = snapshot.to_dict()
        payload["filter_index"] = {name: flt.to_dict() for name, flt in self.filters().items()}
        return payload

    def export_all(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.export(name) for name in self.names)

    def import_snapshot(self, payload: Mapping[str, Any]) -> GraphSnapshot:
        try:
            snapshot = GraphSnapshot.from_dict(dict(payload))
        except (TypeError, ValueError) as exc:
            raise GraphStoreError(f"invalid snapshot payload: {exc}") from exc
        key = _checked_name(snapshot.name)
        if self.exists(key):
            raise GraphStoreError(f"snapshot already exists: {key}")
        self.repository.save(key, snapshot)
        return snapshot

    def clone(self, name: str, new_name: str) -> GraphSnapshot:
        source = self.load(name)
        target = _checked_name(new_name)
        if self.exists(target):
            raise GraphStoreError(f"snapshot already exists: {target}")
        clone = GraphSnapshot(
            name=target,
            data=source.data,
            filter=source.filter,
            layout=source.layout,
            created_at=self.clock(),
            tags=source.tags,
        )
        self.repository.save(target, clone)
        return clone

    def clear(self) -> None:
        for name in self.names:
            self.repository.delete(name)
