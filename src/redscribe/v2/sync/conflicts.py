"""Conflict detection and resolution for sync operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from redscribe.v2.sync.change_journal import record_key
from redscribe.v2.sync.models import ChangeRecord, ConflictRecord


def _timestamp(value: Any) -> str:
    return str(value or "")


def _suggest_resolution(kind: str, local_updated: str, remote_updated: str) -> str:
    if kind == "delete_vs_edit":
        return "keep_local"
    if remote_updated > local_updated:
        return "keep_remote"
    if local_updated > remote_updated:
        return "keep_local"
    if kind == "duplicate":
        return "merged"
    return "keep_remote"


@dataclass(slots=True)
class ConflictDetector:
    """Detect conflicts from local and remote record sets."""

    include_content_conflicts: bool = True

    def detect(
        self,
        local: Iterable[Mapping[str, Any]],
        remote: Iterable[Mapping[str, Any]],
    ) -> list[ConflictRecord]:
        local_map = {record_key(item): dict(item) for item in local}
        remote_map = {record_key(item): dict(item) for item in remote}
        conflicts: list[ConflictRecord] = []
        for key in sorted(set(local_map) & set(remote_map)):
            left = local_map[key]
            right = remote_map[key]
            left_checksum = str(left.get("checksum", ""))
            right_checksum = str(right.get("checksum", ""))
            if left_checksum == right_checksum:
                continue
            left_deleted = left.get("deleted_at")
            right_deleted = right.get("deleted_at")
            local_updated = _timestamp(left.get("updated_at"))
            remote_updated = _timestamp(right.get("updated_at"))
            if bool(left_deleted) != bool(right_deleted):
                kind = "delete_vs_edit"
            elif left.get("title") != right.get("title") and left.get("content") == right.get(
                "content"
            ):
                kind = "metadata"
            elif left.get("content") != right.get("content"):
                kind = "content" if self.include_content_conflicts else "metadata"
            else:
                kind = "metadata"
            conflicts.append(
                ConflictRecord(
                    key=key,
                    kind=kind,
                    path=str(left.get("path") or right.get("path") or ""),
                    title=str(left.get("title") or right.get("title") or ""),
                    local_checksum=left_checksum,
                    remote_checksum=right_checksum,
                    local_updated_at=local_updated,
                    remote_updated_at=remote_updated,
                    suggested=_suggest_resolution(kind, local_updated, remote_updated),
                    details={
                        "local_deleted": bool(left_deleted),
                        "remote_deleted": bool(right_deleted),
                        "title_changed": left.get("title") != right.get("title"),
                        "content_changed": left.get("content") != right.get("content"),
                    },
                )
            )
        for conflict in self.detect_duplicates(remote_map.values()):
            conflicts.append(conflict)
        return sorted(conflicts, key=lambda item: (item.path, item.key))

    def detect_duplicates(self, records: Iterable[Mapping[str, Any]]) -> list[ConflictRecord]:
        by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for record in records:
            kind = str(record.get("kind", "note"))
            title = str(record.get("title", "")).strip().casefold()
            path = str(record.get("path", "")).strip().casefold()
            identity = (kind, path or title)
            if not identity[1]:
                continue
            by_identity.setdefault(identity, []).append(dict(record))
        duplicates: list[ConflictRecord] = []
        for identity, items in sorted(by_identity.items()):
            if len(items) < 2:
                continue
            checksums = {str(item.get("checksum", "")) for item in items}
            if len(checksums) <= 1:
                continue
            first = items[0]
            duplicates.append(
                ConflictRecord(
                    key=f"duplicate:{identity[0]}:{identity[1]}",
                    kind="duplicate",
                    path=str(first.get("path", "")),
                    title=str(first.get("title", "")),
                    suggested="merged",
                    details={
                        "count": len(items),
                        "ids": [item.get("id") for item in items],
                        "checksums": sorted(checksums),
                    },
                )
            )
        return duplicates

    def detect_from_changes(self, changes: Iterable[ChangeRecord]) -> list[ConflictRecord]:
        local: list[dict[str, Any]] = []
        remote: list[dict[str, Any]] = []
        for change in changes:
            if change.local is not None:
                local.append(change.local)
            if change.remote is not None:
                remote.append(change.remote)
        return self.detect(local, remote)


@dataclass(slots=True)
class ConflictResolver:
    """Apply manual or automatic resolutions to detected conflicts."""

    default_resolution: str = "keep_remote"

    def resolve(
        self,
        conflicts: Iterable[ConflictRecord],
        *,
        resolutions: Mapping[str, str] | None = None,
        strategy: str = "merge",
    ) -> list[ConflictRecord]:
        mapping = dict(resolutions or {})
        resolved: list[ConflictRecord] = []
        for conflict in conflicts:
            choice = mapping.get(conflict.key)
            if not choice:
                choice = self._strategy_choice(conflict, strategy)
            if choice not in {
                "keep_local",
                "keep_remote",
                "merged",
                "skip",
                "unresolved",
            }:
                choice = self.default_resolution
            conflict.resolution = choice
            resolved.append(conflict)
        return resolved

    def _strategy_choice(self, conflict: ConflictRecord, strategy: str) -> str:
        if strategy == "prefer_local":
            return "keep_local"
        if strategy == "prefer_remote":
            return "keep_remote"
        if strategy == "skip":
            return "skip"
        if strategy == "merge":
            if conflict.suggested in {"keep_local", "keep_remote", "merged"}:
                return conflict.suggested
            return "merged"
        return conflict.suggested or self.default_resolution

    def unresolved(self, conflicts: Iterable[ConflictRecord]) -> list[ConflictRecord]:
        return [conflict for conflict in conflicts if conflict.resolution == "unresolved"]

    def summary(self, conflicts: Iterable[ConflictRecord]) -> dict[str, int]:
        counts = {
            "total": 0,
            "unresolved": 0,
            "keep_local": 0,
            "keep_remote": 0,
            "merged": 0,
            "skip": 0,
        }
        for conflict in conflicts:
            counts["total"] += 1
            counts[conflict.resolution] = counts.get(conflict.resolution, 0) + 1
        return counts
