"""Tests for navigation graph paths and focus-session transitions."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.commands.focus import FocusError, FocusSessionManager, FocusStatus
from redscribe.v3.commands.navigation import (
    NavEdge,
    NavigationError,
    NavigationGraph,
    NavNode,
    NavPath,
    default_navigation,
    register_core_navigation,
)
from redscribe.v3.entities.types import EntityRef


def test_graph_structure_and_validation() -> None:
    graph = default_navigation()
    assert graph.has("vault")
    assert graph.node("vault").label == "Vault"
    assert {node.id for node in graph.children("vault")} == {
        "pane:main",
        "pane:secondary",
        "folder:engagements",
        "findings",
        "evidence",
        "reports",
    }
    assert graph.parents("findings")[0].id == "vault"
    assert graph.size() == (7, 7)
    with pytest.raises(NavigationError):
        graph.node("unknown")
    with pytest.raises(NavigationError):
        graph.add_edge(NavEdge("vault", "unknown"))
    with pytest.raises(NavigationError):
        graph.add_edge(NavEdge("vault", "vault"))
    with pytest.raises(NavigationError):
        NavEdge("a", "b", cost=0)
    graph.add_edge(NavEdge("pane:main", "pane:secondary", "relates", 5.0))


def test_graph_path_and_breadcrumbs() -> None:
    graph = default_navigation()
    path = graph.path("vault", "findings")
    assert path.cost == 1.0
    assert path.as_dict()["nodes"] == ["vault", "findings"]
    via_folder = graph.path("vault", "findings")
    assert via_folder.nodes[0] == "vault"
    assert [node.id for node in graph.breadcrumbs("findings")] == ["vault", "findings"]
    assert graph.path("vault", "vault") == NavPath(("vault",), 0.0)
    graph.add_node(NavNode("orphan", "Orphan"))
    with pytest.raises(NavigationError):
        graph.path("vault", "orphan")


def test_graph_subtree_neighbors_and_context() -> None:
    graph = default_navigation()
    assert {node.id for node in graph.subtree("vault")} == {
        "pane:main",
        "pane:secondary",
        "folder:engagements",
        "findings",
        "evidence",
        "reports",
    }
    assert "pane:main" in {node.id for node in graph.neighbors("vault", limit=2)}
    with pytest.raises(NavigationError):
        graph.neighbors("vault", limit=0)
    ref = EntityRef.of("note", "alpha", "Alpha")
    graph.add_node(NavNode(str(ref), "Alpha", kind="note", parent="vault", entity=ref))
    graph.link("vault", str(ref))
    from redscribe.v3.commands.types import CommandContext

    context = CommandContext(pane_id="p", entity=ref)
    assert [node.id for node in graph.for_context(context)] == [str(ref)]


def test_graph_snapshot_roundtrip() -> None:
    graph = register_core_navigation(NavigationGraph())
    snapshot = graph.snapshot()
    assert len(snapshot["nodes"]) == 7
    restored = NavigationGraph()
    restored.load(snapshot)
    assert restored.size() == graph.size()
    assert [node.id for node in restored.breadcrumbs("findings")] == ["vault", "findings"]
    with pytest.raises(NavigationError):
        restored.load({"nodes": "bad", "edges": []})
    with pytest.raises(NavigationError):
        restored.load({"nodes": ["bad"], "edges": []})


def test_focus_lifecycle() -> None:
    manager = FocusSessionManager(clock=FixedClock(start=100.0))
    events: list[str] = []
    manager.subscribe(lambda action, session: events.append(action))
    assert manager.current() is None
    session = manager.start("Triage", target="note:alpha", restore_pane="pane:main")
    assert session.status is FocusStatus.ACTIVE
    assert session.started_at == 100.0
    assert manager.restore_target() == "pane:main"
    assert manager.pause().status is FocusStatus.PAUSED
    with pytest.raises(FocusError):
        manager.pause()
    with pytest.raises(FocusError):
        manager.start("Another")
    assert manager.resume().status is FocusStatus.ACTIVE
    assert manager.interrupt("notification").interruptions == 1
    ended = manager.end()
    assert ended.status is FocusStatus.ENDED
    assert ended.elapsed == 0.0
    assert manager.history() == (ended,)
    assert events == ["started", "paused", "resumed", "interrupted:notification", "ended"]
    with pytest.raises(FocusError):
        manager.end()


def test_focus_snapshot_restore_and_validation() -> None:
    manager = FocusSessionManager(clock=FixedClock(start=10.0))
    manager.start("Work", restore_pane="pane:side")
    snapshot = manager.snapshot()
    assert snapshot["current"]["status"] == "active"
    restored = FocusSessionManager()
    restored.load(snapshot)
    assert restored.current().label == "Work"
    assert restored.restore_target() == "pane:side"
    with pytest.raises(FocusError):
        restored.load({"history": "bad"})
    with pytest.raises(FocusError):
        FocusStatus.parse("unknown")
    status = manager.status()
    assert status["active"] is True
    assert status["completed"] == 0
