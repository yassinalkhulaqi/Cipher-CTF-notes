from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.db import Vault
from redscribe.exporter import (
    export_note_html,
    export_note_markdown,
    export_vault_html,
    export_vault_markdown,
    note_front_matter,
    note_to_markdown,
    safe_filename,
)
from redscribe.importer import (
    import_directory,
    import_markdown_file,
    import_markdown_files,
    normalize_tags,
    parse_front_matter,
    read_text_file,
    title_from_body,
)


def test_parse_front_matter() -> None:
    metadata, body = parse_front_matter(
        """---
title: "ACME finding"
tags: [web, critical]
status: active
difficulty: hard
target: app.acme.test
flag: 'flag{demo}'
ignored line
---
# Heading

Body
"""
    )
    assert metadata == {
        "title": "ACME finding",
        "tags": "web,critical",
        "status": "active",
        "difficulty": "hard",
        "target": "app.acme.test",
        "flag": "flag{demo}",
    }
    assert body == "# Heading\n\nBody\n"


def test_parse_front_matter_without_block() -> None:
    assert parse_front_matter("# Title\n\nBody") == ({}, "# Title\n\nBody")
    assert parse_front_matter("---\ntitle: unterminated\n") == (
        {},
        "---\ntitle: unterminated\n",
    )


def test_normalize_tags_and_title_from_body() -> None:
    assert normalize_tags(" web, ctf , ") == "web,ctf"
    assert normalize_tags("[web, ctf]") == "web,ctf"
    assert normalize_tags("") == ""
    assert title_from_body("\n# Heading #\nBody", "fallback") == "Heading"
    assert title_from_body("Paragraph first\n# Later", "fallback") == "fallback"
    assert title_from_body("", "fallback") == "fallback"


def test_read_text_file_encodings(tmp_path: Path) -> None:
    utf8 = tmp_path / "utf8.md"
    utf8.write_text("Café", encoding="utf-8")
    assert read_text_file(utf8) == "Café"

    bom = tmp_path / "bom.md"
    bom.write_bytes(b"\xef\xbb\xbfHello")
    assert read_text_file(bom) == "Hello"

    cp1252 = tmp_path / "cp1252.md"
    cp1252.write_bytes(b"Caf\xe9")
    assert read_text_file(cp1252) == "Café"


def test_import_markdown_file(tmp_path: Path, vault: Vault) -> None:
    source = tmp_path / "finding.md"
    source.write_text(
        """---
title: Cross-tenant access
tags: web,high
status: done
difficulty: medium
target: app.acme.test
flag: flag{imported}
---
# Body title

Details.
""",
        encoding="utf-8",
    )
    note = import_markdown_file(vault, source)
    assert note.title == "Cross-tenant access"
    assert note.tags == "web,high"
    assert note.status == "done"
    assert note.difficulty == "medium"
    assert note.target == "app.acme.test"
    assert note.flag == "flag{imported}"
    assert note.content.startswith("# Body title")
    assert note.parent_id is None


def test_import_markdown_file_uses_heading_and_defaults(tmp_path: Path, vault: Vault) -> None:
    source = tmp_path / "fallback.md"
    source.write_text("# Heading title\n\nBody", encoding="utf-8")
    note = import_markdown_file(vault, source)
    assert note.title == "Heading title"
    assert note.status == "todo"
    assert note.difficulty == ""
    assert note.tags == ""

    invalid = tmp_path / "invalid.md"
    invalid.write_text("---\nstatus: later\ndifficulty: impossible\n---\nBody", encoding="utf-8")
    note = import_markdown_file(vault, invalid)
    assert note.title == "invalid"
    assert note.status == "todo"
    assert note.difficulty == ""


def test_import_markdown_files_sorts_and_skips(tmp_path: Path, vault: Vault) -> None:
    second = tmp_path / "b.md"
    first = tmp_path / "a.md"
    ignored = tmp_path / "c.pdf"
    second.write_text("# B", encoding="utf-8")
    first.write_text("# A", encoding="utf-8")
    ignored.write_text("nope", encoding="utf-8")
    notes = import_markdown_files(vault, [second, ignored, first])
    assert [note.title for note in notes] == ["A", "B"]


def test_import_directory_mirrors_tree(tmp_path: Path, vault: Vault) -> None:
    root = tmp_path / "notes"
    nested = root / "nested"
    empty = root / "empty"
    nested.mkdir(parents=True)
    empty.mkdir()
    (root / "root.md").write_text("# Root note", encoding="utf-8")
    (nested / "child.md").write_text("# Child note", encoding="utf-8")
    (root / ".hidden.md").write_text("# Hidden", encoding="utf-8")
    (root / "ignore.pdf").write_text("nope", encoding="utf-8")

    folder, count = import_directory(vault, root)
    assert folder is not None
    assert count == 2
    assert folder.title == "notes"
    titles = {node.title for node in vault.live_nodes()}
    assert titles == {"notes", "nested", "Root note", "Child note"}

    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    missing, missing_count = import_directory(vault, empty_root)
    assert missing is None
    assert missing_count == 0
    assert all(node.title != "empty-root" for node in vault.live_nodes())

    with pytest.raises(NotADirectoryError):
        import_directory(vault, tmp_path / "missing")


