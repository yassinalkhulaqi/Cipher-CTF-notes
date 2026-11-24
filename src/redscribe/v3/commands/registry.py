"""Additive, data-driven command registry for the V3 command center."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.commands.types import (
    ArgumentSpec,
    ArgumentType,
    CommandEffect,
    CommandGroup,
    CommandSpec,
    CommandStatus,
    PermissionLevel,
)


class DuplicateCommandError(ValueError):
    """Raised when a command id or alias is already registered."""


@dataclass(slots=True)
class CommandRegistry:
    """Registry of declarative commands with stable ordering."""

    _commands: dict[str, CommandSpec] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(self, spec: CommandSpec) -> CommandSpec:
        """Register one command, rejecting conflicting ids and aliases."""
        if spec.id in self._commands:
            raise DuplicateCommandError(f"Command already registered: {spec.id}")
        if spec.id in self._aliases:
            raise DuplicateCommandError(f"Command id conflicts with an alias: {spec.id}")
        for alias in spec.aliases:
            if alias in self._aliases or alias in self._commands:
                raise DuplicateCommandError(f"Alias already registered: {alias}")
        self._commands[spec.id] = spec
        for alias in spec.aliases:
            self._aliases[alias] = spec.id
        return spec

    def register_many(self, specs: tuple[CommandSpec, ...] | list[CommandSpec]) -> int:
        """Register several commands and return how many were added."""
        before = len(self._commands)
        for spec in specs:
            self.register(spec)
        return len(self._commands) - before

    def get(self, command_id: str) -> CommandSpec | None:
        """Look up a command by id or alias."""
        direct = self._commands.get(command_id)
        if direct is not None:
            return direct
        resolved = self._aliases.get(command_id)
        return self._commands.get(resolved) if resolved else None

    def require(self, command_id: str) -> CommandSpec:
        """Look up a command or raise a descriptive error."""
        spec = self.get(command_id)
        if spec is None:
            raise KeyError(f"Unknown command: {command_id}")
        return spec

    def resolve_id(self, value: str) -> str:
        """Resolve an alias to its canonical command id."""
        spec = self.require(value)
        return spec.id

    def all(self) -> tuple[CommandSpec, ...]:
        """Return all commands in stable display order."""
        return tuple(
            sorted(
                self._commands.values(),
                key=lambda spec: (spec.group.order, spec.order, spec.id),
            )
        )

    def by_group(self, group: CommandGroup) -> tuple[CommandSpec, ...]:
        """Return commands belonging to one group."""
        return tuple(spec for spec in self.all() if spec.group is group)

    def groups(self) -> tuple[CommandGroup, ...]:
        """Return groups that contain at least one command."""
        present = {spec.group for spec in self._commands.values()}
        return tuple(sorted(present, key=lambda group: group.order))

    def enabled(self) -> tuple[CommandSpec, ...]:
        """Return commands that are not disabled or hidden."""
        return tuple(
            spec
            for spec in self.all()
            if spec.status not in (CommandStatus.DISABLED, CommandStatus.HIDDEN)
        )

    def validate(self) -> tuple[str, ...]:
        """Return registry integrity problems."""
        problems: list[str] = []
        for spec in self._commands.values():
            if not spec.description:
                problems.append(f"missing description: {spec.id}")
            for keyword in spec.keywords:
                if keyword != keyword.casefold():
                    problems.append(f"non-normalized keyword: {spec.id}")
        return tuple(sorted(problems))

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable registry snapshot."""
        return {
            "commands": [spec.as_dict() for spec in self.all()],
            "aliases": dict(sorted(self._aliases.items())),
        }

    def size(self) -> int:
        """Return the number of registered commands."""
        return len(self._commands)


def _arg(
    name: str,
    *,
    arg_type: ArgumentType = ArgumentType.TEXT,
    required: bool = False,
    default: str = "",
    choices: tuple[str, ...] = (),
    hint: str = "",
) -> ArgumentSpec:
    """Build an argument specification concisely for the default catalog."""
    return ArgumentSpec(
        name=name,
        arg_type=arg_type,
        required=required,
        default=default,
        choices=choices,
        help=hint,
    )


