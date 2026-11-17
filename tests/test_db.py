from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from redscribe.domain.models import Node, VaultStats
from redscribe.storage import ISSUE_CODES, IntegrityReport
from redscribe.storage import db as storage_db
from redscribe.storage.db import SCHEMA_VERSION, Vault
from redscribe.storage.integrity import IndexDrift, IntegrityIssue
from redscribe.storage.retention import (
    AutoBackup,
    CheckpointResult,
    PruneResult,
    list_auto_backups,
    parse_auto_backup,
)


def test_new_vault_is_empty(vault: Vault) -> None:
    assert vault.stats() == VaultStats()
    assert vault.children(None) == []
    assert vault.live_nodes() == []
    assert vault.fts_enabled is True


def test_create_and_read_nodes(vault: Vault) -> None:
    folder = vault.create_node("Engagements", kind="folder")
    note = vault.create_node(
        "ACME",
        folder.id,
        content="# ACME\n\nScope",
        tags="web, report",
        target="app.acme.test",
        status="active",
        difficulty="medium",
        flag="flag{demo}",
        pinned=True,
    )
    assert folder.is_folder
    assert note.is_note
    assert note.parent_id == folder.id
    assert note.tag_list == ["web", "report"]
    assert note.status_label == "Active"
    assert note.difficulty_label == "Medium"
    assert vault.get_node(note.id) == note
    assert vault.path_of(note.id) == "Engagements / ACME"
    assert vault.path_of(note.id, include_self=False) == "Engagements"


def test_create_node_validates_inputs(vault: Vault) -> None:
    with pytest.raises(ValueError):
        vault.create_node("Bad", kind="workspace")
    with pytest.raises(ValueError):
        vault.create_node("Bad", status="later")
    with pytest.raises(ValueError):
        vault.create_node("Bad", difficulty="nightmare")
    with pytest.raises(ValueError):
        vault.create_node("Child", 999)

    note = vault.create_node("Note")
    with pytest.raises(ValueError):
        vault.create_node("Nested", note.id)


def test_create_node_normalizes_title_and_flag(vault: Vault) -> None:
    note = vault.create_node("  Title  ", flag="  flag{demo}  ")
    assert note.title == "Title"
    assert note.flag == "flag{demo}"
    assert vault.create_node("   ").title == "Untitled"


def test_update_node_fields_and_validation(vault: Vault) -> None:
    note = vault.create_node("Note", content="old", status="todo")
    updated = vault.update_node(
        note.id,
        title=" New title ",
        content="new",
        tags="a,b",
        target="10.10.10.10",
        status="done",
        difficulty="easy",
        flag=" flag{updated} ",
        pinned=True,
    )
    assert updated.title == "New title"
    assert updated.content == "new"
    assert updated.tags == "a, b"
    assert updated.target == "10.10.10.10"
    assert updated.status == "done"
    assert updated.difficulty == "easy"
    assert updated.flag == "flag{updated}"
    assert updated.pinned is True

    with pytest.raises(TypeError):
        vault.update_node(note.id, kind="folder")
    with pytest.raises(ValueError):
        vault.update_node(note.id, status="later")
    with pytest.raises(ValueError):
        vault.update_node(note.id, difficulty="nightmare")
    with pytest.raises(ValueError):
        vault.update_node(999, title="Missing")


