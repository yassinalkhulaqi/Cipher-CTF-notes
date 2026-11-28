"""Persistence adapters for preference snapshots and catalog metadata.

All adapters are in-memory and SQLite-ready: they expose plain dictionaries at
the boundary so a future SQL implementation can replace them without changing
service or API code. Timestamps and identifiers are injected for determinism.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v4.a11y_i18n.types import (
    Direction,
    LocaleCatalog,
    MotionPolicy,
    require_locale,
    require_text,
)
from redscribe.v4.clock import Clock
from redscribe.v4.preferences import Preferences


class StorageError(ValueError):
    """Raised when a snapshot or catalog index operation is invalid."""


def require_name(value: object) -> str:
    """Validate a snapshot name."""
    try:
        text = require_text(value, "name", max_length=64)
    except ValueError as exc:
        raise StorageError(str(exc)) from exc
    for character in text:
        if not (character.isalnum() or character in "-_ ."):
            raise StorageError(f"invalid snapshot name: {text}")
    return text


@dataclass(frozen=True, slots=True)
class PreferenceSnapshot:
    """A named, versioned capture of display preferences."""

    name: str
    preferences: Preferences
    motion_policy: MotionPolicy
    locale: str
    saved_at: str
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_name(self.name))
        object.__setattr__(self, "locale", require_locale(self.locale))
        if self.version < 1:
            raise StorageError("version must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "preferences": self.preferences.to_dict(),
            "motion_policy": self.motion_policy.to_dict(),
            "locale": self.locale,
            "saved_at": self.saved_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PreferenceSnapshot:
        raw_preferences = data.get("preferences", {})
        raw_policy = data.get("motion_policy", {})
        if not isinstance(raw_preferences, Mapping) or not isinstance(raw_policy, Mapping):
            raise StorageError("preferences and motion_policy must be objects")
        return cls(
            name=str(data.get("name", "")),
            preferences=Preferences.from_dict(raw_preferences),
            motion_policy=MotionPolicy.from_dict(raw_policy),
            locale=str(data.get("locale", "en")),
            saved_at=str(data.get("saved_at", "")),
            version=int(data.get("version", 1)),
        )


@dataclass(frozen=True, slots=True)
class SnapshotIndex:
    """A compact, queryable summary of all saved snapshots."""

    names: tuple[str, ...]
    locales: tuple[str, ...]
    total: int
    latest_saved_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "locales": list(self.locales),
            "total": self.total,
            "latest_saved_at": self.latest_saved_at,
        }


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    """Immutable metadata used to index a registered locale catalog."""

    locale: str
    language: str
    direction: Direction
    message_count: int
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "locale": self.locale,
            "language": self.language,
            "direction": self.direction.value,
            "message_count": self.message_count,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CatalogRecord:
        return cls(
            locale=str(data.get("locale", "")),
            language=str(data.get("language", "")),
            direction=Direction.parse(str(data.get("direction", "ltr"))),
            message_count=int(data.get("message_count", 0)),
            checksum=str(data.get("checksum", "")),
        )


def catalog_checksum(catalog: LocaleCatalog) -> str:
    """Compute a stable digest of a catalog's translated messages."""
    canonical = "|".join(
        f"{message.value}={catalog.messages[message]}"
        for message in sorted(catalog.messages, key=lambda item: item.value)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class PreferenceSnapshotStore:
    """An upsertable, exportable collection of preference snapshots."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock: Clock = clock or Clock()
        self._snapshots: dict[str, PreferenceSnapshot] = {}
        self._revisions: dict[str, int] = {}

    def save(
        self,
        name: str,
        preferences: Preferences,
        motion_policy: MotionPolicy,
        locale: str,
        *,
        overwrite: bool = False,
    ) -> PreferenceSnapshot:
        key = require_name(name)
        if key in self._snapshots and not overwrite:
            raise StorageError(f"snapshot exists: {key}")
        previous = self._snapshots.get(key)
        version = previous.version + 1 if previous else 1
        snapshot = PreferenceSnapshot(
            name=key,
            preferences=preferences,
            motion_policy=motion_policy,
            locale=require_locale(locale),
            saved_at=self.clock.iso(),
            version=version,
        )
        self._snapshots[key] = snapshot
        self._revisions[key] = self._revisions.get(key, 0) + 1
        return snapshot

    def load(self, name: str) -> PreferenceSnapshot:
        key = require_name(name)
        try:
            return self._snapshots[key]
        except KeyError as exc:
            raise StorageError(f"snapshot not found: {key}") from exc

    def get(self, name: str) -> PreferenceSnapshot | None:
        return self._snapshots.get(require_name(name))

    def remove(self, name: str) -> PreferenceSnapshot:
        key = require_name(name)
        if key not in self._snapshots:
            raise StorageError(f"snapshot not found: {key}")
        removed = self._snapshots.pop(key)
        self._revisions.pop(key, None)
        return removed

    def rename(self, current: str, new_name: str) -> PreferenceSnapshot:
        old_key = require_name(current)
        new_key = require_name(new_name)
        if old_key == new_key:
            raise StorageError("snapshot names must differ")
        snapshot = self.load(old_key)
        if new_key in self._snapshots:
            raise StorageError(f"snapshot exists: {new_key}")
        renamed = PreferenceSnapshot(
            name=new_key,
            preferences=snapshot.preferences,
            motion_policy=snapshot.motion_policy,
            locale=snapshot.locale,
            saved_at=snapshot.saved_at,
            version=snapshot.version + 1,
        )
        del self._snapshots[old_key]
        self._revisions[new_key] = self._revisions.pop(old_key, 0) + 1
        self._snapshots[new_key] = renamed
        return renamed

    def revision(self, name: str) -> int:
        require_name(name)
        return self._revisions.get(name, 0)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._snapshots))

    def all(self) -> tuple[PreferenceSnapshot, ...]:
        return tuple(self._snapshots[name] for name in self.names())

    def count(self) -> int:
        return len(self._snapshots)

    def index(self) -> SnapshotIndex:
        snapshots = self.all()
        locales = tuple(sorted({snapshot.locale for snapshot in snapshots}))
        latest = max((snapshot.saved_at for snapshot in snapshots), default="")
        return SnapshotIndex(self.names(), locales, len(snapshots), latest)

    def export(self) -> dict[str, Any]:
        return {
            "version": 1,
            "snapshots": [snapshot.to_dict() for snapshot in self.all()],
        }

    def import_from(self, data: Mapping[str, Any]) -> int:
        """Merge an exported document into the store, returning the new count."""
        if int(data.get("version", 1)) != 1:
            raise StorageError("unsupported export version")
        raw = data.get("snapshots", [])
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise StorageError("snapshots must be a list")
        imported = 0
        for item in raw:
            if not isinstance(item, Mapping):
                raise StorageError("snapshot entry must be an object")
            snapshot = PreferenceSnapshot.from_dict(item)
            if snapshot.name not in self._snapshots:
                imported += 1
            self._snapshots[snapshot.name] = snapshot
            self._revisions[snapshot.name] = self._revisions.get(snapshot.name, 0) + 1
        return imported

    def clear(self) -> None:
        self._snapshots.clear()
        self._revisions.clear()


class CatalogIndex:
    """A metadata-only index over locale catalogs."""

    def __init__(self) -> None:
        self._records: dict[str, CatalogRecord] = {}

    def register(self, catalog: LocaleCatalog, *, overwrite: bool = False) -> CatalogRecord:
        locale = require_locale(catalog.locale)
        if locale in self._records and not overwrite:
            raise StorageError(f"catalog indexed already: {locale}")
        record = CatalogRecord(
            locale=locale,
            language=locale.split("-", 1)[0],
            direction=catalog.direction,
            message_count=len(catalog.messages),
            checksum=catalog_checksum(catalog),
        )
        self._records[locale] = record
        return record

    def get(self, locale: str) -> CatalogRecord:
        key = require_locale(locale)
        try:
            return self._records[key]
        except KeyError as exc:
            raise StorageError(f"catalog not indexed: {key}") from exc

    def remove(self, locale: str) -> CatalogRecord:
        key = require_locale(locale)
        if key not in self._records:
            raise StorageError(f"catalog not indexed: {key}")
        return self._records.pop(key)

    def locales(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def matching(self, prefix: str) -> tuple[CatalogRecord, ...]:
        query = prefix.strip().casefold()
        return tuple(
            self._records[key] for key in sorted(self._records) if key.casefold().startswith(query)
        )

    def changed(self, catalog: LocaleCatalog) -> bool:
        """Return True when a catalog's checksum differs from the indexed one."""
        try:
            return self.get(catalog.locale).checksum != catalog_checksum(catalog)
        except StorageError:
            return True

    def all(self) -> tuple[CatalogRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def export(self) -> dict[str, Any]:
        return {
            "version": 1,
            "catalogs": [record.to_dict() for record in self.all()],
        }

    def import_from(self, data: Mapping[str, Any]) -> int:
        if int(data.get("version", 1)) != 1:
            raise StorageError("unsupported catalog index version")
        raw = data.get("catalogs", [])
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise StorageError("catalogs must be a list")
        for item in raw:
            if not isinstance(item, Mapping):
                raise StorageError("catalog entry must be an object")
            record = CatalogRecord.from_dict(item)
            self._records[record.locale] = record
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()


def export_bundle(snapshots: PreferenceSnapshotStore, catalogs: CatalogIndex) -> dict[str, Any]:
    """Combine stores into one deterministic, JSON-serializable document."""
    return {
        "schema": "redscribe.a11y-i18n",
        "version": 1,
        "snapshots": snapshots.export(),
        "catalogs": catalogs.export(),
    }


__all__ = [
    "CatalogIndex",
    "CatalogRecord",
    "PreferenceSnapshot",
    "PreferenceSnapshotStore",
    "SnapshotIndex",
    "StorageError",
    "catalog_checksum",
    "export_bundle",
    "require_name",
]
