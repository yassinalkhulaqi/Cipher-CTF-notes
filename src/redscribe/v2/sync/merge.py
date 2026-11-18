"""Merge strategies for sync imports and restores."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.conflicts import ConflictDetector, ConflictResolver
from redscribe.v2.sync.errors import ConflictError, ValidationError
from redscribe.v2.sync.models import MERGE_STRATEGIES, ChangeRecord, ConflictRecord, MergeResult


def _merge_text(local: str, remote: str) -> str:
    if local == remote:
        return local
    if not local.strip():
        return remote
    if not remote.strip():
        return local
    return local.rstrip() + "\n\n<!-- sync:local -->\n\n" + remote.lstrip()


def merge_records(local: Mapping[str, Any], remote: Mapping[str, Any]) -> dict[str, Any]:
    """Merge two note payloads conservatively."""
    merged = dict(remote)
    merged.update({key: value for key, value in local.items() if value not in ("", None)})
    merged["title"] = str(remote.get("title") or local.get("title") or "Untitled")
    merged["content"] = _merge_text(str(local.get("content", "")), str(remote.get("content", "")))
    merged["tags"] = ", ".join(
        sorted(
            {
                part.strip()
                for part in f"{local.get('tags', '')},{remote.get('tags', '')}".split(",")
                if part.strip()
            }
        )
    )
    merged["updated_at"] = max(
        str(local.get("updated_at", "")),
        str(remote.get("updated_at", "")),
    )
    merged["path"] = str(remote.get("path") or local.get("path") or "")
    merged["kind"] = str(remote.get("kind") or local.get("kind") or "note")
    return merged


@dataclass(slots=True)
class MergeEngine:
    """Apply merge strategies to change journals."""

    strategy: str = "merge"
    detector: ConflictDetector = field(default_factory=ConflictDetector)
    resolver: ConflictResolver = field(default_factory=ConflictResolver)

    def __post_init__(self) -> None:
        if self.strategy not in MERGE_STRATEGIES:
            raise ValidationError(f"Unsupported merge strategy: {self.strategy}")

    def plan(
        self,
        local: Iterable[Mapping[str, Any]],
        remote: Iterable[Mapping[str, Any]],
        *,
        resolutions: Mapping[str, str] | None = None,
    ) -> tuple[list[ChangeRecord], list[ConflictRecord]]:
        journal = ChangeJournal()
        changes = [
            change for change in journal.build(local, remote) if change.action != "unchanged"
        ]
        conflicts = self.detector.detect(local, remote)
        self.resolver.resolve(conflicts, resolutions=resolutions, strategy=self.strategy)
        return changes, conflicts

    def apply(
        self,
        local: Iterable[Mapping[str, Any]],
        remote: Iterable[Mapping[str, Any]],
        *,
        resolutions: Mapping[str, str] | None = None,
        dry_run: bool = False,
        applier: Callable[[ChangeRecord, dict[str, Any] | None], None] | None = None,
    ) -> MergeResult:
        changes, conflicts = self.plan(local, remote, resolutions=resolutions)
        conflict_map = {conflict.key: conflict for conflict in conflicts}
        unresolved = [conflict for conflict in conflicts if conflict.resolution == "unresolved"]
        if unresolved and self.strategy not in {"skip"}:
            raise ConflictError(
                "Unresolved merge conflicts",
                details={"count": len(unresolved), "keys": [item.key for item in unresolved]},
            )
        applied: list[ChangeRecord] = []
        skipped: list[ChangeRecord] = []
        for change in changes:
            conflict = conflict_map.get(change.key)
            payload = self._payload_for(change, conflict)
            if payload is None:
                skipped.append(change)
                continue
            if not dry_run and applier is not None:
                applier(change, payload)
            applied.append(change)
        return MergeResult(
            strategy=self.strategy,
            applied=applied,
            skipped=skipped,
            conflicts=conflicts,
            dry_run=dry_run,
        )

    def _payload_for(
        self, change: ChangeRecord, conflict: ConflictRecord | None
    ) -> dict[str, Any] | None:
        if conflict is not None:
            if conflict.resolution == "skip":
                return None
            if conflict.resolution == "keep_local":
                return dict(change.local or {})
            if conflict.resolution == "keep_remote":
                return dict(change.remote or {})
            if conflict.resolution == "merged":
                return merge_records(change.local or {}, change.remote or {})
            if conflict.resolution == "unresolved":
                return None
        if change.action == "create":
            return dict(change.remote or {})
        if change.action == "update":
            if self.strategy == "prefer_local":
                return dict(change.local or {})
            if self.strategy == "prefer_remote":
                return dict(change.remote or {})
            if self.strategy == "skip":
                return None
            return merge_records(change.local or {}, change.remote or {})
        if change.action == "delete":
            if self.strategy == "prefer_remote":
                return None
            if self.strategy == "prefer_local":
                return None
            if self.strategy == "skip":
                return None
            return None
        return None

    def preview(
        self,
        local: Iterable[Mapping[str, Any]],
        remote: Iterable[Mapping[str, Any]],
        *,
        resolutions: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        result = self.apply(local, remote, resolutions=resolutions, dry_run=True)
        return result.as_dict()
