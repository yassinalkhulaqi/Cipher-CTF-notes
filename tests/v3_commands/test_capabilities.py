"""Tests for capability and permission denial of commands."""

from __future__ import annotations

import pytest

from redscribe.v3.capabilities import CAP_COMMANDS, Capabilities
from redscribe.v3.commands.capabilities import (
    CommandCapabilityGuard,
    CommandDeniedError,
    CommandPolicy,
)
from redscribe.v3.commands.registry import default_registry
from redscribe.v3.commands.types import (
    CommandContext,
    CommandGroup,
    CommandSpec,
    DenialReason,
    PermissionLevel,
)


def test_guard_allows_read_command() -> None:
    registry = default_registry()
    guard = CommandCapabilityGuard()
    navigation = registry.require("navigation.back")
    assert guard.allow(navigation)
    assert guard.denial_for(navigation) is None
    guard.check(navigation)


def test_guard_denies_write_command_for_reader() -> None:
    registry = default_registry()
    guard = CommandCapabilityGuard()
    create = registry.require("create.note")
    assert not guard.allow(create)
    denial = guard.denial_for(create)
    assert denial is not None
    assert denial.reason is DenialReason.INSUFFICIENT_PERMISSION
    with pytest.raises(CommandDeniedError) as error:
        guard.check(create)
    assert error.value.denial.command_id == "create.note"
    assert guard.allow(create, actor_level=PermissionLevel.WRITE)


def test_guard_denies_disabled_capability() -> None:
    registry = default_registry()
    disabled = Capabilities(enabled=frozenset({"findings"}))
    guard = CommandCapabilityGuard(capabilities=disabled)
    navigation = registry.require("navigation.back")
    denial = guard.denial_for(navigation)
    assert denial is not None
    assert denial.reason is DenialReason.DISABLED_CAPABILITY
    assert "commands" in denial.detail
    assert guard.denial_for(navigation, _context_without_capabilities()) is not None


def _context_without_capabilities() -> CommandContext:
    return CommandContext(pane_id="pane:main", capabilities=frozenset())


def test_guard_denies_disabled_and_blocked_commands() -> None:
    from redscribe.v3.commands.types import CommandStatus

    disabled = CommandSpec("test.off", "Off", CommandGroup.SYSTEM, status=CommandStatus.DISABLED)
    guard = CommandCapabilityGuard(
        policy=CommandPolicy(denied_commands=frozenset({"test.blocked"}))
    )
    blocked = CommandSpec("test.blocked", "Blocked", CommandGroup.SYSTEM)
    assert guard.denial_for(disabled).reason is DenialReason.DISABLED_COMMAND  # type: ignore[union-attr]
    assert guard.denial_for(blocked).reason is DenialReason.DISABLED_COMMAND  # type: ignore[union-attr]


def test_guard_denies_missing_selection() -> None:
    spec = CommandSpec("test.selection", "Selected", CommandGroup.INSPECT, requires_selection=True)
    guard = CommandCapabilityGuard()
    denial = guard.denial_for(spec, _context_without_capabilities())
    assert denial is not None
    assert denial.reason is DenialReason.DISABLED_CAPABILITY
    context = CommandContext(pane_id="p", capabilities=frozenset({CAP_COMMANDS}))
    denial = guard.denial_for(spec, context)
    assert denial is not None
    assert denial.reason is DenialReason.MISSING_CONTEXT


def test_policy_overrides_capability_and_level() -> None:
    spec = CommandSpec("custom.action", "Custom", CommandGroup.SYSTEM, capability="custom")
    policy = CommandPolicy(
        command_capabilities={"custom.action": "alternate"},
        group_capabilities={CommandGroup.SYSTEM: "fallback"},
        command_levels={"custom.action": PermissionLevel.ADMIN},
    )
    assert policy.capability_for(spec) == "alternate"
    assert policy.level_for(spec) is PermissionLevel.ADMIN
    assert policy.validate() == ()
    guard = CommandCapabilityGuard(
        capabilities=Capabilities(enabled=frozenset({CAP_COMMANDS, "alternate"})),
        policy=policy,
    )
    assert not guard.allow(spec)
    assert guard.allow(spec, actor_level=PermissionLevel.ADMIN)


def test_guard_filter_and_permissions() -> None:
    registry = default_registry()
    guard = CommandCapabilityGuard()
    allowed = guard.filter(registry.all())
    assert len(allowed) < registry.size()
    assert all(spec.min_permission is PermissionLevel.READ for spec in allowed)
    all_allowed = guard.filter(registry.all(), actor_level=PermissionLevel.ADMIN)
    assert len(all_allowed) == registry.size()
