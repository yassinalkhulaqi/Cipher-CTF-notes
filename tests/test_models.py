from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from redscribe.domain.models import (
    FlagHit,
    Node,
    NodeTree,
    SearchHit,
    Snippet,
    TagCount,
    Template,
    VaultStats,
)
from redscribe.domain.utils import utc_now


def _node(**changes: object) -> Node:
    values: dict[str, object] = {
        "id": 1,
        "parent_id": None,
        "title": "HTB Corporate",
        "kind": "note",
        "content": "flag{demo}",
        "tags": "htb, windows",
        "target": "10.10.10.42",
        "status": "active",
        "difficulty": "medium",
        "flag": "flag{demo}",
        "pinned": True,
        "sort_order": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "deleted_at": None,
    }
    values.update(changes)
    return Node(**values)  # type: ignore[arg-type]


def test_node_is_frozen_and_self_describing() -> None:
    node = _node()
    assert node.is_note
    assert not node.is_folder
    assert not node.is_trashed
    assert node.tag_list == ["htb", "windows"]
    assert node.status_label == "Active"
    assert node.status_icon == "●"
    assert node.difficulty_label == "Medium"
    with pytest.raises(FrozenInstanceError):
        node.title = "Changed"  # type: ignore[misc]


def test_node_rejects_invalid_enumerations() -> None:
    with pytest.raises(ValueError, match="kind"):
        _node(kind="workspace")
    with pytest.raises(ValueError, match="status"):
        _node(status="later")
    with pytest.raises(ValueError, match="difficulty"):
        _node(difficulty="nightmare")


def test_node_folder_and_trash_helpers() -> None:
    folder = _node(kind="folder", title="Engagements", status="todo", difficulty="")
    trashed = _node(deleted_at=utc_now())
    assert folder.is_folder
    assert folder.status_icon == "○"
    assert folder.difficulty_label == "Unrated"
    assert trashed.is_trashed


def test_snippet_helpers_are_immutable() -> None:
    snippet = Snippet(
        title="Nmap quick scan",
        command="nmap -sV {{target}}",
        description="Service detection",
        tags="recon,nmap",
        builtin=True,
        builtin_key="nmap-quick-scan",
    )
    assert snippet.tag_list == ["recon", "nmap"]
    assert snippet.category == "recon"
    assert Snippet("Fallback", "id").category == "misc"
    with pytest.raises(FrozenInstanceError):
        snippet.title = "Changed"  # type: ignore[misc]


def test_record_value_objects_and_defaults() -> None:
    assert VaultStats() == VaultStats(notes=0, folders=0, flags=0, targets=0)
    assert TagCount("web", 2).count == 2
    assert SearchHit(1, "Title", "Path", "Snippet").rank == 0.0
    assert FlagHit("flag{x}", 1, "Title", "Path").manual is False
    template = Template("ctf", "CTF", "Challenge", "# {{title}}")
    with pytest.raises(FrozenInstanceError):
        template.name = "Changed"  # type: ignore[misc]


def test_node_tree_keeps_mutable_children() -> None:
    tree = NodeTree(_node(kind="folder"))
    child = NodeTree(_node(id=2), depth=1)
    tree.children.append(child)
    assert tree.children == [child]


def test_domain_sources_do_not_import_ui_or_storage() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "redscribe" / "domain"
    forbidden = ("import tkinter", "from tkinter", "import sqlite3", "from redscribe.db")
    for source in package.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), source.name
