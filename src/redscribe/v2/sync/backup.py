"""Backup planning and execution for sync and portability."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redscribe.domain.utils import utc_now
from redscribe.storage.db import Vault
from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.checksums import checksum_file, checksum_json
from redscribe.v2.sync.errors import ValidationError
from redscribe.v2.sync.manifest import SnapshotManifest
from redscribe.v2.sync.models import BackupPlan, BackupResult
from redscribe.v2.sync.progress import ProgressCallback, ProgressTracker


def _resolve_destination(destination: str | Path, *, suffix: str = ".db") -> Path:
    target = Path(destination).expanduser()
    if not str(target):
        raise ValidationError("Backup destination is required")
    if target.exists() and target.is_dir():
        stamp = utc_now().replace(":", "").replace("-", "")
        target = target / f"redscribe-backup-{stamp}{suffix}"
    if target.suffix == "":
        target = target.with_suffix(suffix)
    return target


def _manifest_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".manifest.json")


@dataclass(slots=True)
class BackupPlanner:
    """Build normalized backup plans and dry-run summaries."""

    def build(
        self,
        *,
        destination: str | Path,
        include_settings: bool = True,
        include_deleted: bool = False,
        include_snippets: bool = True,
        include_manifest: bool = True,
        include_history: bool = False,
        format_name: str = "sqlite",
        format: str | None = None,  # noqa: A002
        dry_run: bool = False,
        label: str = "",
    ) -> BackupPlan:
        fmt = (format if format is not None else format_name).strip().lower() or "sqlite"
        if fmt not in {"sqlite", "json"}:
            raise ValidationError(f"Unsupported backup format: {fmt}")
        path = _resolve_destination(destination, suffix=".db" if fmt == "sqlite" else ".json")
        return BackupPlan(
            destination=str(path),
            include_settings=include_settings,
            include_deleted=include_deleted,
            include_snippets=include_snippets,
            include_manifest=include_manifest,
            include_history=include_history,
            format=fmt,
            dry_run=dry_run,
            label=label.strip(),
        )

    def describe(self, vault: Vault, plan: BackupPlan) -> dict[str, Any]:
        journal = ChangeJournal()
        records = journal.capture_vault(vault, include_deleted=plan.include_deleted)
        snippets = vault.list_custom_snippets() if plan.include_snippets else []
        settings_count = 0
        if plan.include_settings:
            row = vault.connection.execute("SELECT COUNT(*) FROM settings").fetchone()
            settings_count = int(row[0]) if row is not None else 0
        history_count = 0
        if plan.include_history:
            row = vault.connection.execute("SELECT COUNT(*) FROM nodes_history").fetchone()
            history_count = int(row[0]) if row is not None else 0
        return {
            "destination": plan.destination,
            "format": plan.format,
            "records": len(records),
            "notes": sum(1 for item in records if item.get("kind") == "note"),
            "folders": sum(1 for item in records if item.get("kind") == "folder"),
            "snippets": len(snippets),
            "settings": settings_count,
            "history": history_count,
            "include_deleted": plan.include_deleted,
            "manifest_path": str(_manifest_path(Path(plan.destination)))
            if plan.include_manifest
            else "",
        }


class BackupService:
    """Create backup artifacts and manifests."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self.planner = BackupPlanner()

    def create(
        self,
        plan: BackupPlan,
        *,
        progress: ProgressCallback | None = None,
    ) -> BackupResult:
        tracker = ProgressTracker("backup", callback=progress)
        tracker.report("plan", 0, 4, "planning backup")
        description = self.planner.describe(self.vault, plan)
        target = Path(plan.destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest = SnapshotManifest.build(
            source=self.vault.display_path,
            format_name=plan.format,
            records=ChangeJournal().capture_vault(self.vault, include_deleted=plan.include_deleted),
            files={},
            metadata={
                "label": plan.label,
                "include_settings": plan.include_settings,
                "include_deleted": plan.include_deleted,
                "include_snippets": plan.include_snippets,
                "include_history": plan.include_history,
                "counts": description,
            },
        )
        if plan.dry_run:
            tracker.report("plan", 4, 4, "dry run complete", done=True)
            return BackupResult(
                plan=plan,
                path=str(target),
                manifest=manifest.as_dict(),
                checksum="",
                bytes_written=0,
                dry_run=True,
                progress=tracker.reports,
            )

        tracker.report("snapshot", 1, 4, "creating snapshot")
        bytes_written = 0
        checksum = ""
        if plan.format == "sqlite":
            bytes_written, checksum = self._write_sqlite_backup(target, tracker)
        else:
            bytes_written, checksum = self._write_json_backup(target, plan, tracker)

        if plan.include_manifest:
            tracker.report("manifest", 3, 4, "writing manifest")
            manifest.files = {target.name: checksum}
            manifest.metadata["counts"] = description
            manifest.digest = manifest.compute_digest()
            _manifest_path(target).write_text(
                json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        tracker.report("complete", 4, 4, "backup complete", done=True)
        return BackupResult(
            plan=plan,
            path=str(target),
            manifest=manifest.as_dict(),
            checksum=checksum,
            bytes_written=bytes_written,
            dry_run=False,
            progress=tracker.reports,
        )

    def _write_sqlite_backup(self, target: Path, tracker: ProgressTracker) -> tuple[int, str]:
        tracker.report("write", 2, 4, "copying vault database")
        self.vault.backup_to(target)
        checksum = checksum_file(target)
        return target.stat().st_size, checksum

    def _write_json_backup(
        self, target: Path, plan: BackupPlan, tracker: ProgressTracker
    ) -> tuple[int, str]:
        tracker.report("write", 2, 4, "serializing portable backup")
        records = ChangeJournal().capture_vault(self.vault, include_deleted=plan.include_deleted)
        payload: dict[str, Any] = {
            "format": "redscribe.backup.json",
            "created_at": utc_now(),
            "records": records,
        }
        if plan.include_snippets:
            payload["snippets"] = [
                snippet.__dict__ for snippet in self.vault.list_custom_snippets()
            ]
        if plan.include_settings:
            rows = self.vault.connection.execute(
                "SELECT key, value FROM settings ORDER BY key"
            ).fetchall()
            payload["settings"] = {str(row["key"]): str(row["value"]) for row in rows}
        if plan.include_history:
            rows = self.vault.connection.execute(
                "SELECT id, node_id, title, content, tags, target, status, "
                "difficulty, flag, created_at FROM nodes_history ORDER BY id"
            ).fetchall()
            payload["history"] = [dict(row) for row in rows]
        text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
        target.write_text(text, encoding="utf-8")
        return len(text.encode("utf-8")), checksum_json(payload)

    def inspect(self, path: str | Path) -> dict[str, Any]:
        source = Path(path).expanduser()
        if not source.exists():
            raise ValidationError(f"Backup path does not exist: {source}")
        manifest_file = _manifest_path(source)
        manifest = SnapshotManifest.read(manifest_file).as_dict() if manifest_file.is_file() else {}
        info: dict[str, Any] = {
            "path": str(source),
            "exists": source.is_file(),
            "size": source.stat().st_size if source.is_file() else 0,
            "manifest": manifest,
            "manifest_path": str(manifest_file) if manifest_file.is_file() else "",
        }
        if source.suffix.lower() == ".db" and source.is_file():
            info.update(self._inspect_sqlite(source))
        elif source.suffix.lower() == ".json" and source.is_file():
            info.update(self._inspect_json(source))
        return info

    def _inspect_sqlite(self, path: Path) -> dict[str, Any]:
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            counts = {}
            for table in ("nodes", "snippets", "settings", "entity_events", "nodes_history"):
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                    (table,),
                ).fetchone()
                if exists is None:
                    counts[table] = 0
                    continue
                row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row is not None else 0
            return {
                "format": "sqlite",
                "schema_version": version,
                "counts": counts,
                "checksum": checksum_file(path),
            }
        finally:
            connection.close()

    def _inspect_json(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Backup JSON is invalid: {path}") from exc
        records = payload.get("records", []) if isinstance(payload, dict) else []
        snippets = payload.get("snippets", []) if isinstance(payload, dict) else []
        settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
        history = payload.get("history", []) if isinstance(payload, dict) else []
        return {
            "format": "json",
            "schema_version": int(payload.get("schema_version", 0) or 0)
            if isinstance(payload, dict)
            else 0,
            "counts": {
                "nodes": len(records) if isinstance(records, list) else 0,
                "snippets": len(snippets) if isinstance(snippets, list) else 0,
                "settings": len(settings) if isinstance(settings, dict) else 0,
                "history": len(history) if isinstance(history, list) else 0,
            },
            "checksum": checksum_file(path),
        }


def create_quick_backup(vault: Vault, directory: str | Path) -> BackupResult:
    """Convenience helper for callers that want a sqlite backup now."""
    service = BackupService(vault)
    plan = service.planner.build(destination=directory, format="sqlite")
    return service.create(plan)
