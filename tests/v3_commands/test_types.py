"""Tests for data-only command value types."""

from __future__ import annotations

import pytest

from redscribe.v3.commands.types import (
    ArgumentSpec,
    ArgumentType,
    CommandContext,
    CommandDenial,
    CommandEffect,
    CommandGroup,
    CommandGroupResult,
    CommandHit,
    CommandInvocation,
    CommandResult,
    CommandSpec,
    CommandStatus,
    DenialReason,
    PermissionLevel,
)
from redscribe.v3.entities.types import EntityKind, EntityRef


def test_command_group_parse_and_order() -> None:
    assert CommandGroup.parse("NAVIGATION") is CommandGroup.NAVIGATION
    assert CommandGroup.parse(" session ") is CommandGroup.SESSION
    assert CommandGroup.NAVIGATION.label == "Navigation"
    assert CommandGroup.NAVIGATION.order < CommandGroup.SESSION.order
    with pytest.raises(ValueError):
        CommandGroup.parse("missing")


def test_permission_level_satisfies() -> None:
    assert PermissionLevel.ADMIN.satisfies(PermissionLevel.WRITE)
    assert PermissionLevel.WRITE.satisfies(PermissionLevel.READ)
    assert not PermissionLevel.READ.satisfies(PermissionLevel.WRITE)


def test_argument_spec_validation() -> None:
    spec = ArgumentSpec(name="title", required=True, max_length=10)
    assert spec.validate_value(" hello ") == " hello "
    spec.validate_value("1234567890")
    with pytest.raises(ValueError):
        spec.validate_value("12345678901")
    with pytest.raises(ValueError):
        ArgumentSpec(name="Bad Name")
    with pytest.raises(ValueError):
        ArgumentSpec(name="mode", arg_type=ArgumentType.CHOICE)
    with pytest.raises(ValueError):
        ArgumentSpec(name="mode", arg_type=ArgumentType.CHOICE, choices=("a", "b")).validate_value(
            "c"
        )
    with pytest.raises(ValueError):
        ArgumentSpec(name="count", arg_type=ArgumentType.NUMBER).validate_value("abc")
    with pytest.raises(ValueError):
        ArgumentSpec(name="flag", arg_type=ArgumentType.BOOLEAN).validate_value("maybe")
    with pytest.raises(ValueError):
        ArgumentSpec(name="ref", arg_type=ArgumentType.ENTITY_REF).validate_value("nocolon")
    assert ArgumentSpec(name="flag", arg_type=ArgumentType.BOOLEAN).validate_value("YES") == "YES"


def test_argument_spec_as_dict() -> None:
    payload = ArgumentSpec(name="ref", arg_type=ArgumentType.ENTITY_REF, required=True).as_dict()
    assert payload["name"] == "ref"
    assert payload["arg_type"] == "entity_ref"
    assert payload["required"] is True
    assert payload["choices"] == []


def test_command_spec_validation() -> None:
    spec = CommandSpec(id="view.split", title="Split pane", group=CommandGroup.VIEW)
    assert spec.argument_names == ()
    assert spec.required_argument_names == ()
    assert spec.argument("missing") is None
    with pytest.raises(ValueError):
        CommandSpec(id="bad", title="Bad", group=CommandGroup.VIEW)
    with pytest.raises(ValueError):
        CommandSpec(id="view.split", title="", group=CommandGroup.VIEW)
    with pytest.raises(ValueError):
        CommandSpec(id="view.split", title="X", group=CommandGroup.VIEW, aliases=("split", "split"))
    with pytest.raises(ValueError):
        CommandSpec(
            id="view.split",
            title="X",
            group=CommandGroup.VIEW,
            arguments=(
                ArgumentSpec(name="first"),
                ArgumentSpec(name="second", required=True),
            ),
        )


def test_command_spec_as_dict() -> None:
    spec = CommandSpec(
        id="view.split",
        title="Split pane",
        group=CommandGroup.VIEW,
        description="Splits",
        keywords=("pane",),
        aliases=("split",),
        arguments=(ArgumentSpec(name="orientation", required=True),),
        effect=CommandEffect.OPEN_PANE,
        target_kind=EntityKind.NOTE,
        min_permission=PermissionLevel.WRITE,
    )
    payload = spec.as_dict()
    assert payload["id"] == "view.split"
    assert payload["group"] == "view"
    assert payload["effect"] == "open_pane"
    assert payload["target_kind"] == "note"
    assert payload["min_permission"] == 1
    assert payload["status"] == CommandStatus.ENABLED.value


def test_command_invocation_signature_and_dict() -> None:
    first = CommandInvocation("view.split", {"b": "2", "a": "1"})
    second = CommandInvocation("view.split", {"a": "1", "b": "2"})
    assert first.signature == second.signature
    payload = first.as_dict()
    assert payload["arguments"] == {"b": "2", "a": "1"}
    assert payload["source"] == "palette"
    with pytest.raises(ValueError):
        CommandInvocation("")
    with pytest.raises(ValueError):
        CommandInvocation("x.y", {"a": 1})  # type: ignore[dict-item]


def test_command_context_properties() -> None:
    entity = EntityRef.of("note", "alpha", "Alpha")
    selected = EntityRef.of("finding", "web-1", "SQLi")
    context = CommandContext(
        pane_id="pane:main",
        entity=entity,
        selection=(selected,),
        tags=("recon",),
        focus_active=True,
        capabilities=frozenset({"commands"}),
    )
    assert context.entity_ref == "note:alpha"
    assert context.selection_refs == ("finding:web-1",)
    payload = context.as_dict()
    assert payload["entity"]["label"] == "Alpha"
    assert payload["focus_active"] is True
    assert payload["capabilities"] == ["commands"]
    with pytest.raises(ValueError):
        CommandContext(pane_id="")
    with pytest.raises(ValueError):
        CommandContext(
            pane_id="p", selection=tuple(EntityRef.of("note", str(i)) for i in range(65))
        )


def test_results_and_denial_payloads() -> None:
    invocation = CommandInvocation("view.open")
    hit = CommandHit(
        command=CommandSpec("view.open", "Open", CommandGroup.VIEW), score=2.5, signals=("exact",)
    )
    result = CommandResult(
        invocation=invocation, accepted=True, data={"pane": "main"}, event_kind="command.executed"
    )
    group = CommandGroupResult(group=CommandGroup.VIEW, hits=(hit,))
    assert hit.as_dict()["score"] == 2.5
    assert result.as_dict()["data"] == {"pane": "main"}
    assert group.as_dict()["label"] == "View"
    denial = CommandDenial(DenialReason.DISABLED_CAPABILITY, "view.open", "blocked")
    assert denial.as_dict() == {
        "reason": "disabled_capability",
        "command_id": "view.open",
        "detail": "blocked",
    }
