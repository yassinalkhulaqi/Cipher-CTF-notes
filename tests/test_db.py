from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from redscribe.domain.models import Node, VaultStats
from redscribe.storage import db as storage_db
from redscribe.storage.db import SCHEMA_VERSION, Vault


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
    assert updated.tags == "a,b"
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
        assert upgraded.schema_version == 2
        indexes = {
            str(row["name"])
            for row in upgraded.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {"idx_nodes_kind", "idx_nodes_target", "idx_nodes_pinned"} <= indexes
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
