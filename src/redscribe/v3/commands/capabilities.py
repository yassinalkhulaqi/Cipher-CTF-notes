"""Capability and permission checks for command execution."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from redscribe.v3.capabilities import CAP_COMMANDS, Capabilities
from redscribe.v3.commands.types import (
    CommandContext,
    CommandDenial,
    CommandGroup,
    CommandSpec,
    DenialReason,
    PermissionLevel,
)


class CommandDeniedError(RuntimeError):
    """Raised when a command is not allowed to run."""

    def __init__(self, denial: CommandDenial) -> None:
        super().__init__(denial.detail or denial.reason.value)
        self.denial = denial


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    """Declarative policy overriding capability and permission defaults."""

    master_capability: str = CAP_COMMANDS
    group_capabilities: dict[CommandGroup, str] = field(default_factory=dict)
    command_capabilities: dict[str, str] = field(default_factory=dict)
    command_levels: dict[str, PermissionLevel] = field(default_factory=dict)
    denied_commands: frozenset[str] = frozenset()

    def capability_for(self, spec: CommandSpec) -> str:
        """Return the effective capability for a command."""
        if spec.id in self.command_capabilities:
            return self.command_capabilities[spec.id]
        if spec.group in self.group_capabilities:
            return self.group_capabilities[spec.group]
        return spec.capability

    def level_for(self, spec: CommandSpec) -> PermissionLevel:
        """Return the effective permission level for a command."""
        return self.command_levels.get(spec.id, spec.min_permission)

    def validate(self) -> tuple[str, ...]:
        """Return policy integrity problems."""
        problems: list[str] = []
        if not self.master_capability:
            problems.append("master capability cannot be blank")
        for command_id in self.command_capabilities:
            if not command_id:
                problems.append("command capability key cannot be blank")
        return tuple(sorted(problems))


@dataclass(slots=True)
class CommandCapabilityGuard:
    """Central gate used by the service and API namespace."""

    capabilities: Capabilities = field(default_factory=Capabilities)
    policy: CommandPolicy = field(default_factory=CommandPolicy)

    def check(
        self,
        spec: CommandSpec,
        context: CommandContext | None = None,
        *,
        actor_level: PermissionLevel = PermissionLevel.READ,
    ) -> None:
        """Raise :class:`CommandDeniedError` when a command must not run."""
        if spec.id in self.policy.denied_commands:
            self._deny(spec, DenialReason.DISABLED_COMMAND, f"Command is blocked: {spec.id}")
        if spec.status.value != "enabled":
            self._deny(spec, DenialReason.DISABLED_COMMAND, f"Command is disabled: {spec.id}")
        required = self.policy.capability_for(spec)
        if not self.capabilities.has(self.policy.master_capability):
            self._deny(
                spec,
                DenialReason.DISABLED_CAPABILITY,
                f"Capability is disabled: {self.policy.master_capability}",
            )
        if not self.capabilities.has(required):
            self._deny(
                spec, DenialReason.DISABLED_CAPABILITY, f"Capability is disabled: {required}"
            )
        if context is not None and required not in context.capabilities:
            self._deny(spec, DenialReason.DISABLED_CAPABILITY, f"Pane lacks capability: {required}")
        level = self.policy.level_for(spec)
        if not actor_level.satisfies(level):
            self._deny(
                spec,
                DenialReason.INSUFFICIENT_PERMISSION,
                f"Command '{spec.id}' requires {level.name}",
            )
        if spec.requires_selection and (context is None or not context.selection):
            self._deny(spec, DenialReason.MISSING_CONTEXT, "Command requires a selection")

    @staticmethod
    def _deny(spec: CommandSpec, reason: DenialReason, detail: str) -> None:
        """Raise a structured denial."""
        raise CommandDeniedError(CommandDenial(reason=reason, command_id=spec.id, detail=detail))

    def allow(
        self,
        spec: CommandSpec,
        context: CommandContext | None = None,
        *,
        actor_level: PermissionLevel = PermissionLevel.READ,
    ) -> bool:
        """Return whether a command is allowed without raising."""
        try:
            self.check(spec, context, actor_level=actor_level)
        except CommandDeniedError:
            return False
        return True

    def filter(
        self,
        specs: Iterable[CommandSpec],
        context: CommandContext | None = None,
        *,
        actor_level: PermissionLevel = PermissionLevel.READ,
    ) -> tuple[CommandSpec, ...]:
        """Filter commands to those allowed for the actor."""
        return tuple(spec for spec in specs if self.allow(spec, context, actor_level=actor_level))

    def denial_for(
        self,
        spec: CommandSpec,
        context: CommandContext | None = None,
        *,
        actor_level: PermissionLevel = PermissionLevel.READ,
    ) -> CommandDenial | None:
        """Return the first denial reason, if any."""
        try:
            self.check(spec, context, actor_level=actor_level)
        except CommandDeniedError as error:
            return error.denial
        return None
