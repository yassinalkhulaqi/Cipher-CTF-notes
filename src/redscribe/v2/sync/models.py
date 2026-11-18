"""Data models for sync and portability workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SYNC_FORMATS: tuple[str, ...] = ("json", "markdown", "html", "sqlite")
MERGE_STRATEGIES: tuple[str, ...] = ("skip", "prefer_local", "prefer_remote", "merge")
CONFLICT_KINDS: tuple[str, ...] = (
    "content",
    "metadata",
    "delete_vs_edit",
    "duplicate",
    "schema",
)
CONFLICT_RESOLUTIONS: tuple[str, ...] = (
    "unresolved",
    "keep_local",
    "keep_remote",
    "merged",
    "skip",
)
OPERATION_STATUS: tuple[str, ...] = ("planned", "running", "completed", "failed", "dry_run")


@dataclass(slots=True)
class ProgressReport:
    """Progress for a long-running sync operation."""

    operation: str
    stage: str
    current: int
    total: int
    message: str = ""
    percent: float = 0.0
    done: bool = False

    def as_dict(self) -> dict[str, Any]:
        percent = self.percent
        if self.total > 0 and percent <= 0:
            percent = round((self.current / self.total) * 100, 2)
        return {
            "operation": self.operation,
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "percent": percent,
            "done": self.done,
        }


@dataclass(slots=True)
class SyncOperation:
    """High level description of a planned or completed operation."""

    kind: str
    status: str
    source: str = ""
    destination: str = ""
    dry_run: bool = False
    format: str = "json"
    details: dict[str, Any] = field(default_factory=dict)
    progress: ProgressReport | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "source": self.source,
            "destination": self.destination,
            "dry_run": self.dry_run,
            "format": self.format,
            "details": dict(self.details),
            "progress": self.progress.as_dict() if self.progress is not None else None,
        }


@dataclass(slots=True)
class SnapshotRecord:
    """Portable record for one exported note."""

    id: int
    parent_id: int | None
    title: str
    kind: str
    content: str
    tags: str
    target: str
    status: str
    difficulty: str
    flag: str
    pinned: bool
    sort_order: int
    created_at: str
    updated_at: str
    deleted_at: str | None
    path: str
    checksum: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SnapshotRecord:
        return cls(
            id=int(data.get("id", 0)),
            parent_id=data.get("parent_id"),
            title=str(data.get("title", "")),
            kind=str(data.get("kind", "note")),
            content=str(data.get("content", "")),
            tags=str(data.get("tags", "")),
            target=str(data.get("target", "")),
            status=str(data.get("status", "todo")),
            difficulty=str(data.get("difficulty", "")),
            flag=str(data.get("flag", "")),
            pinned=bool(data.get("pinned", False)),
            sort_order=int(data.get("sort_order", 0)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            deleted_at=data.get("deleted_at"),
            path=str(data.get("path", "")),
            checksum=str(data.get("checksum", "")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "title": self.title,
            "kind": self.kind,
            "content": self.content,
            "tags": self.tags,
            "target": self.target,
            "status": self.status,
            "difficulty": self.difficulty,
            "flag": self.flag,
            "pinned": self.pinned,
            "sort_order": self.sort_order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "path": self.path,
            "checksum": self.checksum,
        }


@dataclass(slots=True)
class SnapshotBundle:
    """A portable snapshot containing notes and integrity metadata."""

    records: list[SnapshotRecord]
    manifest: dict[str, Any]
    source_path: str = ""
    format: str = "json"

    def as_dict(self) -> dict[str, Any]:
        return {
            "records": [record.as_dict() for record in self.records],
            "manifest": dict(self.manifest),
            "source_path": self.source_path,
            "format": self.format,
        }


@dataclass(slots=True)
class ChangeRecord:
    """A normalized change derived from a snapshot or vault state."""

    key: str
    action: str
    entity_type: str
    title: str
    path: str
    checksum: str = ""
    updated_at: str = ""
    local: dict[str, Any] | None = None
    remote: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "action": self.action,
            "entity_type": self.entity_type,
            "title": self.title,
            "path": self.path,
            "checksum": self.checksum,
            "updated_at": self.updated_at,
            "local": self.local,
            "remote": self.remote,
        }


@dataclass(slots=True)
class ConflictRecord:
    """A detected conflict between local and remote states."""

    key: str
    kind: str
    path: str
    title: str
    local_checksum: str = ""
    remote_checksum: str = ""
    local_updated_at: str = ""
    remote_updated_at: str = ""
    resolution: str = "unresolved"
    details: dict[str, Any] = field(default_factory=dict)
    suggested: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "path": self.path,
            "title": self.title,
            "local_checksum": self.local_checksum,
            "remote_checksum": self.remote_checksum,
            "local_updated_at": self.local_updated_at,
            "remote_updated_at": self.remote_updated_at,
            "resolution": self.resolution,
            "details": dict(self.details),
            "suggested": self.suggested,
        }


@dataclass(slots=True)
class DryRunReport:
    """Result of a dry-run plan."""

    operation: str
    valid: bool
    summary: dict[str, Any]
    changes: list[ChangeRecord] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    progress: ProgressReport | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "valid": self.valid,
            "summary": dict(self.summary),
            "changes": [change.as_dict() for change in self.changes],
            "conflicts": [conflict.as_dict() for conflict in self.conflicts],
            "warnings": list(self.warnings),
            "progress": self.progress.as_dict() if self.progress is not None else None,
        }


@dataclass(slots=True)
class BackupPlan:
    destination: str
    include_settings: bool = True
    include_deleted: bool = False
    include_snippets: bool = True
    include_manifest: bool = True
    include_history: bool = False
    format: str = "sqlite"
    dry_run: bool = False
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "include_settings": self.include_settings,
            "include_deleted": self.include_deleted,
            "include_snippets": self.include_snippets,
            "include_manifest": self.include_manifest,
            "include_history": self.include_history,
            "format": self.format,
            "dry_run": self.dry_run,
            "label": self.label,
        }


@dataclass(slots=True)
class RestorePlan:
    source: str
    mode: str = "replace"
    verify_checksums: bool = True
    dry_run: bool = False
    allow_incompatible: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "mode": self.mode,
            "verify_checksums": self.verify_checksums,
            "dry_run": self.dry_run,
            "allow_incompatible": self.allow_incompatible,
        }


@dataclass(slots=True)
class ExportPlan:
    destination: str
    format: str = "json"
    include_deleted: bool = False
    include_settings: bool = False
    dry_run: bool = False
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "format": self.format,
            "include_deleted": self.include_deleted,
            "include_settings": self.include_settings,
            "dry_run": self.dry_run,
            "label": self.label,
        }


@dataclass(slots=True)
class ImportPlan:
    source: str
    format: str = "auto"
    strategy: str = "merge"
    verify_checksums: bool = True
    dry_run: bool = False
    parent_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "format": self.format,
            "strategy": self.strategy,
            "verify_checksums": self.verify_checksums,
            "dry_run": self.dry_run,
            "parent_id": self.parent_id,
        }


@dataclass(slots=True)
class BackupResult:
    plan: BackupPlan
    path: str
    manifest: dict[str, Any]
    checksum: str
    bytes_written: int
    dry_run: bool
    progress: list[ProgressReport] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.as_dict(),
            "path": self.path,
            "manifest": dict(self.manifest),
            "checksum": self.checksum,
            "bytes_written": self.bytes_written,
            "dry_run": self.dry_run,
            "progress": [item.as_dict() for item in self.progress],
        }


@dataclass(slots=True)
class RestoreResult:
    plan: RestorePlan
    restored_path: str
    manifest: dict[str, Any]
    verified: bool
    dry_run: bool
    warnings: list[str] = field(default_factory=list)
    progress: list[ProgressReport] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.as_dict(),
            "restored_path": self.restored_path,
            "manifest": dict(self.manifest),
            "verified": self.verified,
            "dry_run": self.dry_run,
            "warnings": list(self.warnings),
            "progress": [item.as_dict() for item in self.progress],
        }


@dataclass(slots=True)
class MergeResult:
    strategy: str
    applied: list[ChangeRecord] = field(default_factory=list)
    skipped: list[ChangeRecord] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "applied": [item.as_dict() for item in self.applied],
            "skipped": [item.as_dict() for item in self.skipped],
            "conflicts": [item.as_dict() for item in self.conflicts],
            "dry_run": self.dry_run,
            "counts": {
                "applied": len(self.applied),
                "skipped": len(self.skipped),
                "conflicts": len(self.conflicts),
            },
        }
