"""Tests for command-center API v3 namespace routes."""

from __future__ import annotations

from typing import Any

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import V3Router
from redscribe.v3.commands.types import PermissionLevel
from redscribe.v3.entities.ids import new_id
from redscribe.v3.entities.types import EntityKind
from redscribe.v3.namespaces import commands as namespace


@pytest.fixture(autouse=True)
def _isolated_service() -> Any:
    previous = namespace.set_service(None)
    yield
    namespace.set_service(previous)


def _router() -> V3Router:
    router = V3Router()
    namespace.register(router)
    return router


def test_registered_routes_and_manifest() -> None:
    router = _router()
    assert router.size() == 31
    assert "commands" in router.namespaces()
    assert router.get("commands", "manifest") is not None
    assert router.get("commands", "manifest").public is True  # type: ignore[union-attr]
    manifest = router.dispatch("commands", "manifest")
    assert len(manifest["commands"]) == 22
    assert "system" not in router.namespaces()
    with pytest.raises(V3Error):
        router.dispatch("commands", "unknown")


def test_list_suggest_and_context_routes() -> None:
    router = _router()
    listed = router.dispatch("commands", "list", {"pane": "pane:main", "permission": "READ"})
    assert listed["context"]["pane_id"] == "pane:main"
    assert listed["commands"]
    suggested = router.dispatch("commands", "suggest", {"query": "focus", "limit": 5})
    assert suggested["groups"]
    assert all(len(group["hits"]) <= 5 for group in suggested["groups"])
    context = router.dispatch("commands", "context", {"pane": "pane:custom"})
    assert context["context"]["workspace_id"] == "main"
    with pytest.raises(V3Error):
        router.dispatch("commands", "suggest", {"query": "x", "limit": -1})


def test_execute_route_and_capability_denial() -> None:
    router = _router()
    result = router.dispatch(
        "commands",
        "execute",
        {"command_id": "navigation.back", "pane": "pane:main"},
        {"x-request-id": "req_test"},
    )
    assert result["result"]["accepted"] is True
    assert result["focus"]["active"] is False
    events = namespace.get_service().bus.of_kind("command.executed")
    assert events[0].request_id == "req_test"
    with pytest.raises(V3Error) as denial:
        router.dispatch(
            "commands", "execute", {"command_id": "create.note", "arguments": {"title": "X"}}
        )
    assert denial.value.code.value == "forbidden"
    assert denial.value.context["reason"] == "insufficient_permission"
    with pytest.raises(V3Error) as unknown:
        router.dispatch("commands", "execute", {"command_id": "nope.nope"})
    assert unknown.value.code.value == "forbidden"


def test_execute_route_rejects_bad_payloads() -> None:
    router = _router()
    with pytest.raises(V3Error):
        router.dispatch("commands", "execute", {})
    with pytest.raises(V3Error):
        router.dispatch("commands", "execute", {"command_id": "create.note", "arguments": []})


def test_usage_routes() -> None:
    router = _router()
    service = namespace.get_service()
    service.actor_level = PermissionLevel.WRITE
    router.dispatch(
        "commands",
        "usage.record",
        {"command_id": "navigation.back", "pane": "pane:main"},
    )
    recent = router.dispatch("commands", "usage.recent", {"limit": 3})
    assert recent["recent"][0]["command_id"] == "navigation.back"
    frequent = router.dispatch("commands", "usage.frequent", {"limit": 3})
    assert frequent["frequent"][0]["count"] == 1
    executed = router.dispatch(
        "commands", "execute", {"command_id": "navigation.goto", "arguments": {"ref": "note:alpha"}}
    )
    assert executed["result"]["accepted"] is True
    with pytest.raises(V3Error):
        router.dispatch("commands", "usage.recent", {"limit": 0})


