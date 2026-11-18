from __future__ import annotations

from redscribe.v2.sync.checksums import (
    ChecksumVerifier,
    canonical_json,
    checksum_bytes,
    checksum_json,
    checksum_text,
)
from redscribe.v2.sync.conflicts import ConflictDetector, ConflictResolver
from redscribe.v2.sync.manifest import SnapshotManifest
from redscribe.v2.sync.merge import MergeEngine, merge_records
from redscribe.v2.sync.migration import MigrationCompatibility
from redscribe.v2.sync.models import ConflictRecord, ProgressReport
from redscribe.v2.sync.portable import (
    compatibility_matrix,
    get_profile,
    list_profiles,
    portability_summary,
)
from redscribe.v2.sync.progress import ProgressTracker, progress_summary
from redscribe.v2.sync.reports import summarize_changes, summarize_conflicts
from redscribe.v2.sync.state import SyncStateStore
from redscribe.v2.sync.version_vectors import VersionVector, bump_vector, compare_vectors


def test_checksum_helpers_and_verifier_detect_mismatches() -> None:
    assert checksum_bytes(b"hello") == checksum_text("hello")
    assert checksum_json({"a": 1, "b": 2}) == checksum_json({"b": 2, "a": 1})
    assert canonical_json({"z": 1, "a": 2}) == '{"a":2,"z":1}'
    verifier = ChecksumVerifier()
    report = verifier.compare({"a.txt": "x"}, {"a.txt": "y", "b.txt": "z"}, allow_extra=False)
    assert report.ok is False
    assert report.mismatched["a.txt"]["expected"] == "x"
    assert report.extra == ["b.txt"]
    clean = verifier.compare({"a.txt": "x"}, {"a.txt": "x"}, allow_extra=True)
    assert clean.ok is True


def test_manifest_build_validate_and_digest() -> None:
    records = [
        {"id": 1, "title": "A", "path": "A", "checksum": "abc", "kind": "note"},
        {"id": 2, "title": "B", "path": "B", "checksum": "def", "kind": "note"},
    ]
    manifest = SnapshotManifest.build(source="vault.db", format="json", records=records)
    assert manifest.record_count == 2
    assert manifest.record_checksums == {"A": "abc", "B": "def"}
    assert manifest.digest == manifest.compute_digest()
    validated = SnapshotManifest.from_dict(manifest.as_dict()).validate()
    assert validated.digest == manifest.digest


def test_version_vectors_compare_and_merge() -> None:
    local = VersionVector.from_dict({"node-a": 2, "node-b": 1})
    remote = VersionVector.from_dict({"node-a": 1, "node-b": 2})
    assert compare_vectors(local, local.copy()) == "equal"
    assert compare_vectors(local, VersionVector.from_dict({"node-a": 1})) == "local"
    assert compare_vectors(VersionVector.from_dict({"node-a": 1}), local) == "remote"
    assert compare_vectors(local, remote) == "concurrent"
    merged = local.copy().merge(remote)
    assert merged.as_dict() == {"node-a": 2, "node-b": 2}
    bumped = bump_vector({"node-a": 1}, "node-a", 3)
    assert bumped.value("node-a") == 4


def test_progress_tracker_and_summary() -> None:
    tracker = ProgressTracker("sync")
    tracker.report("plan", 0, 2, "planning")
    tracker.report("plan", 1, 2, "halfway")
    tracker.report("plan", 2, 2, "done", done=True)
    assert tracker.latest() is not None
    summary = progress_summary(tracker.reports)
    assert summary["stages"] == 1
    assert summary["done"] is True
    assert isinstance(tracker.reports[0], ProgressReport)


def test_conflict_detection_and_resolution() -> None:
    local = [
        {
            "id": 1,
            "title": "Note",
            "path": "Note",
            "kind": "note",
            "content": "local",
            "checksum": "a",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    remote = [
        {
            "id": 1,
            "title": "Note",
            "path": "Note",
            "kind": "note",
            "content": "remote",
            "checksum": "b",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    ]
    detector = ConflictDetector()
    conflicts = detector.detect(local, remote)
    assert len(conflicts) == 1
    assert conflicts[0].kind == "content"
    resolver = ConflictResolver()
    resolved = resolver.resolve(conflicts, strategy="prefer_remote")
    assert resolved[0].resolution == "keep_remote"
    summary = resolver.summary(resolved)
    assert summary["total"] == 1
    assert summary["keep_remote"] == 1


def test_merge_engine_preview_and_record_merge() -> None:
    local = [
        {
            "id": 1,
            "title": "Alpha",
            "path": "Alpha",
            "kind": "note",
            "content": "left",
            "tags": "web",
            "checksum": "a",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    remote = [
        {
            "id": 1,
            "title": "Alpha",
            "path": "Alpha",
            "kind": "note",
            "content": "right",
            "tags": "api",
            "checksum": "b",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    ]
    merged = merge_records(local[0], remote[0])
    assert "sync:local" in merged["content"]
    assert merged["tags"] in {"api, web", "web, api"}
    engine = MergeEngine(strategy="merge")
    preview = engine.preview(local, remote)
    assert preview["dry_run"] is True
    assert preview["counts"]["conflicts"] >= 1


def test_migration_compatibility_and_profiles() -> None:
    migration = MigrationCompatibility(current_schema=4, supported_manifest_versions=("1.0",))
    report = migration.check_manifest(
        {
            "manifest_version": "1.0",
            "schema_version": 3,
            "app_version": "0.0.0",
            "record_count": 1,
        }
    )
    assert report.compatible is True
    assert report.requires_migration is True
    plan = migration.migration_plan(
        {
            "manifest_version": "1.0",
            "schema_version": 3,
            "app_version": "0.0.0",
            "record_count": 1,
        }
    )
    assert isinstance(plan["steps"], list)
    profiles = list_profiles()
    assert any(profile["name"] == "quick-json" for profile in profiles)
    assert get_profile("full-backup").format == "sqlite"
    matrix = compatibility_matrix()
    assert "json" in matrix["export"]
    summary = portability_summary(
        [
            {"kind": "note", "tags": "a,b", "target": "x", "flag": "f", "content": "c"},
            {"kind": "folder", "tags": "", "target": "", "flag": "", "content": ""},
        ]
    )
    assert summary["total"] == 2
    assert summary["tags"] == 2


def test_reports_and_state_store() -> None:
    change = type(
        "C",
        (),
        {
            "action": "update",
            "entity_type": "note",
            "path": "x",
            "key": "x",
            "title": "X",
            "checksum": "",
            "updated_at": "",
            "local": None,
            "remote": None,
            "as_dict": lambda self: {},
        },
    )()
    conflict = ConflictRecord(
        key="x",
        kind="content",
        path="x",
        title="X",
        resolution="unresolved",
    )
    changes = summarize_changes([change])
    conflicts = summarize_conflicts([conflict])
    assert changes["total"] == 1
    assert conflicts["unresolved"] == 1
    store = SyncStateStore(max_operations=10, max_sessions=10)
    op = store.create_operation("backup")
    store.update_operation(op.operation_id, status="completed")
    assert store.get_operation(op.operation_id)["status"] == "completed"
    session = store.create_conflict_session("import", [conflict])
    assert store.get_conflict_session(session.session_id).session_id == session.session_id
    resolved = store.resolve_conflict_session(session.session_id, {"x": "keep_local"})
    assert resolved.resolved is True
    stats = store.stats()
    assert stats["operations"] >= 1
