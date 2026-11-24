"""Tests for the additive command registry and its default catalog."""

from __future__ import annotations

import pytest

from redscribe.v3.commands.registry import (
    CommandRegistry,
    DuplicateCommandError,
    default_commands,
    default_registry,
)
from redscribe.v3.commands.types import CommandGroup, CommandSpec, CommandStatus


def test_default_catalog_is_broad_and_valid() -> None:
    registry = default_registry()
    assert registry.size() == len(default_commands()) == 22
    assert set(registry.groups()) == {
        CommandGroup.NAVIGATION,
        CommandGroup.CREATE,
        CommandGroup.INSPECT,
        CommandGroup.VIEW,
        CommandGroup.SESSION,
        CommandGroup.AUTOMATION,
        CommandGroup.SYSTEM,
    }
    assert registry.validate() == ()
    assert registry.get("goto") is registry.get("navigation.goto")
    assert registry.resolve_id("g") == "navigation.goto"
    assert registry.require("create.note").title == "New note"


def test_registry_rejects_duplicates() -> None:
    registry = CommandRegistry()
    spec = CommandSpec("view.split", "Split", CommandGroup.VIEW, aliases=("view.alt",))
    assert registry.register(spec) is spec
    with pytest.raises(DuplicateCommandError):
        registry.register(spec)
    with pytest.raises(DuplicateCommandError):
        registry.register(CommandSpec("view.alt", "Conflict", CommandGroup.VIEW))
    with pytest.raises(DuplicateCommandError):
        registry.register(
            CommandSpec("view.other", "Other", CommandGroup.VIEW, aliases=("view.alt",))
        )
    with pytest.raises(KeyError):
        registry.require("missing.command")


def test_registry_ordering_and_filters() -> None:
    registry = CommandRegistry()
    registry.register_many(
        [
            CommandSpec("view.z", "Z", CommandGroup.VIEW, order=20),
            CommandSpec("navigation.a", "A", CommandGroup.NAVIGATION, order=5),
            CommandSpec("view.a", "A", CommandGroup.VIEW, order=5),
            CommandSpec("system.hidden", "H", CommandGroup.SYSTEM, status=CommandStatus.HIDDEN),
            CommandSpec("system.off", "O", CommandGroup.SYSTEM, status=CommandStatus.DISABLED),
        ]
    )
    assert [spec.id for spec in registry.all()][:3] == [
        "navigation.a",
        "view.a",
        "view.z",
    ]
    assert [spec.id for spec in registry.by_group(CommandGroup.VIEW)] == ["view.a", "view.z"]
    assert "system.hidden" not in [spec.id for spec in registry.enabled()]
    assert len(registry.enabled()) == 3


def test_registry_snapshot_roundtrip() -> None:
    source = default_registry()
    payload = source.snapshot()
    assert len(payload["commands"]) == 22
    assert payload["aliases"]["goto"] == "navigation.goto"
    rebuilt = CommandRegistry()
    rebuilt.register_many(
        tuple(
            CommandSpec(
                id=str(item["id"]),
                title=str(item["title"]),
                group=CommandGroup.parse(str(item["group"])),
                description=str(item["description"]),
            )
            for item in payload["commands"]
        )
    )
    assert rebuilt.size() == source.size()
