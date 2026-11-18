from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.namespaces import sync as sync_namespace
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2


def _router(vault: Vault) -> V2Router:
    api = ApiV2(vault)
    sync_namespace.register(api)
    return V2Router(vault, api)


def _data(response):
    assert response["ok"] is True
    return response["data"]


@pytest.fixture
def vault(tmp_path: Path):
    db = Vault(tmp_path / "vault.db")
    try:
        db.create_node("Alpha", content="alpha", tags="web", target="app")
        db.create_node("Beta", content="beta", tags="api", target="api")
        yield db
    finally:
        db.close()


def test_register_exposes_sync_routes(vault: Vault) -> None:
    api = ApiV2(vault)
    namespace = sync_namespace.register(api)
    names = sync_namespace.route_names()
    assert namespace.routes()
    assert set(names) <= set(api.routes)
    assert "sync.health" in api.routes
    assert "sync.backup.create" in api.routes
    assert "sync.import.run" in api.routes
    assert "sync.conflicts.session.create" in api.routes
    assert len(api.routes) == len(set(api.routes))


def test_health_snapshot_and_portability_routes(vault: Vault, tmp_path: Path) -> None:
    router = _router(vault)
    health = _data(router.dispatch("sync.health", {}))
    assert health["namespace"] == "sync"
    assert health["records"] >= 2
    assert "formats" in health
    snapshot = _data(router.dispatch("sync.snapshot", {}))
    assert snapshot["manifest"]["record_count"] >= 2
    assert len(snapshot["records"]) >= 2
    profiles = _data(router.dispatch("sync.portability.profiles", {}))
    assert profiles["profiles"]
    profile = _data(router.dispatch("sync.portability.profile", {"name": "quick-json"}))
    assert profile["name"] == "quick-json"
    matrix = _data(router.dispatch("sync.portability.matrix", {}))
    assert "export" in matrix
    source = tmp_path / "bundle.json"
    source.write_text(json.dumps({"records": snapshot["records"]}), encoding="utf-8")
    detected = _data(router.dispatch("sync.portability.detect", {"path": str(source)}))
    assert detected["format"] == "json"
    records = _data(router.dispatch("sync.portability.records", {"path": str(source)}))
    assert records["summary"]["total"] >= 2


def test_backup_restore_export_import_and_dry_run_routes(vault: Vault, tmp_path: Path) -> None:
    router = _router(vault)
    backup_path = tmp_path / "backup.db"
    plan = _data(
        router.dispatch(
            "sync.backup.plan",
            {"destination": str(backup_path), "format": "sqlite", "include_settings": True},
        )
    )
    assert plan["plan"]["destination"].endswith("backup.db")
    created = _data(
        router.dispatch(
            "sync.backup.create",
            {"destination": str(backup_path), "format": "sqlite", "include_settings": True},
        )
    )
    assert Path(created["path"]).is_file()
    assert created["checksum"]
    inspected = _data(router.dispatch("sync.backup.inspect", {"path": created["path"]}))
    assert inspected["format"] in {"sqlite", "json"}

    export_target = tmp_path / "export.json"
    export_dry = _data(
        router.dispatch(
            "sync.export.plan",
            {"destination": str(export_target), "format": "json", "dry_run": True},
        )
    )
    assert export_dry["dry_run"]["operation"] == "export"
    exported = _data(
        router.dispatch(
            "sync.export.run",
            {"destination": str(export_target), "format": "json", "label": "test"},
        )
    )
    assert Path(exported["path"]).is_file()
    assert Path(exported["manifest_path"]).is_file()

    preview = _data(
        router.dispatch(
            "sync.import.plan",
            {"source": str(export_target), "format": "json", "strategy": "skip", "dry_run": True},
        )
    )
    assert preview["dry_run"] is True
    assert "merge" in preview
    dry_run = _data(
        router.dispatch(
            "sync.dry_run",
            {"operation": "import", "payload": {"source": str(export_target), "strategy": "merge"}},
        )
    )
    assert dry_run["operation"] == "import"

    restore_dry = _data(
        router.dispatch(
            "sync.restore.plan",
            {"source": str(backup_path), "dry_run": True, "mode": "inspect"},
        )
    )
    assert restore_dry["plan"]["source"].endswith("backup.db")
    # Import into a fresh vault to verify run path.
    other = Vault(tmp_path / "other.db")
    try:
        other_router = _router(other)
        imported = _data(
            other_router.dispatch(
                "sync.import.run",
                {
                    "source": str(export_target),
                    "format": "json",
                    "strategy": "merge",
                    "dry_run": False,
                },
            )
        )
        assert imported["dry_run"] is False
        assert imported["merge"]["counts"]["applied"] >= 0
        assert len(other.live_nodes()) >= 1
    finally:
        other.close()


