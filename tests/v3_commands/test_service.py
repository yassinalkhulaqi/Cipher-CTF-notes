"""Tests for the command-center application service."""

from __future__ import annotations

import pytest

from redscribe.v3.capabilities import CAP_COMMANDS, Capabilities
from redscribe.v3.clock import FixedClock
from redscribe.v3.commands.macros import MacroError
from redscribe.v3.commands.service import (
    EXECUTED_EVENT,
    FOCUS_EVENT,
    MACRO_EVENT,
    WORKSPACE_EVENT,
    CommandCenterService,
)
from redscribe.v3.commands.types import (
    CommandInvocation,
    DenialReason,
    PermissionLevel,
)
from redscribe.v3.entities.types import EntityRef


def _writer() -> CommandCenterService:
    service = CommandCenterService(clock=FixedClock(start=100.0))
    service.actor_level = PermissionLevel.WRITE
    return service


def test_manifest_and_command_listing() -> None:
    service = _writer()
    manifest = service.manifest()
    assert len(manifest["commands"]) == 22
    assert "navigation" in manifest["groups"]
    assert manifest["permission"] == 1
    assert service.list_commands()
    assert all(spec.capability == CAP_COMMANDS for spec in service.list_commands())


def test_suggest_groups_and_usage() -> None:
    service = _writer()
    groups = service.suggest("note")
    assert groups
    assert groups[0].hits[0].command.id == "create.note"
    service.usage.record(CommandInvocation("create.note"), now=100.0)
    boosted = service.suggest("note")
    assert boosted[0].hits[0].score >= groups[0].hits[0].score


def test_execute_emits_event_and_records_usage() -> None:
    service = _writer()
    result = service.execute(
        CommandInvocation("create.note", {"title": "Demo"}), request_id="req_1"
    )
    assert result.accepted
    assert result.event_kind == EXECUTED_EVENT
    assert result.invocation.arguments == {"title": "Demo"}
    events = service.bus.of_kind(EXECUTED_EVENT)
    assert len(events) == 1
    assert events[0].event.payload["command_id"] == "create.note"
    assert events[0].request_id == "req_1"
    assert service.usage.stats("create.note").count == 1


def test_execute_validates_arguments() -> None:
    service = _writer()
    from redscribe.v3.commands.parser import BindingError

    with pytest.raises(BindingError):
        service.execute(CommandInvocation("create.note", {}))
    with pytest.raises(ValueError):
        service.execute(CommandInvocation("create.finding", {"title": "X", "severity": "extreme"}))
    with pytest.raises(ValueError):
        service.execute(CommandInvocation("create.note", {"title": "X", "extra": "y"}))


def test_execute_denies_unknown_and_capability() -> None:
    service = _writer()
    from redscribe.v3.commands.capabilities import CommandDeniedError

    with pytest.raises(CommandDeniedError) as unknown:
        service.execute(CommandInvocation("does.not_exist"))
    assert unknown.value.denial.reason is DenialReason.UNKNOWN_COMMAND
    service.actor_level = PermissionLevel.READ
    with pytest.raises(CommandDeniedError) as denied:
        service.execute(CommandInvocation("create.note", {"title": "X"}))
    assert denied.value.denial.reason is DenialReason.INSUFFICIENT_PERMISSION
    assert service.bus.size() == 0


def test_execute_macro_command_records_sequence() -> None:
    service = _writer()
    service.execute(CommandInvocation("automation.record", {"name": "demo"}))
    assert service.recorder.is_recording
    service.execute(CommandInvocation("navigation.goto", {"ref": "note:alpha"}))
    service.execute(CommandInvocation("session.start", {"label": "Triage"}))
    macro = service.stop_macro()
    assert macro.command_ids == ("navigation.goto", "session.start")
    assert service.library.size() == 1
    assert service.bus.of_kind(MACRO_EVENT)
    expanded = service.run_macro("demo")
    assert [item.command_id for item in expanded] == list(macro.command_ids)
    with pytest.raises(MacroError):
        service.run_macro("missing")


def test_execute_focus_and_workspace_effects() -> None:
    service = _writer()
    service.execute(CommandInvocation("session.start", {"label": "Deep work"}))
    assert service.focus.current().label == "Deep work"
    assert service.bus.of_kind(FOCUS_EVENT)
    service.execute(CommandInvocation("session.pause"))
    assert service.focus.current().status.value == "paused"
    service.execute(CommandInvocation("session.resume"))
    service.execute(CommandInvocation("session.end"))
    assert service.focus.current().status.value == "ended"
    service.execute(CommandInvocation("view.split", {"orientation": "vertical"}))
    assert len(service.workspace.panes()) == 2
    assert service.bus.of_kind(WORKSPACE_EVENT)
    service.execute(CommandInvocation("view.close", {"pane": "pane:2"}))
    assert len(service.workspace.panes()) == 1


def test_context_resolution_from_pane_and_entity() -> None:
    service = _writer()
    service.workspace.set_context("pane:main", "note:alpha")
    context = service.resolve_context()
    assert context.entity_ref == "note:alpha"
    assert context.pane_id == "pane:main"
    assert context.workspace_id == "main"
    service.focus_start("Session", restore_pane="pane:main")
    assert service.resolve_context().focus_active is True
    service.focus_end()


def test_register_entity_and_breadcrumbs() -> None:
    service = _writer()
    ref = EntityRef.of("note", "alpha", "Alpha")
    service.register_entity(ref, parent="vault")
    crumbs = service.breadcrumbs(str(ref))
    assert [node.id for node in crumbs] == ["vault", str(ref)]
    assert service.breadcrumbs("note:missing") == ()


def test_full_snapshot_restore_roundtrip() -> None:
    service = _writer()
    service.execute(CommandInvocation("navigation.back"))
    service.workspace.split("pane:main", "horizontal", new_pane_id="pane:side")
    snapshot = service.snapshot()
    assert set(snapshot) == {"usage", "macros", "focus", "workspace", "navigation"}
    restored = CommandCenterService()
    restored.restore(snapshot)
    assert restored.usage.size() == service.usage.size()
    assert [pane.id for pane in restored.workspace.panes()] == ["pane:main", "pane:side"]
    assert restored.navigation.size() == service.navigation.size()


def test_disabled_capability_blocks_suggest() -> None:
    service = CommandCenterService(capabilities=Capabilities(enabled=frozenset({"findings"})))
    service.actor_level = PermissionLevel.WRITE
    assert service.list_commands() == ()
    assert service.suggest("note") == ()