def test_macro_routes() -> None:
    router = _router()
    service = namespace.get_service()
    service.actor_level = PermissionLevel.WRITE
    started = router.dispatch("commands", "macros.start", {"name": "demo"})
    assert started["recorder"]["recording"] is True
    router.dispatch("commands", "execute", {"command_id": "navigation.back"})
    stored = router.dispatch("commands", "macros.stop", {})
    macro_id = stored["macro"]["id"]
    listed = router.dispatch("commands", "macros.list", {})
    assert listed["macros"][0]["name"] == "demo"
    expanded = router.dispatch("commands", "macros.run", {"name": "demo"})
    assert expanded["steps"][0]["command_id"] == "navigation.back"
    again = router.dispatch("commands", "macros.expand", {"name": "demo"})
    assert again["steps"] == expanded["steps"]
    assert router.dispatch("commands", "macros.delete", {"macro_id": macro_id})["deleted"] is True
    with pytest.raises(V3Error):
        router.dispatch("commands", "macros.run", {"name": "missing"})
    with pytest.raises(V3Error):
        router.dispatch("commands", "macros.start", {"name": ""})


def test_navigation_and_focus_routes() -> None:
    router = _router()
    crumbs = router.dispatch("commands", "nav.breadcrumbs", {"ref": "vault"})
    assert crumbs["crumbs"][0]["id"] == "vault"
    neighbors = router.dispatch("commands", "nav.neighbors", {"ref": "vault", "limit": 2})
    assert len(neighbors["neighbors"]) == 2
    with pytest.raises(V3Error):
        router.dispatch("commands", "nav.neighbors", {"ref": "missing"})
    started = router.dispatch("commands", "focus.start", {"label": "Work"})
    assert started["session"]["status"] == "active"
    assert router.dispatch("commands", "focus.status", {})["focus"]["active"] is True
    assert router.dispatch("commands", "focus.pause", {})["session"]["status"] == "paused"
    assert router.dispatch("commands", "focus.resume", {})["session"]["status"] == "active"
    assert router.dispatch("commands", "focus.end", {})["session"]["status"] == "ended"
    with pytest.raises(V3Error):
        router.dispatch("commands", "focus.pause", {})


def test_workspace_routes() -> None:
    router = _router()
    snapshot = router.dispatch("commands", "workspace.snapshot", {})
    assert [pane["id"] for pane in snapshot["panes"]] == ["pane:main"]
    split = router.dispatch(
        "commands",
        "workspace.split",
        {"pane": "pane:main", "orientation": "horizontal", "new_pane": "pane:side"},
    )
    assert split["pane"]["id"] == "pane:side"
    assert len(split["panes"]) == 2
    resized = router.dispatch("commands", "workspace.resize", {"pane": "pane:side", "size": 0.3})
    assert resized["workspace"]["tree"]["root"]["ratio"] == 0.7
    contexted = router.dispatch(
        "commands", "workspace.context", {"pane": "pane:side", "ref": "note:alpha"}
    )
    assert contexted["pane"]["context_ref"] == "note:alpha"
    activated = router.dispatch("commands", "workspace.activate", {"pane": "pane:main"})
    assert activated["pane"]["id"] == "pane:main"
    closed = router.dispatch("commands", "workspace.close", {"pane": "pane:side"})
    assert [pane["id"] for pane in closed["panes"]] == ["pane:main"]
    restored = router.dispatch(
        "commands", "workspace.restore", {"workspace": snapshot["workspace"]}
    )
    assert restored["workspace"] == snapshot["workspace"]
    with pytest.raises(V3Error):
        router.dispatch("commands", "workspace.close", {"pane": "pane:main"})


def test_state_permission_and_install_routes() -> None:
    router = _router()
    service = namespace.get_service()
    service.actor_level = PermissionLevel.WRITE
    ref = new_id(EntityKind.NOTE, prefix="alpha")
    assert str(ref).startswith("note:alpha")
    snap = router.dispatch("commands", "state.snapshot", {})
    assert set(snap["snapshot"]) == {"usage", "macros", "focus", "workspace", "navigation"}
    level = router.dispatch("commands", "permission.set", {"level": "admin"})
    assert level["permission"] == 2
    with pytest.raises(V3Error):
        router.dispatch("commands", "permission.set", {"level": "superuser"})
    restored = router.dispatch("commands", "state.restore", {"snapshot": snap["snapshot"]})
    assert set(restored["snapshot"]) == set(snap["snapshot"])
    with pytest.raises(V3Error):
        router.dispatch("commands", "state.restore", {"snapshot": []})

    fresh = V3Router()
    assert fresh.install_namespaces() > 0
    assert fresh.get("commands", "manifest") is not None
    assert namespace.get_service() is service
