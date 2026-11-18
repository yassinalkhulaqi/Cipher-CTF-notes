"""Restore planning and execution."""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.sync.backup import BackupService
from redscribe.v2.sync.checksums import checksum_file
from redscribe.v2.sync.errors import ValidationError
from redscribe.v2.sync.manifest import SnapshotManifest
from redscribe.v2.sync.migration import MigrationCompatibility
from redscribe.v2.sync.models import RestorePlan, RestoreResult
from redscribe.v2.sync.progress import ProgressCallback, ProgressTracker


@dataclass(slots=True)
class RestorePlanner:
    """Normalize restore plans and describe compatibility."""

    def build(
        self,
        *,
        source: str | Path,
        mode: str = "replace",
        verify_checksums: bool = True,
        dry_run: bool = False,
        allow_incompatible: bool = False,
    ) -> RestorePlan:
        normalized_mode = mode.strip().lower() or "replace"
        if normalized_mode not in {"replace", "inspect"}:
            raise ValidationError(f"Unsupported restore mode: {normalized_mode}")
        path = Path(source).expanduser()
        if not str(path):
            raise ValidationError("Restore source is required")
        return RestorePlan(
            source=str(path),
            mode=normalized_mode,
            verify_checksums=verify_checksums,
            dry_run=dry_run,
            allow_incompatible=allow_incompatible,
        )

    def inspect(self, vault: Vault, plan: RestorePlan) -> dict[str, Any]:
        backup = BackupService(vault)
        info = backup.inspect(plan.source)
        manifest = info.get("manifest") or {}
        compatibility = None
        if isinstance(manifest, dict) and manifest:
            compatibility = MigrationCompatibility().check_manifest(manifest).as_dict()
        elif info.get("format") == "sqlite":
            schema_version = int(info.get("schema_version", 0) or 0)
            pseudo = {
                "manifest_version": "1.0",
                "schema_version": schema_version,
                "app_version": "",
                "record_count": int(info.get("counts", {}).get("nodes", 0)),
            }
            if schema_version > 0:
                compatibility = MigrationCompatibility().check_manifest(pseudo).as_dict()
        info["compatibility"] = compatibility
        info["plan"] = plan.as_dict()
        return info


class RestoreService:
    """Restore sqlite backups and portable JSON snapshots."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self.planner = RestorePlanner()
        self.backup = BackupService(vault)

    def inspect(self, plan: RestorePlan) -> dict[str, Any]:
        return self.planner.inspect(self.vault, plan)

    def restore(
        self,
        plan: RestorePlan,
        *,
        progress: ProgressCallback | None = None,
    ) -> RestoreResult:
        tracker = ProgressTracker("restore", callback=progress)
        tracker.report("inspect", 0, 4, "inspecting restore source")
        inspection = self.inspect(plan)
        source = Path(plan.source)
        if not source.exists():
            raise ValidationError(f"Restore source does not exist: {source}")
        manifest_data = (
            inspection.get("manifest") if isinstance(inspection.get("manifest"), dict) else {}
        )
        compatibility = (
            inspection.get("compatibility")
            if isinstance(inspection.get("compatibility"), dict)
            else None
        )
        warnings: list[str] = []
        if compatibility and not compatibility.get("compatible", False):
            if not plan.allow_incompatible:
                raise ValidationError(
                    "Restore source is not compatible",
                    details=compatibility,
                )
            warnings.extend(str(item) for item in compatibility.get("errors", []))

        if plan.verify_checksums and isinstance(manifest_data, dict) and manifest_data:
            tracker.report("verify", 1, 4, "verifying manifest checksums")
            manifest = SnapshotManifest.from_dict(manifest_data)
            if source.name in manifest.files:
                actual = checksum_file(source)
                expected = manifest.files[source.name]
                if actual != expected:
                    raise ValidationError(
                        "Restore checksum mismatch",
                        details={"expected": expected, "actual": actual},
                    )

        if plan.dry_run or plan.mode == "inspect":
            tracker.report("complete", 4, 4, "dry run complete", done=True)
            return RestoreResult(
                plan=plan,
                restored_path=str(source),
                manifest=manifest_data if isinstance(manifest_data, dict) else {},
                verified=bool(plan.verify_checksums),
                dry_run=True,
                warnings=warnings,
                progress=tracker.reports,
            )

        tracker.report("apply", 2, 4, "restoring backup")
        restored_path = self._apply(source)
        tracker.report("complete", 4, 4, "restore complete", done=True)
        return RestoreResult(
            plan=plan,
            restored_path=str(restored_path),
            manifest=manifest_data if isinstance(manifest_data, dict) else {},
            verified=bool(plan.verify_checksums),
            dry_run=False,
            warnings=warnings,
            progress=tracker.reports,
        )

    def _apply(self, source: Path) -> Path:
        if source.suffix.lower() == ".db":
            if self.vault.path is None:
                raise ValidationError("Cannot restore a sqlite backup into an in-memory vault")
            self.vault.close()
            target = self.vault.path
            shutil.copy2(source, target)
            wal = Path(str(source) + "-wal")
            shm = Path(str(source) + "-shm")
            for sidecar in (Path(str(target) + "-wal"), Path(str(target) + "-shm")):
                if sidecar.exists():
                    sidecar.unlink()
            if wal.exists():
                shutil.copy2(wal, Path(str(target) + "-wal"))
            if shm.exists():
                shutil.copy2(shm, Path(str(target) + "-shm"))
            self.vault.__init__(target)  # type: ignore[misc]
            return target
        if source.suffix.lower() == ".json":
            return self._restore_json(source)
        raise ValidationError(f"Unsupported restore source format: {source.suffix}")

    def _restore_json(self, source: Path) -> Path:
        payload = json.loads(source.read_text(encoding="utf-8"))
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            raise ValidationError("Portable backup JSON is missing records")
        with self.vault.connection:
            self.vault.connection.execute("DELETE FROM nodes")
            self.vault.connection.execute("DELETE FROM sqlite_sequence WHERE name = 'nodes'")
        for record in sorted(
            records, key=lambda item: (int(item.get("sort_order", 0)), int(item.get("id", 0)))
        ):
            if not isinstance(record, dict):
                continue
            self.vault.connection.execute(
                "INSERT INTO nodes("
                "id, parent_id, title, kind, content, tags, target, status, "
                "difficulty, flag, pinned, sort_order, created_at, updated_at, deleted_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.get("id"),
                    record.get("parent_id"),
                    str(record.get("title", "Untitled")),
                    str(record.get("kind", "note")),
                    str(record.get("content", "")),
                    str(record.get("tags", "")),
                    str(record.get("target", "")),
                    str(record.get("status", "todo")),
                    str(record.get("difficulty", "")),
                    str(record.get("flag", "")),
                    int(bool(record.get("pinned", False))),
                    int(record.get("sort_order", 0) or 0),
                    str(record.get("created_at", "")),
                    str(record.get("updated_at", "")),
                    record.get("deleted_at"),
                ),
            )
        self.vault.connection.commit()
        with contextlib.suppress(Exception):
            self.vault.rebuild_search_index()
        return self.vault.path or Path(self.vault.display_path)


def verify_sqlite_backup(path: str | Path) -> dict[str, Any]:
    """Run a quick integrity check on a sqlite backup file."""
    source = Path(path)
    if not source.is_file():
        raise ValidationError(f"Backup file does not exist: {source}")
    connection = sqlite3.connect(str(source))
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        result = str(row[0]) if row is not None else "unknown"
        return {"ok": result == "ok", "result": result, "path": str(source)}
    finally:
        connection.close()
