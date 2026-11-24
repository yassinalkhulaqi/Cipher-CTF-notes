"""Tests for pane trees, resizing, per-pane context, and persistence."""

from __future__ import annotations

import pytest

from redscribe.v3.commands.workspace import (
    MemoryPanePersistence,
    PaneNode,
    PaneOrientation,
    PaneSpec,
    PaneTree,
    WorkspaceError,
    WorkspaceManager,
    WorkspaceState,
    default_workspace,
)


def _pane(identifier: str, title: str = "") -> PaneSpec:
    return PaneSpec(id=identifier, title=title or identifier)


def test_pane_spec_validation() -> None:
    pane = _pane("pane:main", "Main")
    assert pane.as_dict()["id"] == "pane:main"
    with pytest.raises(WorkspaceError):
        _pane("Bad Pane")
    with pytest.raises(WorkspaceError):
        PaneSpec(id="pane:x", title="")
    with pytest.raises(WorkspaceError):
        PaneSpec(id="pane:x", title="X", size=0)
    with pytest.raises(WorkspaceError):
        PaneSpec(id="pane:x", title="X", min_size=2.0)


def test_pane_node_invariants() -> None:
    with pytest.raises(WorkspaceError):
        PaneNode(pane=_pane("pane:a"), orientation=PaneOrientation.VERTICAL)
    with pytest.raises(WorkspaceError):
        PaneNode()
    with pytest.raises(WorkspaceError):
        PaneNode.branch(
            PaneNode.leaf(_pane("pane:a")),
            PaneNode.leaf(_pane("pane:b")),
            PaneOrientation.VERTICAL,
            2.0,
        )
    assert PaneNode.leaf(_pane("pane:a")).is_leaf


def test_pane_tree_insert_and_paths() -> None:
    tree = PaneTree(PaneNode.leaf(_pane("pane:a")))
    tree = tree.insert("pane:a", _pane("pane:b"), PaneOrientation.VERTICAL)
    assert [pane.id for pane in tree.leaves()] == ["pane:a", "pane:b"]
    assert tree.paths() == {"pane:a": (0,), "pane:b": (1,)}
    assert tree.find("pane:a") == (0,)
    assert tree.find("pane:missing") is None
    with pytest.raises(WorkspaceError):
        tree.insert("pane:missing", _pane("pane:c"), PaneOrientation.VERTICAL)
    with pytest.raises(WorkspaceError):
        tree.insert("pane:a", _pane("pane:a"), PaneOrientation.VERTICAL)
    with pytest.raises(WorkspaceError):
        tree.node_at((0, 0))


def test_pane_tree_resize_remove_and_update() -> None:
    tree = PaneTree(PaneNode.leaf(_pane("pane:a")))
    tree = tree.insert("pane:a", _pane("pane:b"), PaneOrientation.VERTICAL, ratio=0.4)
    tree = tree.resize("pane:a", 0.3)
    assert tree.root.ratio == 0.3
    tree = tree.resize("pane:b", 0.25)
    assert tree.root.ratio == 0.75
    tree = tree.update("pane:b", title="Secondary", context_ref="note:alpha")
    updated = next(pane for pane in tree.leaves() if pane.id == "pane:b")
    assert updated.title == "Secondary"
    assert updated.context_ref == "note:alpha"
    with pytest.raises(WorkspaceError):
        tree.update("pane:b", shell="rm -rf /")  # type: ignore[arg-type]
    with pytest.raises(WorkspaceError):
        tree.resize("pane:a", 1.5)
    remaining = tree.remove("pane:b")
    assert [pane.id for pane in remaining.leaves()] == ["pane:a"]
    with pytest.raises(WorkspaceError):
        remaining.remove("pane:a")
    with pytest.raises(WorkspaceError):
        tree.remove("pane:missing")


def test_pinned_pane_cannot_close() -> None:
    pane = PaneSpec(id="pane:pin", title="Pinned", closable=False)
    tree = PaneTree(PaneNode.leaf(pane))
    tree = tree.insert("pane:pin", _pane("pane:b"), PaneOrientation.HORIZONTAL)
    with pytest.raises(WorkspaceError):
        tree.remove("pane:pin")
    assert tree.remove("pane:b").leaves()[0].id == "pane:pin"


def test_pane_tree_snapshot_roundtrip() -> None:
    tree = PaneTree(PaneNode.leaf(_pane("pane:a")))
    tree = tree.insert("pane:a", _pane("pane:b"), PaneOrientation.HORIZONTAL, ratio=0.35)
    payload = tree.as_dict()
    restored = PaneTree.from_dict(payload)
    assert restored.paths() == tree.paths()
    assert restored.root.ratio == 0.35
    assert restored.root.orientation is PaneOrientation.HORIZONTAL
    with pytest.raises(WorkspaceError):
        PaneTree.from_dict({"children": []})


def test_workspace_state_requires_valid_active_pane() -> None:
    tree = PaneTree(PaneNode.leaf(_pane("pane:a")))
    assert WorkspaceState(id="main", tree=tree, active_pane="pane:a").as_dict()["id"] == "main"
    with pytest.raises(WorkspaceError):
        WorkspaceState(id="main", tree=tree, active_pane="pane:missing")


def test_workspace_manager_split_resize_close() -> None:
    manager = default_workspace()
    assert manager.active().id == "pane:main"
    assert manager.panes() == (manager.active(),)
    new_pane = manager.split(
        "pane:main", "horizontal", new_pane_id="pane:side", title="Side", ratio=0.4
    )
    assert new_pane.id == "pane:side"
    assert [pane.id for pane in manager.panes()] == ["pane:main", "pane:side"]
    assert manager.active().id == "pane:side"
    manager.resize("pane:side", 0.3)
    assert manager.state.tree.root.ratio == 0.7
    manager.activate("pane:main")
    assert manager.active().id == "pane:main"
    closed = manager.close("pane:side")
    assert closed.id == "pane:main"
    assert len(manager.panes()) == 1
    with pytest.raises(WorkspaceError):
        manager.close("pane:main")
    with pytest.raises(WorkspaceError):
        manager.activate("pane:missing")
    with pytest.raises(WorkspaceError):
        manager.split("pane:main", "diagonal")


def test_workspace_manager_context_and_persistence() -> None:
    persistence = MemoryPanePersistence()
    manager = WorkspaceManager(default_workspace().state, persistence=persistence)
    manager.set_context("pane:main", "note:alpha")
    assert manager.active().context_ref == "note:alpha"
    manager.rename("pane:main", "Notes")
    assert manager.active().title == "Notes"
    snapshot = manager.save()
    assert persistence.load() == snapshot
    reloaded = WorkspaceManager(default_workspace().state, persistence=persistence)
    assert reloaded.load() is True
    assert reloaded.active().context_ref == "note:alpha"
    assert reloaded.active().title == "Notes"
    assert WorkspaceManager(default_workspace().state).load() is False
    with pytest.raises(WorkspaceError):
        manager.restore({"bad": True})
    with pytest.raises(WorkspaceError):
        manager.set_context("pane:missing", "note:x")


def test_pane_orientation_parse() -> None:
    assert PaneOrientation.parse("row") is PaneOrientation.HORIZONTAL
    assert PaneOrientation.parse("COLUMN") is PaneOrientation.VERTICAL
    assert PaneOrientation.parse("vertical") is PaneOrientation.VERTICAL
    with pytest.raises(WorkspaceError):
        PaneOrientation.parse("diagonal")
