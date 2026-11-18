from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.storage.db import Vault
from redscribe.v2.sync.backup import BackupService
from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.conflicts import ConflictDetector
from redscribe.v2.sync.exporter import ExportPipeline
from redscribe.v2.sync.importer import ImportPipeline
from redscribe.v2.sync.merge import MergeEngine
from redscribe.v2.sync.restore import RestoreService
from redscribe.v2.sync.service import SyncService


@pytest.fixture
def vault(tmp_path: Path):
    db = Vault(tmp_path / "vault.db")
    try:
        folder = db.create_node("Folder", kind="folder")
        db.create_node("One", folder.id, content="one", tags="web")
        db.create_node("Two", folder.id, content="two", tags="api", target="svc")
        yield db
    finally:
        db.close()


def test_snapshot_export_and_import_roundtrip_json(vault: Vault, tmp_path: Path) -> None:
    service = SyncService(vault)
    snapshot = service.snapshot()
    assert snapshot["manifest"]["record_count"] >= 2
    export_path = tmp_path / "snapshot.json"
    export = service.export_run({"destination": str(export_path), "format": "json"})
    assert Path(export["path"]).is_file()
    assert export["manifest"]["format"] == "json"

    target = Vault(tmp_path / "target.db")
    try:
        target_service = SyncService(target)
        preview = target_service.import_plan(
            {"source": str(export_path), "format": "json", "strategy": "merge"}
        )
        assert preview["dry_run"] is True
        result = target_service.import_run(
            {"source": str(export_path), "format": "json", "strategy": "merge"}
        )
        assert result["dry_run"] is False
        assert len(target.live_nodes()) >= 1
    finally:
        target.close()


def test_backup_inspect_and_restore_dry_run(vault: Vault, tmp_path: Path) -> None:
    backup = BackupService(vault)
    plan = backup.planner.build(
        destination=tmp_path / "b.db", format="sqlite", include_settings=True
    )
    result = backup.create(plan)
    assert Path(result.path).is_file()
    inspected = backup.inspect(result.path)
    assert inspected["format"] == "sqlite"
    assert inspected["counts"]["nodes"] >= 1

    restore = RestoreService(vault)
    restore_plan = restore.planner.build(source=result.path, dry_run=True, mode="inspect")
    dry = restore.restore(restore_plan)
    assert dry.dry_run is True
    assert dry.verified is True


def test_conflict_detection_merge_and_journal(vault: Vault) -> None:
    service = SyncService(vault)
    local = service.journal.capture_vault(vault)
    remote = [dict(item) for item in local]
    remote[0]["content"] = "changed"
    remote[0]["updated_at"] = "2030-01-01T00:00:00Z"
    remote[0]["checksum"] = "different"
    journal = ChangeJournal()
    changes = journal.build(local, remote)
    assert any(item.action == "update" for item in changes)
    conflicts = ConflictDetector().detect(local, remote)
    assert conflicts
    preview = MergeEngine(strategy="merge").preview(local, remote)
    assert preview["dry_run"] is True
    detected = service.detect_conflicts(remote=remote)
    assert detected["summary"]["conflicts"] >= 1
    diff = service.diff_journal(remote=remote)
    assert diff["summary"]["total"] >= len(local)


def test_markdown_export_and_import_pipeline(vault: Vault, tmp_path: Path) -> None:
    exporter = ExportPipeline(vault)
    plan = exporter.plan(destination=tmp_path / "notes", format="markdown")
    export = exporter.export(plan)
    assert Path(export["path"]).is_dir()
    target = Vault(tmp_path / "md.db")
    try:
        importer = ImportPipeline(target)
        import_plan = importer.plan(source=str(export["path"]), format="markdown", strategy="merge")
        preview = importer.preview(import_plan)
        assert preview["dry_run"] is True
        result = importer.run(import_plan)
        assert result["dry_run"] is False
    finally:
        target.close()


def test_dry_run_migration_and_progress_reports(vault: Vault) -> None:
    service = SyncService(vault)
    backup_dry = service.dry_run("backup", {"destination": "x.db", "format": "sqlite"})
    assert backup_dry["operation"] == "backup"
    assert backup_dry["valid"] is True
    migration = service.migration_check(
        {"manifest_version": "1.0", "schema_version": 4, "record_count": 1}
    )
    assert migration["compatibility"]["compatible"] is True
    progress = service.progress_report([{"stage": "scan"}, {"stage": "write", "message": "done"}])
    assert progress["summary"]["stages"] == 2
