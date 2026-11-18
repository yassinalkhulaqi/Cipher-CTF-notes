"""Dry-run planning helpers for sync operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.sync.backup import BackupService
from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.conflicts import ConflictDetector
from redscribe.v2.sync.errors import ValidationError
from redscribe.v2.sync.exporter import ExportPipeline
from redscribe.v2.sync.importer import ImportPipeline
from redscribe.v2.sync.migration import MigrationCompatibility
from redscribe.v2.sync.models import DryRunReport
from redscribe.v2.sync.progress import ProgressTracker
from redscribe.v2.sync.restore import RestoreService


@dataclass(slots=True)
class DryRunPlanner:
    """Build dry-run reports for backup, restore, export, and import flows."""

    vault: Vault

    def backup(self, **kwargs: Any) -> DryRunReport:
        tracker = ProgressTracker("backup.dry_run")
        tracker.report("plan", 0, 2, "planning backup")
        service = BackupService(self.vault)
        params = dict(kwargs)
        params.pop("dry_run", None)
        plan = service.planner.build(dry_run=True, **params)
        description = service.planner.describe(self.vault, plan)
        tracker.report("complete", 2, 2, "backup dry run complete", done=True)
        return DryRunReport(
            operation="backup",
            valid=True,
            summary={"plan": plan.as_dict(), "description": description},
            warnings=[],
            progress=tracker.latest(),
        )

    def restore(self, **kwargs: Any) -> DryRunReport:
        tracker = ProgressTracker("restore.dry_run")
        tracker.report("inspect", 0, 2, "inspecting restore")
        service = RestoreService(self.vault)
        params = dict(kwargs)
        params.pop("dry_run", None)
        plan = service.planner.build(dry_run=True, **params)
        inspection = service.inspect(plan)
        compatibility = inspection.get("compatibility") if isinstance(inspection, dict) else None
        warnings: list[str] = []
        valid = True
        if isinstance(compatibility, dict):
            warnings.extend(str(item) for item in compatibility.get("warnings", []))
            if not compatibility.get("compatible", False):
                valid = False
                warnings.extend(str(item) for item in compatibility.get("errors", []))
        tracker.report("complete", 2, 2, "restore dry run complete", done=True)
        return DryRunReport(
            operation="restore",
            valid=valid,
            summary={"plan": plan.as_dict(), "inspection": inspection},
            warnings=warnings,
            progress=tracker.latest(),
        )

    def export(self, **kwargs: Any) -> DryRunReport:
        tracker = ProgressTracker("export.dry_run")
        tracker.report("plan", 0, 2, "planning export")
        pipeline = ExportPipeline(self.vault)
        params = dict(kwargs)
        params.pop("dry_run", None)
        plan = pipeline.plan(dry_run=True, **params)
        journal = ChangeJournal()
        records = journal.capture_vault(self.vault, include_deleted=plan.include_deleted)
        tracker.report("complete", 2, 2, "export dry run complete", done=True)
        return DryRunReport(
            operation="export",
            valid=True,
            summary={
                "plan": plan.as_dict(),
                "records": len(records),
                "notes": sum(1 for item in records if item.get("kind") == "note"),
            },
            warnings=[],
            progress=tracker.latest(),
        )

    def import_plan(self, **kwargs: Any) -> DryRunReport:
        tracker = ProgressTracker("import.dry_run")
        tracker.report("load", 0, 3, "loading import source")
        pipeline = ImportPipeline(self.vault)
        params = dict(kwargs)
        params.pop("dry_run", None)
        plan = pipeline.plan(dry_run=True, **params)
        local = ChangeJournal().capture_vault(self.vault)
        remote = pipeline.load_records(plan)
        tracker.report("diff", 1, 3, "detecting changes")
        journal = ChangeJournal()
        changes = [item for item in journal.build(local, remote) if item.action != "unchanged"]
        conflicts = ConflictDetector().detect(local, remote)
        tracker.report("complete", 3, 3, "import dry run complete", done=True)
        return DryRunReport(
            operation="import",
            valid=True,
            summary={
                "plan": plan.as_dict(),
                "local_records": len(local),
                "remote_records": len(remote),
                "changes": len(changes),
                "conflicts": len(conflicts),
            },
            changes=changes,
            conflicts=conflicts,
            warnings=[],
            progress=tracker.latest(),
        )

    def migration(self, manifest: Mapping[str, Any]) -> DryRunReport:
        tracker = ProgressTracker("migration.dry_run")
        tracker.report("check", 0, 2, "checking compatibility")
        compatibility = MigrationCompatibility()
        report = compatibility.check_manifest(manifest)
        plan = compatibility.migration_plan(manifest)
        tracker.report("complete", 2, 2, "migration check complete", done=True)
        return DryRunReport(
            operation="migration",
            valid=report.compatible,
            summary={"compatibility": report.as_dict(), "plan": plan},
            warnings=list(report.warnings),
            progress=tracker.latest(),
        )

    def from_operation(self, operation: str, payload: Mapping[str, Any]) -> DryRunReport:
        op = operation.strip().lower()
        if op == "backup":
            return self.backup(**dict(payload))
        if op == "restore":
            return self.restore(**dict(payload))
        if op == "export":
            return self.export(**dict(payload))
        if op == "import":
            return self.import_plan(**dict(payload))
        if op == "migration":
            manifest = payload.get("manifest")
            if not isinstance(manifest, Mapping):
                raise ValidationError("migration dry run requires a manifest object")
            return self.migration(manifest)
        raise ValidationError(f"Unsupported dry-run operation: {operation}")