def default_commands() -> tuple[CommandSpec, ...]:
    """Return the built-in command catalog for the command center."""
    return (
        CommandSpec(
            id="navigation.goto",
            title="Go to entity",
            group=CommandGroup.NAVIGATION,
            description="Open any entity by kind:value reference.",
            keywords=("jump", "open", "goto"),
            aliases=("goto", "g"),
            arguments=(
                _arg("ref", arg_type=ArgumentType.ENTITY_REF, required=True, hint="kind:value"),
                _arg("pane", default="active", hint="Target pane id"),
            ),
            effect=CommandEffect.NAVIGATE,
            order=10,
        ),
        CommandSpec(
            id="navigation.open",
            title="Open recent",
            group=CommandGroup.NAVIGATION,
            description="Open the most recently used entity.",
            keywords=("recent", "resume"),
            aliases=("open",),
            arguments=(_arg("ref", arg_type=ArgumentType.ENTITY_REF),),
            effect=CommandEffect.NAVIGATE,
            order=20,
        ),
        CommandSpec(
            id="navigation.back",
            title="Navigate back",
            group=CommandGroup.NAVIGATION,
            description="Step back through the breadcrumb trail.",
            keywords=("previous", "history"),
            aliases=("back",),
            effect=CommandEffect.NAVIGATE,
            order=30,
        ),
        CommandSpec(
            id="navigation.forward",
            title="Navigate forward",
            group=CommandGroup.NAVIGATION,
            description="Step forward through the breadcrumb trail.",
            keywords=("next", "history"),
            aliases=("forward",),
            effect=CommandEffect.NAVIGATE,
            order=40,
        ),
        CommandSpec(
            id="navigation.breadcrumbs",
            title="Show breadcrumbs",
            group=CommandGroup.NAVIGATION,
            description="Reveal the breadcrumb path for the current pane.",
            keywords=("path", "trail"),
            aliases=("crumbs",),
            effect=CommandEffect.NAVIGATE,
            order=50,
        ),
        CommandSpec(
            id="create.note",
            title="New note",
            group=CommandGroup.CREATE,
            description="Create a note in the current workspace.",
            keywords=("add", "document", "capture"),
            aliases=("newnote",),
            arguments=(
                _arg("title", required=True, hint="Note title"),
                _arg("tags", hint="Comma-separated tags"),
            ),
            effect=CommandEffect.MUTATE,
            min_permission=PermissionLevel.WRITE,
            order=10,
        ),
        CommandSpec(
            id="create.finding",
            title="New finding",
            group=CommandGroup.CREATE,
            description="Draft a finding linked to the active target.",
            keywords=("add", "vulnerability", "issue"),
            aliases=("newfinding",),
            arguments=(
                _arg("title", required=True),
                _arg(
                    "severity",
                    arg_type=ArgumentType.CHOICE,
                    default="medium",
                    choices=("info", "low", "medium", "high", "critical"),
                ),
            ),
            effect=CommandEffect.MUTATE,
            min_permission=PermissionLevel.WRITE,
            order=20,
        ),
        CommandSpec(
            id="create.target",
            title="New target",
            group=CommandGroup.CREATE,
            description="Add a target to the active engagement.",
            keywords=("add", "scope", "host"),
            aliases=("newtarget",),
            arguments=(
                _arg("name", required=True),
                _arg("scope", hint="Scope expression"),
            ),
            effect=CommandEffect.MUTATE,
            min_permission=PermissionLevel.WRITE,
            order=30,
        ),
        CommandSpec(
            id="create.folder",
            title="New folder",
            group=CommandGroup.CREATE,
            description="Create a folder in the vault tree.",
            keywords=("add", "directory"),
            aliases=("newfolder",),
            arguments=(
                _arg("name", required=True),
                _arg("parent", hint="Parent folder reference"),
            ),
            effect=CommandEffect.MUTATE,
            min_permission=PermissionLevel.WRITE,
            order=40,
        ),
        CommandSpec(
            id="inspect.entity",
            title="Inspect entity",
            group=CommandGroup.INSPECT,
            description="Show metadata and links for an entity.",
            keywords=("details", "properties", "info"),
            aliases=("inspect",),
            arguments=(_arg("ref", arg_type=ArgumentType.ENTITY_REF, required=True),),
            effect=CommandEffect.INSPECT,
            order=10,
        ),
        CommandSpec(
            id="inspect.evidence",
            title="Verify evidence",
            group=CommandGroup.INSPECT,
            description="Check evidence integrity from the command bar.",
            keywords=("hash", "custody", "verify"),
            aliases=("verify",),
            arguments=(_arg("ref", arg_type=ArgumentType.ENTITY_REF, required=True),),
            effect=CommandEffect.INSPECT,
            order=20,
        ),
        CommandSpec(
            id="view.split",
            title="Split pane",
            group=CommandGroup.VIEW,
            description="Split the active pane into a second workspace pane.",
            keywords=("pane", "layout", "side-by-side"),
            aliases=("split",),
            arguments=(
                _arg(
                    "orientation",
                    arg_type=ArgumentType.CHOICE,
                    default="vertical",
                    choices=("vertical", "horizontal"),
                ),
            ),
            effect=CommandEffect.OPEN_PANE,
            order=10,
        ),
        CommandSpec(
            id="view.close",
            title="Close pane",
            group=CommandGroup.VIEW,
            description="Close a pane and restore focus to its neighbor.",
            keywords=("pane", "layout"),
            aliases=("closepane",),
            arguments=(_arg("pane", required=True),),
            effect=CommandEffect.OPEN_PANE,
            order=20,
        ),
        CommandSpec(
            id="view.focus",
            title="Focus pane",
            group=CommandGroup.VIEW,
            description="Move keyboard focus to a named pane.",
            keywords=("pane", "activate"),
            aliases=("focuspane",),
            arguments=(_arg("pane", required=True),),
            effect=CommandEffect.OPEN_PANE,
            order=30,
        ),
        CommandSpec(
            id="session.start",
            title="Start focus session",
            group=CommandGroup.SESSION,
            description="Begin a distraction-free focus session.",
            keywords=("deep work", "distraction", "zen"),
            aliases=("focus",),
            arguments=(_arg("label", default="Focus"),),
            effect=CommandEffect.FOCUS,
            order=10,
        ),
        CommandSpec(
            id="session.pause",
            title="Pause focus session",
            group=CommandGroup.SESSION,
            description="Pause the active focus session without ending it.",
            keywords=("break", "hold"),
            aliases=("pause",),
            effect=CommandEffect.FOCUS,
            order=20,
        ),
        CommandSpec(
            id="session.resume",
            title="Resume focus session",
            group=CommandGroup.SESSION,
            description="Resume a paused focus session.",
            keywords=("continue",),
            aliases=("resume",),
            effect=CommandEffect.FOCUS,
            order=30,
        ),
        CommandSpec(
            id="session.end",
            title="End focus session",
            group=CommandGroup.SESSION,
            description="End the focus session and restore the previous pane.",
            keywords=("stop", "finish"),
            aliases=("endfocus",),
            effect=CommandEffect.FOCUS,
            order=40,
        ),
        CommandSpec(
            id="automation.record",
            title="Record macro",
            group=CommandGroup.AUTOMATION,
            description="Record the next commands as a replayable data macro.",
            keywords=("macro", "replay", "sequence"),
            aliases=("record",),
            arguments=(_arg("name", required=True),),
            effect=CommandEffect.MACRO,
            min_permission=PermissionLevel.WRITE,
            order=10,
        ),
        CommandSpec(
            id="automation.run",
            title="Run macro",
            group=CommandGroup.AUTOMATION,
            description="Replay a stored command sequence.",
            keywords=("macro", "replay", "sequence"),
            aliases=("runmacro",),
            arguments=(_arg("name", required=True),),
            effect=CommandEffect.MACRO,
            min_permission=PermissionLevel.WRITE,
            order=20,
        ),
        CommandSpec(
            id="system.help",
            title="Keyboard help",
            group=CommandGroup.SYSTEM,
            description="Show shortcuts and command-bar syntax.",
            keywords=("shortcuts", "keys", "docs"),
            aliases=("help",),
            arguments=(_arg("topic", default="commands"),),
            effect=CommandEffect.DIALOG,
            order=10,
        ),
        CommandSpec(
            id="system.settings",
            title="Open settings",
            group=CommandGroup.SYSTEM,
            description="Open a settings section.",
            keywords=("preferences", "config"),
            aliases=("settings",),
            arguments=(_arg("section", default="general"),),
            effect=CommandEffect.DIALOG,
            min_permission=PermissionLevel.WRITE,
            order=20,
        ),
    )


def default_registry() -> CommandRegistry:
    """Build a registry preloaded with the built-in catalog."""
    registry = CommandRegistry()
    registry.register_many(default_commands())
    return registry