def test_conflict_merge_journal_vector_and_migration_routes(vault: Vault, tmp_path: Path) -> None:
    router = _router(vault)
    snapshot = _data(router.dispatch("sync.snapshot", {}))
    remote = [dict(item) for item in snapshot["records"]]
    remote[0]["content"] = "changed remotely"
    remote[0]["updated_at"] = "2030-01-01T00:00:00Z"
    remote[0]["checksum"] = "different"

    detected = _data(
        router.dispatch("sync.conflicts.detect", {"remote": remote, "strategy": "merge"})
    )
    assert detected["summary"]["conflicts"] >= 1
    resolved = _data(
        router.dispatch(
            "sync.conflicts.resolve",
            {"remote": remote, "strategy": "prefer_remote"},
        )
    )
    assert "conflicts" in resolved
    session = _data(
        router.dispatch(
            "sync.conflicts.session.create",
            {"operation": "import", "remote": remote, "strategy": "merge"},
        )
    )
    session_id = session["session_id"]
    listed = _data(router.dispatch("sync.conflicts.session.list", {"limit": 10}))
    assert any(item["session_id"] == session_id for item in listed["sessions"])
    fetched = _data(router.dispatch("sync.conflicts.session.get", {"session_id": session_id}))
    assert fetched["session_id"] == session_id
    if fetched["conflicts"]:
        key = fetched["conflicts"][0]["key"]
        updated = _data(
            router.dispatch(
                "sync.conflicts.session.resolve",
                {"session_id": session_id, "resolutions": {key: "keep_remote"}},
            )
        )
        assert updated["session_id"] == session_id
    discarded = _data(router.dispatch("sync.conflicts.session.discard", {"session_id": session_id}))
    assert discarded["session_id"] == session_id

    merge = _data(router.dispatch("sync.merge.preview", {"remote": remote, "strategy": "merge"}))
    assert merge["dry_run"] is True
    journal = _data(router.dispatch("sync.journal.diff", {"remote": remote}))
    assert "entries" in journal
    report = _data(router.dispatch("sync.journal.report", {"remote": remote}))
    assert "summary" in report

    vectors = _data(
        router.dispatch(
            "sync.vectors.compare",
            {"local": {"device": 2, "server": 1}, "remote": {"device": 1, "server": 3}},
        )
    )
    assert vectors["relation"] == "concurrent"
    assert vectors["merged"]["server"] == 3

    migration = _data(
        router.dispatch(
            "sync.migration.check",
            {
                "manifest": {
                    "manifest_version": "1.0",
                    "schema_version": 4,
                    "app_version": "1.0.0",
                    "record_count": 1,
                }
            },
        )
    )
    assert migration["compatibility"]["compatible"] is True

    progress = _data(
        router.dispatch(
            "sync.progress.report",
            {"steps": [{"stage": "plan"}, {"stage": "run", "message": "done"}]},
        )
    )
    assert progress["summary"]["stages"] == 2
    stats = _data(router.dispatch("sync.state.stats", {}))
    assert "operations" in stats
    operations = _data(router.dispatch("sync.state.operations", {"limit": 10}))
    assert "operations" in operations


def test_checksum_route_accepts_expected_actual_and_path(vault: Vault, tmp_path: Path) -> None:
    router = _router(vault)
    payload = b"abc123"
    file_path = tmp_path / "data.txt"
    file_path.write_text("abc123", encoding="utf-8")
    digest = _data(router.dispatch("sync.checksums.verify", {"path": str(file_path)}))
    assert digest["checksum"]
    comparison = _data(
        router.dispatch(
            "sync.checksums.verify",
            {
                "expected": {"file.txt": digest["checksum"]},
                "actual": {"file.txt": digest["checksum"]},
            },
        )
    )
    assert comparison["ok"] is True
    encoded = base64.b64encode(payload).decode("ascii")
    assert encoded
