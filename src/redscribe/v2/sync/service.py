"""High-level sync and portability service."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from redscribe.storage.db import Vault
from redscribe.v2.sync.backup import BackupService
from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.checksums import ChecksumVerifier, checksum_file
from redscribe.v2.sync.conflicts import ConflictDetector, ConflictResolver
from redscribe.v2.sync.dry_run import DryRunPlanner
from redscribe.v2.sync.errors import ValidationError
from redscribe.v2.sync.exporter import ExportPipeline
from redscribe.v2.sync.importer import ImportPipeline
from redscribe.v2.sync.manifest import SnapshotManifest
from redscribe.v2.sync.merge import MergeEngine
from redscribe.v2.sync.migration import MigrationCompatibility
from redscribe.v2.sync.progress import ProgressTracker, progress_summary
from redscribe.v2.sync.restore import RestoreService
from redscribe.v2.sync.version_vectors import VersionVector, compare_vectors


class SyncService:
    """Facade used by API handlers and tests."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self.backups = BackupService(vault)
        self.restores = RestoreService(vault)
        self.exports = ExportPipeline(vault)
        self.imports = ImportPipeline(vault)
        self.dry_runs = DryRunPlanner(vault)
        self.journal = ChangeJournal()
        self.conflicts = ConflictDetector()
        self.resolver = ConflictResolver()
        self.migrations = MigrationCompatibility()

    def health(self) -> dict[str, Any]:
        journal = self.journal.capture_vault(self.vault)
        return {
            "ok": True,
            "namespace": "sync",
            "records": len(journal),
            "formats": ["json", "markdown", "html", "sqlite"],
            "strategies": ["skip", "prefer_local", "prefer_remote", "merge"],
            "vault": self.vault.display_path,
            "schema_version": self.vault.schema_version,
        }

    def snapshot(self, *, include_deleted: bool = False) -> dict[str, Any]:
        records = self.journal.capture_vault(self.vault, include_deleted=include_deleted)
        manifest = SnapshotManifest.build(
            source=self.vault.display_path,
            format_name="json",
            records=records,
            metadata={"include_deleted": include_deleted},
        )
        return {"manifest": manifest.as_dict(), "records": records}

    def backup_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.backups.planner.build(**dict(payload))
        return {
            "plan": plan.as_dict(),
            "description": self.backups.planner.describe(self.vault, plan),
        }

    def backup_create(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.backups.planner.build(**dict(payload))
        result = self.backups.create(plan)
        return result.as_dict()

    def backup_inspect(self, path: str) -> dict[str, Any]:
        return self.backups.inspect(path)

    def restore_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.restores.planner.build(**dict(payload))
        return {"plan": plan.as_dict(), "inspection": self.restores.inspect(plan)}

    def restore_apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.restores.planner.build(**dict(payload))
        result = self.restores.restore(plan)
        return result.as_dict()

    def export_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.exports.plan(**dict(payload))
        report = self.dry_runs.export(**dict(payload))
        return {"plan": plan.as_dict(), "dry_run": report.as_dict()}

    def export_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.exports.plan(**dict(payload))
        return self.exports.export(plan)

    def import_plan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.imports.plan(**dict(payload))
        return self.imports.preview(plan)

    def import_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan = self.imports.plan(**dict(payload))
        resolutions = payload.get("resolutions")
        resolved = dict(resolutions) if isinstance(resolutions, Mapping) else {}
        return self.imports.run(plan, resolutions=resolved)

    def dry_run(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        report = self.dry_runs.from_operation(operation, payload)
        return report.as_dict()

    def verify_checksums(
        self,
        *,
        expected: Mapping[str, Any] | None = None,
        actual: Mapping[str, Any] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        verifier = ChecksumVerifier()
        if path:
            source = Path(path)
            if source.is_dir():
                files = {
                    str(p.relative_to(source)).replace("\\", "/"): checksum_file(p)
                    for p in sorted(source.rglob("*"))
                    if p.is_file()
                }
                return {"path": str(source), "files": files, "count": len(files)}
            if source.is_file():
                digest = checksum_file(source)
                if expected:
                    verifier.require(
                        {
                            "file": str(next(iter(expected.values())))
                            if len(expected) == 1
                            else digest
                        },
                        {"file": digest},
                    )
                return {"path": str(source), "checksum": digest}
            raise ValidationError(f"Checksum path does not exist: {source}")
        report = verifier.compare(expected or {}, actual or {}, allow_extra=True)
        return report.as_dict()

    def detect_conflicts(
        self,
        *,
        remote: list[dict[str, Any]] | None = None,
        source: str | None = None,
        strategy: str = "merge",
    ) -> dict[str, Any]:
        local = self.journal.capture_vault(self.vault)
        remote_records = self._load_remote(remote=remote, source=source)
        journal = ChangeJournal()
        changes = [
            item for item in journal.build(local, remote_records) if item.action != "unchanged"
        ]
        conflicts = self.conflicts.detect(local, remote_records)
        self.resolver.resolve(conflicts, strategy=strategy)
        return {
            "changes": [item.as_dict() for item in changes],
            "conflicts": [item.as_dict() for item in conflicts],
            "summary": {
                "changes": len(changes),
                "conflicts": len(conflicts),
                "resolutions": self.resolver.summary(conflicts),
            },
        }

    def resolve_conflicts(
        self,
        *,
        remote: list[dict[str, Any]] | None = None,
        source: str | None = None,
        resolutions: Mapping[str, str] | None = None,
        strategy: str = "merge",
    ) -> dict[str, Any]:
        local = self.journal.capture_vault(self.vault)
        remote_records = self._load_remote(remote=remote, source=source)
        conflicts = self.conflicts.detect(local, remote_records)
        self.resolver.resolve(conflicts, resolutions=resolutions or {}, strategy=strategy)
        return {
            "conflicts": [item.as_dict() for item in conflicts],
            "summary": self.resolver.summary(conflicts),
        }

    def merge_preview(
        self,
        *,
        remote: list[dict[str, Any]] | None = None,
        source: str | None = None,
        strategy: str = "merge",
        resolutions: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        local = self.journal.capture_vault(self.vault)
        remote_records = self._load_remote(remote=remote, source=source)
        engine = MergeEngine(strategy=strategy)
        return engine.preview(local, remote_records, resolutions=resolutions or {})

    def diff_journal(
        self,
        *,
        remote: list[dict[str, Any]] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        local = self.journal.capture_vault(self.vault)
        remote_records = self._load_remote(remote=remote, source=source)
        journal = ChangeJournal()
        journal.build(local, remote_records)
        return journal.as_dict()

    def compare_vectors(
        self,
        local: Mapping[str, Any] | None,
        remote: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        left = VersionVector.from_dict(local)
        right = VersionVector.from_dict(remote)
        return {
            "local": left.as_dict(),
            "remote": right.as_dict(),
            "relation": compare_vectors(left, right),
            "merged": left.copy().merge(right).as_dict(),
        }

    def migration_check(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        report = self.migrations.check_manifest(manifest)
        return {
            "compatibility": report.as_dict(),
            "plan": self.migrations.migration_plan(manifest),
            "supported": self.migrations.supported_versions(),
        }

    def progress_report(self, steps: list[Mapping[str, Any]]) -> dict[str, Any]:
        tracker = ProgressTracker("sync.progress")
        total = len(steps)
        for index, step in enumerate(steps, start=1):
            stage = str(step.get("stage", f"step-{index}"))
            message = str(step.get("message", ""))
            tracker.report(stage, index, total, message, done=index == total)
        return {
            "reports": tracker.as_dicts(),
            "summary": progress_summary(tracker.reports),
        }

    def _load_remote(
        self,
        *,
        remote: list[dict[str, Any]] | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        if remote is not None:
            return [dict(item) for item in remote if isinstance(item, dict)]
        if source:
            plan = self.imports.plan(source=source, format="auto", dry_run=True)
            return self.imports.load_records(plan)
        return []