def test_children_are_ordered_by_sort_order(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    first = vault.create_node("First", folder.id)
    second = vault.create_node("Second", folder.id)
    third = vault.create_node("Third", folder.id)
    assert [node.id for node in vault.children(folder.id)] == [first.id, second.id, third.id]

    vault.reorder_node(third.id, -2)
    assert [node.id for node in vault.children(folder.id)] == [third.id, first.id, second.id]
    assert vault.reorder_node(third.id, -10) is not None
    assert vault.reorder_node(third.id, 10) is not None
    assert vault.reorder_node(third.id, 0) is not None
    assert vault.reorder_node(999, 1) is None


def test_move_node_between_folders(vault: Vault) -> None:
    source = vault.create_node("Source", kind="folder")
    destination = vault.create_node("Destination", kind="folder")
    first = vault.create_node("First", source.id)
    second = vault.create_node("Second", source.id)

    moved = vault.move_node(second.id, destination.id)
    assert moved.parent_id == destination.id
    assert [node.id for node in vault.children(source.id)] == [first.id]
    assert [node.id for node in vault.children(destination.id)] == [second.id]

    vault.move_node(second.id, destination.id, before_id=None)
    assert [node.id for node in vault.children(destination.id)] == [second.id]

    with pytest.raises(ValueError):
        vault.move_node(second.id, 999)
    with pytest.raises(ValueError):
        vault.move_node(second.id, first.id)
    with pytest.raises(ValueError):
        vault.move_node(source.id, source.id)


def test_move_node_cannot_create_cycle(vault: Vault) -> None:
    parent = vault.create_node("Parent", kind="folder")
    child = vault.create_node("Child", parent.id, kind="folder")
    grandchild = vault.create_node("Grandchild", child.id, kind="folder")
    with pytest.raises(ValueError):
        vault.move_node(parent.id, grandchild.id)
    with pytest.raises(ValueError):
        vault.move_node(parent.id, parent.id)


def test_duplicate_node_copies_subtree(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    child = vault.create_node("Child", folder.id, kind="folder")
    note = vault.create_node("Note", child.id, content="body", tags="tag")

    copy = vault.duplicate_node(folder.id)
    assert copy.id != folder.id
    assert copy.title == "Folder (copy)"
    assert copy.parent_id == folder.parent_id
    copied_children = vault.children(copy.id)
    assert len(copied_children) == 1
    assert copied_children[0].id != child.id
    copied_notes = vault.children(copied_children[0].id)
    assert len(copied_notes) == 1
    assert copied_notes[0].id != note.id
    assert copied_notes[0].content == "body"


def test_soft_delete_restore_and_empty_trash(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    child = vault.create_node("Child", folder.id, kind="folder")
    note = vault.create_node("Note", child.id, content="secret")

    assert vault.delete_node(folder.id) == 3
    assert vault.get_node(folder.id) is None
    assert vault.get_node(note.id) is None
    assert vault.children(None) == []
    assert [node.id for node in vault.trashed_roots()] == [folder.id]
    assert vault.stats().trashed == 3

    restored = vault.restore_node(folder.id)
    assert restored.id == folder.id
    assert vault.get_node(note.id) is not None
    assert vault.get_node(child.id) is not None
    assert vault.restore_node(folder.id).id == restored.id

    vault.delete_node(note.id)
    assert vault.get_node(note.id) is None
    assert vault.get_node(child.id) is not None
    assert vault.empty_trash() == 1
    assert vault.trashed_roots() == []


def test_permanent_delete_removes_subtree(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    note = vault.create_node("Note", folder.id)
    assert vault.delete_node(folder.id, permanent=True) == 2
    assert vault.get_node(folder.id, include_deleted=True) is None
    assert vault.get_node(note.id, include_deleted=True) is None
    with pytest.raises(ValueError):
        vault.delete_node(folder.id)
    with pytest.raises(ValueError):
        vault.restore_node(999)


def test_restore_with_deleted_parent_moves_note_to_root(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    note = vault.create_node("Note", folder.id)
    vault.delete_node(folder.id)

    restored = vault.restore_node(note.id)
    assert restored.parent_id is None
    assert vault.children(None)[0].id == note.id


def test_search_uses_fts_and_excludes_folders_and_trash(vault: Vault) -> None:
    folder = vault.create_node("HTB folder", kind="folder")
    note = vault.create_node(
        "HTB Corporate",
        folder.id,
        content="A Windows box with SMB.",
        tags="htb,windows",
    )
    vault.create_node("Other", content="Nothing relevant")

    hits = vault.search("corporate")
    assert [hit.node_id for hit in hits] == [note.id]
    assert hits[0].path == "HTB folder"
    assert "Corporate" in hits[0].title

    assert vault.search("HTB") != []
    assert all(hit.node_id != folder.id for hit in vault.search("HTB"))

    vault.delete_node(note.id)
    assert vault.search("corporate") == []


def test_search_updates_fts_when_node_changes(vault: Vault) -> None:
    note = vault.create_node("Original", content="alpha bravo")
    assert [hit.node_id for hit in vault.search("alpha")] == [note.id]
    vault.update_node(note.id, title="Renamed", content="charlie delta")
    assert vault.search("alpha") == []
    assert [hit.node_id for hit in vault.search("charlie")] == [note.id]


def test_search_like_fallback(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    note = vault.create_node("Target", folder.id, content="A very secret value", tags="red")
    vault.delete_node(vault.create_node("Trash", content="secret").id)

    vault.fts_enabled = False
    hits = vault.search("secret")
    assert [hit.node_id for hit in hits] == [note.id]
    assert hits[0].path == "Folder"
    assert "tags: red" not in hits[0].snippet
    assert vault.search("   ") == []


def test_symbol_only_query_uses_like_search(vault: Vault) -> None:
    note = vault.create_node("Pipe", content="admin | flag{test}")
    assert [hit.node_id for hit in vault.search("|")] == [note.id]
    assert [hit.node_id for hit in vault.search("flag{test}")] == [note.id]


def test_failed_fts_setup_removes_partial_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        storage_db,
        "_FTS_SCHEMA",
        storage_db._FTS_SCHEMA + "\nCREATE TABLE deliberately_broken (",
    )
    with Vault(":memory:") as vault:
        assert vault.fts_enabled is False
        names = {
            str(row["name"])
            for row in vault.connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'nodes_fts%'"
            )
        }
        assert names == set()
        note = vault.create_node("Fallback", content="searchable")
        assert [hit.node_id for hit in vault.search("searchable")] == [note.id]


def test_search_invalid_fts_query_falls_back(monkeypatch: pytest.MonkeyPatch, vault: Vault) -> None:
    note = vault.create_node("Note", content="alpha")
    calls = {"count": 0}

    def broken(query: str, limit: int) -> list[object]:
        calls["count"] += 1
        raise sqlite3.OperationalError("boom")

    monkeypatch.setattr(vault, "_search_fts", broken)
    hits = vault.search("alpha")
    assert calls["count"] == 1
    assert vault.fts_enabled is False
    assert [hit.node_id for hit in hits] == [note.id]


def test_recent_pinned_and_iter_notes(vault: Vault) -> None:
    first = vault.create_node("First", content="a")
    second = vault.create_node("Second", content="b", pinned=True)
    folder = vault.create_node("Folder", kind="folder")
    vault.connection.execute(
        "UPDATE nodes SET updated_at = ? WHERE id = ?", ("2026-10-21T10:00:00+00:00", first.id)
    )
    vault.connection.execute(
        "UPDATE nodes SET updated_at = ? WHERE id = ?", ("2026-10-21T11:00:00+00:00", second.id)
    )
    vault.connection.commit()
    assert [node.id for node in vault.recent_notes()] == [second.id, first.id]
    assert [node.id for node in vault.pinned_notes()] == [second.id]
    assert folder.id not in {node.id for node in vault.iter_notes()}
    vault.delete_node(first.id)
    assert [node.id for node in vault.recent_notes()] == [second.id]


def test_tags_flags_and_stats(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    first = vault.create_node(
        "First",
        folder.id,
        content="flag{alpha} and ctf{beta}",
        tags="Web,HTB,web",
        target="app.test",
        flag="flag{manual}",
        pinned=True,
    )
    second = vault.create_node(
        "Second",
        folder.id,
        content="ctf{beta} again",
        tags="web",
        target="app.test",
    )
    vault.create_node("Third", content="nothing", tags="linux")

    counts = {entry.tag: entry.count for entry in vault.tag_counts()}
    assert counts == {"Web": 2, "HTB": 1, "linux": 1}
    assert {node.id for node in vault.tag_nodes("WEB")} == {first.id, second.id}
    assert {node.id for node in vault.tag_nodes("HTB")} == {first.id}
    assert vault.tag_nodes("missing") == []

    flags = vault.collected_flags()
    assert [hit.flag for hit in flags] == ["flag{manual}", "flag{alpha}", "ctf{beta}"]
    assert flags[0].manual is True
    assert flags[0].node_id == first.id

    stats = vault.stats()
    assert stats.notes == 3
    assert stats.folders == 1
    assert stats.flags == 3
    assert stats.targets == 1
    assert stats.tags == 3
    assert stats.pinned == 1


def test_stats_only_count_pinned_notes(vault: Vault) -> None:
    vault.create_node("Pinned folder", kind="folder", pinned=True)
    vault.create_node("Pinned note", pinned=True)
    vault.create_node("Plain note")
    stats = vault.stats()
    assert stats.notes == 2
    assert stats.folders == 1
    assert stats.pinned == 1


def test_stats_caches_invalidate_after_changes(vault: Vault) -> None:
    first = vault.create_node(
        "First",
        content="flag{alpha}",
        tags="Web",
        target="app.test",
    )
    initial = vault.stats()
    assert initial.notes == 1
    assert initial.flags == 1
    assert initial.tags == 1
    assert [hit.flag for hit in vault.collected_flags()] == ["flag{alpha}"]

    vault.create_node(
        "Second",
        content="ctf{beta}",
        tags="Linux",
        target="app.test",
    )
    updated = vault.stats()
    assert updated.notes == 2
    assert updated.flags == 2
    assert updated.tags == 2
    assert {hit.flag for hit in vault.collected_flags()} == {"flag{alpha}", "ctf{beta}"}
    assert {entry.tag for entry in vault.tag_counts()} == {"Web", "Linux"}

    vault.update_node(first.id, content="clean", tags="")
    assert vault.stats().flags == 1
    assert [hit.flag for hit in vault.collected_flags()] == ["ctf{beta}"]


def test_content_revision_ignores_setting_writes(vault: Vault) -> None:
    revision = vault.content_revision
    vault.set_setting("ui.last_note", "1")
    assert vault.content_revision == revision
    vault.create_node("Note")
    assert vault.content_revision > revision


def test_basic_stats_skips_content_scans(vault: Vault) -> None:
    vault.create_node("Note", content="flag{alpha}", tags="Web", target="app.test")
    stats = vault.basic_stats()
    assert stats.notes == 1
    assert stats.targets == 1
    assert stats.flags == 0
    assert stats.tags == 0


def test_settings_round_trip(vault: Vault) -> None:
    assert vault.get_setting("missing") is None
    assert vault.get_setting("missing", "fallback") == "fallback"
    vault.set_setting("theme", "light")
    assert vault.get_setting("theme") == "light"
    vault.set_setting("theme", "dark")
    assert vault.get_setting("theme") == "dark"

    assert vault.get_json_setting("layout", {"width": 0}) == {"width": 0}
    vault.set_json_setting("layout", {"width": 240, "expanded": [1, 2]})
    assert vault.get_json_setting("layout", {}) == {"width": 240, "expanded": [1, 2]}
    vault.set_setting("broken", "{not json")
    assert vault.get_json_setting("broken", ["safe"]) == ["safe"]


def test_custom_snippets_crud(vault: Vault) -> None:
    snippet = vault.create_snippet(
        " Listener ", " nc -lvnp 4444 ", " Catch shells ", " shell,listen "
    )
    assert snippet.id is not None
    assert snippet.title == "Listener"
    assert snippet.command == "nc -lvnp 4444"
    assert snippet.description == "Catch shells"
    assert snippet.tags == "shell,listen"
    assert snippet.tag_list == ["shell", "listen"]
    assert snippet.category == "shell"
    assert vault.list_custom_snippets() == [snippet]

    updated = vault.update_snippet(
        snippet.id, title="Better listener", command="nc -lvnp 9001", tags="shell"
    )
    assert updated.command == "nc -lvnp 9001"
    assert vault.list_custom_snippets()[0].title == "Better listener"
    assert vault.delete_snippet(snippet.id) is True
    assert vault.delete_snippet(snippet.id) is False
    assert vault.list_custom_snippets() == []

    with pytest.raises(ValueError):
        vault.create_snippet("Empty", "   ")
    with pytest.raises(ValueError):
        vault.update_snippet(999, title="Missing", command="echo hi")


def test_backup_creates_usable_copy(tmp_path: Path, vault: Vault) -> None:
    note = vault.create_node("Backed up", content="flag{copy}", tags="backup")
    destination = tmp_path / "backups" / "vault-copy.db"
    assert vault.backup_to(destination) == destination
    with Vault(destination) as copy:
        copied = copy.get_node(note.id)
        assert copied is not None
        assert copied.content == "flag{copy}"
        assert copy.get_node(note.id).tags == "backup"  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        vault.backup_to(vault.path)  # type: ignore[arg-type]


def test_backup_to_auto_does_not_overwrite(tmp_path: Path) -> None:
    with Vault(tmp_path / "vault.db") as vault:
        first = vault.backup_to_auto()
        second = vault.backup_to_auto()
    assert first != second
    assert first.exists()
    assert second.exists()
    assert re.fullmatch(r"vault-\d{8}T\d{6}Z(?:-\d+)?\.db", first.name)


def test_metadata_changes_get_a_version_immediately(vault: Vault) -> None:
    note = vault.create_node("Original", content="body")
    vault.update_node(note.id, status="done")
    vault.update_node(note.id, flag="flag{new}")
    versions = vault.list_versions(note.id)
    assert len(versions) >= 2
    snapshot = vault.get_version(versions[0]["id"])
    assert snapshot is not None
    assert snapshot["status"] == "done"
    assert snapshot["flag"] == ""


def test_node_filename(vault: Vault) -> None:
    note = vault.create_node("HTB — Corporate!")
    assert vault.node_filename(note.id) == "htb-corporate.md"
    assert vault.node_filename(999) == "note-999.md"


def test_schema_version_and_display_path(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "vault.db"
    with Vault(path) as vault:
        assert vault.display_path == str(path)
        assert vault.schema_version == SCHEMA_VERSION
        assert vault.get_setting("missing") is None
    assert path.exists()

    memory = Vault(":memory:")
    try:
        assert memory.display_path == ":memory:"
        assert memory.path is None
        assert memory.get_node(1) is None
    finally:
        memory.close()


def test_file_vault_uses_wal(tmp_path: Path) -> None:
    with Vault(tmp_path / "vault.db") as vault:
        row = vault.connection.execute("PRAGMA journal_mode").fetchone()
        assert row is not None
        assert str(row[0]).lower() == "wal"


def test_legacy_schema_is_migrated_in_place(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with Vault(path) as vault:
        vault.connection.execute("DROP INDEX idx_nodes_kind")
        vault.connection.execute("PRAGMA user_version = 1")
        vault.connection.commit()

    with Vault(path) as upgraded:
        assert upgraded.schema_version == SCHEMA_VERSION
        indexes = {
            str(row["name"])
            for row in upgraded.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {"idx_nodes_kind", "idx_nodes_target", "idx_nodes_pinned"} <= indexes
        assert any(
            str(row["name"]) == "nodes_history"
            for row in upgraded.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        )
        assert upgraded.create_node("Migrated").title == "Migrated"


def test_newer_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    with Vault(path) as vault:
        vault.connection.execute("PRAGMA user_version = 999")
        vault.connection.commit()

    with pytest.raises(RuntimeError, match="newer than this RedScribe build"):
        Vault(path)


def test_closed_vault_is_idempotent() -> None:
    vault = Vault(":memory:")
    vault.close()
    vault.close()
    assert vault._closed is True


def test_json_setting_encoding(vault: Vault) -> None:
    vault.set_json_setting("unicode", {"title": "Café"})
    raw = vault.get_setting("unicode")
    assert raw is not None
    assert json.loads(raw)["title"] == "Café"


def test_live_nodes_round_trip(vault: Vault) -> None:
    folder = vault.create_node("F", kind="folder")
    note = vault.create_node("N", folder.id)
    trash = vault.create_node("Trash", content="x")
    vault.delete_node(trash.id)
    live = vault.live_nodes()
    assert {node.id for node in live} == {folder.id, note.id}
    assert all(isinstance(node, Node) for node in live)


@contextmanager
def _without_foreign_keys(vault: Vault) -> Iterator[sqlite3.Connection]:
    connection = vault.connection
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        yield connection
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _raw_node(
    connection: sqlite3.Connection,
    *,
    parent_id: int | None = None,
    title: str = "Raw",
    kind: str = "note",
    tags: str = "",
    deleted_at: str | None = None,
) -> int:
    stamp = "2026-01-01T00:00:00Z"
    cursor = connection.execute(
        "INSERT INTO nodes (parent_id, title, kind, content, tags, target, status, "
        "difficulty, flag, pinned, sort_order, created_at, updated_at, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            parent_id,
            title,
            kind,
            "",
            tags,
            "",
            "todo",
            "",
            "",
            0,
            0,
            stamp,
            stamp,
            deleted_at,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def test_integrity_report_clean_vault(vault: Vault) -> None:
    report = vault.integrity_report()
    assert isinstance(report, IntegrityReport)
    assert report.ok is True
    assert report.issues == ()
    assert report.nodes_checked == 0
    assert report.settings_checked == 0
    assert report.schema_version == SCHEMA_VERSION
    assert report.fts_enabled is True
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.codes() == frozenset()
    assert report.counts() == {}
    payload = report.as_dict()
    assert payload["ok"] is True
    assert payload["issues"] == []
    assert payload["nodes_checked"] == 0


def test_integrity_report_counts_nodes_and_settings(vault: Vault) -> None:
    vault.create_node("One")
    vault.create_node("Two")
    vault.set_setting("theme", "dark")
    report = vault.integrity_report()
    assert report.nodes_checked == 2
    assert report.settings_checked == 1
    assert report.ok is True


def test_integrity_report_detects_missing_parent(vault: Vault) -> None:
    note = vault.create_node("Lost")
    with _without_foreign_keys(vault) as connection:
        connection.execute("UPDATE nodes SET parent_id = 9999 WHERE id = ?", (note.id,))
        connection.commit()
    report = vault.integrity_report()
    issues = [issue for issue in report.issues if issue.code == "missing_parent"]
    assert len(issues) == 1
    assert isinstance(issues[0], IntegrityIssue)
    assert issues[0].node_id == note.id
    assert issues[0].severity == "error"
    assert issues[0].related_ids == (9999,)
    assert report.ok is False
    assert report.error_count == 1
    assert report.codes() == frozenset({"missing_parent"})


def test_integrity_report_detects_orphan_with_note_parent(vault: Vault) -> None:
    parent = vault.create_node("Container", content="x")
    with _without_foreign_keys(vault) as connection:
        child_id = _raw_node(connection, parent_id=parent.id, title="Child")
    issues = [issue for issue in vault.integrity_report().issues if issue.code == "orphan_node"]
    assert [issue.node_id for issue in issues] == [child_id]
    assert issues[0].severity == "warning"
    assert issues[0].related_ids == (parent.id,)


def test_integrity_report_detects_live_node_with_deleted_parent(vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    child = vault.create_node("Child", folder.id)
    with _without_foreign_keys(vault) as connection:
        connection.execute(
            "UPDATE nodes SET deleted_at = ? WHERE id = ?",
            ("2026-01-01T00:00:00Z", folder.id),
        )
        connection.commit()
    issues = [issue for issue in vault.integrity_report().issues if issue.code == "orphan_node"]
    assert [issue.node_id for issue in issues] == [child.id]
    assert "deleted parent" in issues[0].message


def test_integrity_report_detects_two_node_cycle(vault: Vault) -> None:
    first = vault.create_node("First", kind="folder")
    second = vault.create_node("Second", first.id, kind="folder")
    with _without_foreign_keys(vault) as connection:
        connection.execute("UPDATE nodes SET parent_id = ? WHERE id = ?", (second.id, first.id))
        connection.commit()
    issues = [issue for issue in vault.integrity_report().issues if issue.code == "cycle"]
    assert len(issues) == 1
    assert issues[0].node_id == first.id
    assert issues[0].related_ids == tuple(sorted((first.id, second.id)))
    assert "cycle" in issues[0].message.lower()
    assert vault.integrity_report().ok is False


def test_integrity_report_detects_self_cycle(vault: Vault) -> None:
    note = vault.create_node("Self", kind="folder")
    with _without_foreign_keys(vault) as connection:
        connection.execute("UPDATE nodes SET parent_id = ? WHERE id = ?", (note.id, note.id))
        connection.commit()
    issues = [issue for issue in vault.integrity_report().issues if issue.code == "cycle"]
    assert len(issues) == 1
    assert issues[0].related_ids == (note.id,)


def test_integrity_report_detects_invalid_tags(vault: Vault) -> None:
    bad = vault.create_node("Bad tags")
    other = vault.create_node("Control tags")
    good = vault.create_node("Good tags", tags="web, ctf")
    connection = vault.connection
    connection.execute("UPDATE nodes SET tags = ? WHERE id = ?", (" a , a , b", bad.id))
    connection.execute("UPDATE nodes SET tags = ? WHERE id = ?", ("tag\nline", other.id))
    connection.commit()
    issues = [issue for issue in vault.integrity_report().issues if issue.code == "invalid_tag"]
    assert [issue.node_id for issue in issues] == sorted((bad.id, other.id))
    assert good.id not in {issue.node_id for issue in issues}


def test_integrity_report_detects_duplicate_slugs(vault: Vault) -> None:
    first = vault.create_node("Same Title")
    second = vault.create_node("same title")
    vault.create_node("Other")
    trashed = vault.create_node("Same Title")
    vault.delete_node(trashed.id)
    issues = [issue for issue in vault.integrity_report().issues if issue.code == "duplicate_slug"]
    assert len(issues) == 1
    assert issues[0].key == "same-title"
    assert issues[0].related_ids == (first.id, second.id)
    assert issues[0].severity == "warning"


def test_integrity_report_detects_bad_json_settings(vault: Vault) -> None:
    vault.set_setting("broken", "{not json")
    vault.set_setting("broken_list", "[1, 2")
    vault.set_setting("plain", "hello")
    vault.set_json_setting("layout", {"width": 240})
    issues = [
        issue for issue in vault.integrity_report().issues if issue.code == "invalid_json_setting"
    ]
    assert [issue.key for issue in issues] == ["broken", "broken_list"]
    assert len({issue.key for issue in issues}) == 2


def test_integrity_report_accepts_extra_json_keys(vault: Vault) -> None:
    vault.set_setting("custom", "nope")
    assert vault.integrity_report().codes() == frozenset()
    report = vault.integrity_report(json_keys=["custom"])
    assert report.codes() == frozenset({"invalid_json_setting"})
    assert report.counts() == {"invalid_json_setting": 1}


def test_integrity_report_detects_fts_drift_and_repair_fixes_it(vault: Vault) -> None:
    note = vault.create_node("Needle", content="needle alpha")
    extra = vault.create_node("Extra", content="beta")
    connection = vault.connection
    for trigger in ("nodes_fts_ai", "nodes_fts_ad", "nodes_fts_au"):
        connection.execute(f"DROP TRIGGER {trigger}")
    connection.commit()
    connection.execute("UPDATE nodes SET content = ? WHERE id = ?", ("needle omega", note.id))
    connection.commit()
    with _without_foreign_keys(vault) as raw:
        raw.execute("DELETE FROM nodes WHERE id = ?", (extra.id,))
        raw.commit()
    report = vault.integrity_report()
    assert {"fts_drift", "fts_missing_trigger"} <= report.codes()
    drift = vault.index_drift()
    assert isinstance(drift, IndexDrift)
    assert note.id in drift.changed_ids
    assert extra.id in drift.stale_ids
    assert len(drift.missing_triggers) == 3
    result = vault.repair_index()
    assert result.rebuilt is True
    assert result.rows_fixed >= 2
    assert result.triggers_restored == 3
    assert result.remaining_drift == 0
    assert vault.index_drift().clean is True
    assert [hit.node_id for hit in vault.search("omega")] == [note.id]
    assert vault.integrity_report().ok is True


def test_repair_index_is_noop_when_clean(vault: Vault) -> None:
    vault.create_node("Note", content="alpha")
    assert vault.index_drift().clean is True
    result = vault.repair_index()
    assert result.rebuilt is False
    assert result.rows_fixed == 0
    assert result.triggers_restored == 0
    assert result.remaining_drift == 0
    assert result.as_dict()["rebuilt"] is False
    assert vault.index_drift().clean is True


def test_repair_index_when_fts_disabled(vault: Vault) -> None:
    vault.fts_enabled = False
    result = vault.repair_index()
    assert result.rebuilt is False
    assert vault.index_drift().clean is True
    report = vault.integrity_report()
    assert report.fts_enabled is False
    assert report.codes() == frozenset()


def test_integrity_report_detects_missing_fts_index_and_repairs(
    vault_factory: Callable[..., Vault],
) -> None:
    vault = vault_factory("broken-index.db")
    vault.create_node("Note", content="alpha")
    connection = vault.connection
    for trigger in ("nodes_fts_ai", "nodes_fts_ad", "nodes_fts_au"):
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    connection.execute("DROP TABLE nodes_fts")
    connection.commit()
    report = vault.integrity_report()
    assert "fts_missing_index" in report.codes()
    assert report.error_count == 1
    result = vault.repair_index()
    assert result.rebuilt is True
    assert result.triggers_restored == 3
    assert vault.index_drift().clean is True
    assert [hit.node_id for hit in vault.search("alpha")] != []


def test_integrity_report_issues_are_sorted(vault: Vault) -> None:
    vault.create_node("Duplicate")
    vault.create_node("Duplicate")
    vault.set_setting("bad", "{oops")
    connection = vault.connection
    connection.execute(
        "UPDATE nodes SET tags = ? WHERE id = (SELECT MIN(id) FROM nodes)",
        (" a , a ",),
    )
    connection.commit()
    report = vault.integrity_report()
    codes = [issue.code for issue in report.issues]
    assert codes == sorted(codes, key=ISSUE_CODES.index)
    assert report.counts() == {
        "invalid_tag": 1,
        "duplicate_slug": 1,
        "invalid_json_setting": 1,
    }
    payload = report.as_dict()
    assert all(isinstance(entry["related_ids"], list) for entry in payload["issues"])


def test_issue_codes_are_unique() -> None:
    assert len(ISSUE_CODES) == len(set(ISSUE_CODES))


def test_prune_versions_keeps_newest_per_node(vault: Vault) -> None:
    first = vault.create_node("First", content="v0")
    second = vault.create_node("Second", content="v0")
    for status in ("active", "done", "blocked", "todo"):
        vault.update_node(first.id, status=status)
    for tag in ("a", "b"):
        vault.update_node(second.id, tags=tag)
    first_ids = [entry["id"] for entry in vault.list_versions(first.id)]
    second_ids = [entry["id"] for entry in vault.list_versions(second.id)]
    assert len(first_ids) >= 3
    assert len(second_ids) >= 2
    result = vault.prune_versions(1)
    assert isinstance(result, PruneResult)
    assert result.versions_removed == len(first_ids) + len(second_ids) - 2
    assert result.nodes_affected == 2
    assert result.orphan_versions_removed == 0
    assert [entry["id"] for entry in vault.list_versions(first.id)] == first_ids[:1]
    assert [entry["id"] for entry in vault.list_versions(second.id)] == second_ids[:1]
    assert result.as_dict()["nodes_affected"] == 2


def test_prune_versions_zero_clears_history(vault: Vault) -> None:
    note = vault.create_node("Note")
    vault.update_node(note.id, status="done")
    assert vault.list_versions(note.id) != []
    result = vault.prune_versions(0)
    assert result.versions_removed >= 1
    assert vault.list_versions(note.id) == []
    with pytest.raises(ValueError, match="non-negative"):
        vault.prune_versions(-1)


def test_prune_versions_removes_orphan_history(vault: Vault) -> None:
    note = vault.create_node("Note")
    vault.update_node(note.id, status="done")
    with _without_foreign_keys(vault) as connection:
        connection.execute(
            "INSERT INTO nodes_history (node_id, title, content, tags, target, status, "
            "difficulty, flag, created_at) VALUES (?, 'Ghost', '', '', '', '', '', '', ?)",
            (99999, "2026-01-01T00:00:00Z"),
        )
        connection.commit()
    result = vault.prune_versions(5)
    assert result.orphan_versions_removed == 1


def test_backup_to_auto_rotation_keeps_newest_and_user_backups(tmp_path: Path) -> None:
    with Vault(tmp_path / "vault.db") as vault:
        created = [vault.backup_to_auto() for _ in range(4)]
        user_backup = tmp_path / "backups" / "my-manual-backup.db"
        user_backup.write_bytes(b"user data")
        newest = vault.backup_to_auto(max_backups=2)
    remaining = {path.name for path in (tmp_path / "backups").iterdir()}
    assert newest.name in remaining
    assert created[-1].name in remaining
    assert created[0].name not in remaining
    assert created[1].name not in remaining
    assert created[2].name not in remaining
    assert user_backup.read_bytes() == b"user data"
    automatic = [name for name in remaining if name.startswith("vault-")]
    assert len(automatic) == 2


def test_backup_to_auto_rotation_orders_by_timestamp(tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        (directory / f"vault-{stamp}.db").write_bytes(b"old")
    user_backup = directory / "notes-export.db"
    user_backup.write_bytes(b"user")
    with Vault(tmp_path / "vault.db") as vault:
        newest = vault.backup_to_auto(max_backups=2)
    remaining = {path.name for path in directory.iterdir()}
    assert newest.name in remaining
    assert "vault-20260103T000000Z.db" in remaining
    assert "vault-20260102T000000Z.db" not in remaining
    assert "vault-20250101T000000Z.db" not in remaining
    assert user_backup.read_bytes() == b"user"


def test_backup_to_auto_without_max_keeps_all(vault: Vault) -> None:
    created = [vault.backup_to_auto() for _ in range(4)]
    assert all(path.exists() for path in created)
    assert len(created) == len(set(created))


def test_backup_to_auto_rejects_non_positive_rotation(vault: Vault) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        vault.backup_to_auto(max_backups=0)
    with pytest.raises(ValueError, match="at least 1"):
        vault.backup_to_auto(max_backups=-2)
    directory = vault.path.parent / "backups"
    assert not directory.exists()


def test_backup_to_auto_rotation_for_memory_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(storage_db.tempfile, "gettempdir", lambda: str(tmp_path))
    with Vault(":memory:") as vault:
        first = vault.backup_to_auto()
        second = vault.backup_to_auto(max_backups=1)
    directory = tmp_path / "redscribe-backups"
    assert [entry.path.name for entry in list_auto_backups(directory)] == [second.name]
    assert first.exists() is False


def test_parse_auto_backup_and_list(tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    directory.mkdir()
    names = (
        "vault-20260101T000000Z.db",
        "vault-20260101T000000Z-2.db",
        "vault-20260101T000000Z-10.db",
        "manual.db",
    )
    for name in names:
        (directory / name).write_bytes(b"x")
    entries = list_auto_backups(directory)
    assert [entry.sequence for entry in entries] == [0, 2, 10]
    assert [entry.sort_key for entry in entries] == sorted(entry.sort_key for entry in entries)
    assert parse_auto_backup(Path("manual.db")) is None
    entry = parse_auto_backup(Path("vault-20260101T000000Z-10.db"))
    assert isinstance(entry, AutoBackup)
    assert entry.stamp == "20260101T000000Z"
    assert entry.sequence == 10
    assert list_auto_backups(tmp_path / "missing") == []


def test_checkpoint_and_optimize(vault: Vault) -> None:
    vault.create_node("Note")
    result = vault.checkpoint()
    assert isinstance(result, CheckpointResult)
    assert result.mode == "TRUNCATE"
    assert result.busy == 0
    assert result.log >= 0
    assert result.checkpointed >= 0
    assert result.as_dict()["mode"] == "TRUNCATE"
    passive = vault.checkpoint(mode="passive")
    assert passive.mode == "PASSIVE"
    with pytest.raises(ValueError, match="Unsupported checkpoint mode"):
        vault.checkpoint(mode="NOPE")
    vault.optimize()


def test_checkpoint_memory_vault() -> None:
    with Vault(":memory:") as vault:
        result = vault.checkpoint()
        assert result.busy == 0
        assert result.log == -1
        assert result.checkpointed == -1
        vault.optimize()