def test_note_markdown_export(tmp_path: Path, vault: Vault) -> None:
    note = vault.create_node(
        "HTB Box",
        content="# HTB Box\n\nBody\n",
        tags="htb",
        target="10.10.10.10",
        status="done",
        difficulty="easy",
        flag="flag{exported}",
    )
    assert note_front_matter(note).startswith('---\ntitle: "HTB Box"\n')
    markdown = note_to_markdown(note)
    assert 'tags: "htb"' in markdown
    assert 'target: "10.10.10.10"' in markdown
    assert "# HTB Box" in markdown

    destination = export_note_markdown(vault, note.id, tmp_path / "exports" / "note")
    assert destination.suffix == ".md"
    content = destination.read_text(encoding="utf-8")
    assert content.startswith('---\ntitle: "HTB Box"')
    assert "Body" in content

    renamed = export_note_markdown(vault, note.id, tmp_path / "note.txt")
    assert renamed.name == "note.md"

    empty = vault.create_node("Empty")
    assert note_to_markdown(empty).endswith("---\n")

    folder = vault.create_node("Folder", kind="folder")
    with pytest.raises(ValueError):
        export_note_markdown(vault, folder.id, tmp_path / "folder.md")
    with pytest.raises(ValueError):
        export_note_markdown(vault, 999, tmp_path / "missing.md")


def test_note_html_export(tmp_path: Path, vault: Vault) -> None:
    note = vault.create_node(
        "Finding <script>",
        content="# Finding\n\n<script>alert(1)</script>",
        tags="web,high",
        target="app.test",
        status="active",
        difficulty="medium",
        flag="flag{html}",
    )
    destination = export_note_html(vault, note.id, tmp_path / "finding.html")
    content = destination.read_text(encoding="utf-8")
    assert "<title>Finding &lt;script&gt;</title>" in content
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content
    assert "flag{html}" in content
    assert "Medium" in content
    assert "Target" in content


def test_vault_markdown_export_mirrors_and_deduplicates(tmp_path: Path, vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    vault.create_node("Duplicate", folder.id, content="one")
    vault.create_node("Duplicate", folder.id, content="two")
    vault.create_node("Root note", content="root")
    vault.create_node("Trash", content="gone")
    trash_note = next(node for node in vault.iter_notes() if node.title == "Trash")
    vault.delete_node(trash_note.id)

    destination = tmp_path / "mirror"
    count = export_vault_markdown(vault, destination)
    assert count == 3
    assert (destination / "Root note.md").exists()
    assert (destination / "Folder" / "Duplicate.md").exists()
    assert (destination / "Folder" / "Duplicate (2).md").exists()
    assert not (destination / "Trash.md").exists()
    assert "one" in (destination / "Folder" / "Duplicate.md").read_text(encoding="utf-8")
    assert "two" in (destination / "Folder" / "Duplicate (2).md").read_text(encoding="utf-8")


def test_vault_html_export(tmp_path: Path, vault: Vault) -> None:
    folder = vault.create_node("Folder", kind="folder")
    note = vault.create_node(
        "Visible",
        folder.id,
        content="# Visible\n\nSome <b>markup</b>",
        tags="web",
        target="app.test",
        status="done",
    )
    hidden = vault.create_node("Hidden", content="secret")
    vault.delete_node(hidden.id)

    destination = tmp_path / "report.html"
    assert export_vault_html(vault, tmp_path / "report") == 1
    content = destination.read_text(encoding="utf-8")
    assert "REDSCRIBE VAULT" in content
    assert "Visible" in content
    assert "secret" not in content
    assert "&lt;b&gt;markup&lt;/b&gt;" in content
    assert f'id="note-{note.id}"' in content
    assert "Filter notes" in content
    assert "vaultSearch" in content

    empty = Vault(tmp_path / "empty.db")
    try:
        assert export_vault_html(empty, tmp_path / "empty.html") == 0
        empty_content = (tmp_path / "empty.html").read_text(encoding="utf-8")
        assert "No notes to report yet." in empty_content
    finally:
        empty.close()


def test_safe_filename() -> None:
    assert safe_filename("Hello / World") == "Hello - World"
    assert safe_filename("", fallback="note-1", extension=".md") == "note-1.md"
    assert safe_filename("name.md", extension=".md") == "name.md.md"
