"""Data-only contracts for the V3 command center.

Commands are declarative records: a command says *what effect* it requests,
never how to execute a shell command. This keeps macros, history, and API
payloads safe to persist and replay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.capabilities import CAP_COMMANDS
from redscribe.v3.entities.types import EntityKind, EntityRef

COMMAND_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
ARGUMENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class CommandGroup(str, Enum):
    """Top-level grouping used by the palette and API."""

    NAVIGATION = "navigation"
    CREATE = "create"
    INSPECT = "inspect"
    EDIT = "edit"
    VIEW = "view"
    SESSION = "session"
    AUTOMATION = "automation"
    SYSTEM = "system"

    @classmethod
    def parse(cls, value: str) -> CommandGroup:
        """Parse a group name with a stable error message."""
        normalized = value.strip().casefold()
        for group in cls:
            if group.value == normalized:
                return group
        raise ValueError(f"Unknown command group: {value}")

    @property
    def label(self) -> str:
        """Human-readable group label."""
        return self.value.replace("_", " ").title()

    @property
    def order(self) -> int:
        """Stable display order."""
        return tuple(group.value for group in CommandGroup).index(self.value) * 10


class CommandEffect(str, Enum):
    """Declarative effect requested by a command."""

    NAVIGATE = "navigate"
    OPEN_PANE = "open_pane"
    MUTATE = "mutate"
    INSPECT = "inspect"
    DIALOG = "dialog"
    FOCUS = "focus"
    MACRO = "macro"


class ArgumentType(str, Enum):
    """Validation contract for a command argument."""

    TEXT = "text"
    CHOICE = "choice"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENTITY_REF = "entity_ref"


class CommandStatus(str, Enum):
    """Visibility and availability of a command."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    HIDDEN = "hidden"


class PermissionLevel(int, Enum):
    """Local permission level required to run a command."""

    READ = 0
    WRITE = 1
    ADMIN = 2

    def satisfies(self, required: PermissionLevel) -> bool:
        """Return whether this level meets or exceeds another."""
        return int(self) >= int(required)


class DenialReason(str, Enum):
    """Why a command could not run."""

    UNKNOWN_COMMAND = "unknown_command"
    DISABLED_COMMAND = "disabled_command"
    DISABLED_CAPABILITY = "disabled_capability"
    INSUFFICIENT_PERMISSION = "insufficient_permission"
    MISSING_CONTEXT = "missing_context"
    INVALID_ARGUMENT = "invalid_argument"


@dataclass(frozen=True, slots=True)
class ArgumentSpec:
    """One validated command argument."""

    name: str
    arg_type: ArgumentType = ArgumentType.TEXT
    required: bool = False
    default: str = ""
    choices: tuple[str, ...] = ()
    help: str = ""
    max_length: int = 240

    def __post_init__(self) -> None:
        if not ARGUMENT_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"Invalid argument name: {self.name}")
        if self.arg_type is ArgumentType.CHOICE and not self.choices:
            raise ValueError(f"Choice argument '{self.name}' needs choices")
        if self.max_length < 1:
            raise ValueError("Argument max_length must be positive")
        if len(self.default) > self.max_length:
            raise ValueError(f"Default for '{self.name}' exceeds max_length")

    def validate_value(self, value: str) -> str:
        """Validate and normalize one supplied value."""
        if len(value) > self.max_length:
            raise ValueError(f"Argument '{self.name}' exceeds {self.max_length} characters")
        if self.arg_type is ArgumentType.CHOICE and value not in self.choices:
            raise ValueError(f"Argument '{self.name}' must be one of: {', '.join(self.choices)}")
        if self.arg_type is ArgumentType.NUMBER:
            try:
                float(value)
            except ValueError as error:
                raise ValueError(f"Argument '{self.name}' must be numeric") from error
        if self.arg_type is ArgumentType.BOOLEAN and value.casefold() not in {
            "true",
            "false",
            "yes",
            "no",
            "1",
            "0",
        }:
            raise ValueError(f"Argument '{self.name}' must be a boolean")
        if self.arg_type is ArgumentType.ENTITY_REF and ":" not in value:
            raise ValueError(f"Argument '{self.name}' must be a kind:value reference")
        return value

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "arg_type": self.arg_type.value,
            "required": self.required,
            "default": self.default,
            "choices": list(self.choices),
            "help": self.help,
            "max_length": self.max_length,
        }


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """A declarative command definition registered by any feature branch."""

    id: str
    title: str
    group: CommandGroup
    description: str = ""
    keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    arguments: tuple[ArgumentSpec, ...] = ()
    capability: str = CAP_COMMANDS
    status: CommandStatus = CommandStatus.ENABLED
    effect: CommandEffect = CommandEffect.NAVIGATE
    order: int = 100
    target_kind: EntityKind | None = None
    requires_selection: bool = False
    min_permission: PermissionLevel = PermissionLevel.READ

    def __post_init__(self) -> None:
        if not COMMAND_ID_PATTERN.fullmatch(self.id):
            raise ValueError(f"Invalid command id: {self.id}")
        if not self.title.strip():
            raise ValueError("Command title cannot be blank")
        if len(self.keywords) > 32 or len(self.aliases) > 16:
            raise ValueError("Command keyword and alias limits exceeded")
        names = tuple(argument.name for argument in self.arguments)
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate argument names in command '{self.id}'")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError(f"Duplicate aliases in command '{self.id}'")
        seen_optional = False
        for argument in self.arguments:
            if argument.required and seen_optional:
                raise ValueError(f"Required argument after optional in '{self.id}'")
            if not argument.required:
                seen_optional = True

    @property
    def argument_names(self) -> tuple[str, ...]:
        """Names of all declared arguments."""
        return tuple(argument.name for argument in self.arguments)

    @property
    def required_argument_names(self) -> tuple[str, ...]:
        """Names of arguments that must be supplied."""
        return tuple(argument.name for argument in self.arguments if argument.required)

    def argument(self, name: str) -> ArgumentSpec | None:
        """Look up an argument specification by name."""
        return next((item for item in self.arguments if item.name == name), None)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "title": self.title,
            "group": self.group.value,
            "description": self.description,
            "keywords": list(self.keywords),
            "aliases": list(self.aliases),
            "arguments": [argument.as_dict() for argument in self.arguments],
            "capability": self.capability,
            "status": self.status.value,
            "effect": self.effect.value,
            "order": self.order,
            "target_kind": self.target_kind.value if self.target_kind else "",
            "requires_selection": self.requires_selection,
            "min_permission": self.min_permission.value,
        }


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """A structured, replayable request to run one command."""

    command_id: str
    arguments: dict[str, str] = field(default_factory=dict)
    source: str = "palette"
    context_ref: str = ""

    def __post_init__(self) -> None:
        if not self.command_id or len(self.command_id) > 120:
            raise ValueError("Command id must be 1-120 characters")
        if any(not isinstance(key, str) or not key for key in self.arguments):
            raise ValueError("Argument keys must be non-empty strings")
        if any(not isinstance(value, str) for value in self.arguments.values()):
            raise ValueError("Argument values must be strings")

    @property
    def signature(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        """Stable identity used for usage tracking and deduplication."""
        return (self.command_id, tuple(sorted(self.arguments.items())))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "command_id": self.command_id,
            "arguments": dict(self.arguments),
            "source": self.source,
            "context_ref": self.context_ref,
        }


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of a structured command execution."""

    invocation: CommandInvocation
    accepted: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    event_kind: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "invocation": self.invocation.as_dict(),
            "accepted": self.accepted,
            "message": self.message,
            "data": dict(self.data),
            "event_kind": self.event_kind,
        }


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Everything a command needs to know about the active pane."""

    pane_id: str
    workspace_id: str = "main"
    entity: EntityRef | None = None
    selection: tuple[EntityRef, ...] = ()
    tags: tuple[str, ...] = ()
    focus_active: bool = False
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.pane_id or len(self.pane_id) > 80:
            raise ValueError("Pane id must be 1-80 characters")
        if len(self.selection) > 64:
            raise ValueError("A context supports at most 64 selected entities")

    @property
    def entity_ref(self) -> str:
        """Canonical reference of the active entity, if any."""
        return str(self.entity) if self.entity is not None else ""

    @property
    def selection_refs(self) -> tuple[str, ...]:
        """Canonical references of selected entities."""
        return tuple(str(item) for item in self.selection)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "pane_id": self.pane_id,
            "workspace_id": self.workspace_id,
            "entity": self.entity.as_dict() if self.entity is not None else None,
            "selection": [item.as_dict() for item in self.selection],
            "tags": list(self.tags),
            "focus_active": self.focus_active,
            "capabilities": sorted(self.capabilities),
        }


@dataclass(frozen=True, slots=True)
class CommandHit:
    """One ranked command result."""

    command: CommandSpec
    score: float
    signals: tuple[str, ...] = ()
    matched_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "command": self.command.as_dict(),
            "score": round(self.score, 4),
            "signals": list(self.signals),
            "matched_text": self.matched_text,
        }


@dataclass(frozen=True, slots=True)
class CommandGroupResult:
    """Ranked results collected under one group heading."""

    group: CommandGroup
    hits: tuple[CommandHit, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "group": self.group.value,
            "label": self.group.label,
            "hits": [hit.as_dict() for hit in self.hits],
        }


@dataclass(frozen=True, slots=True)
class CommandDenial:
    """A structured denial with no executable payload."""

    reason: DenialReason
    command_id: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation."""
        return {
            "reason": self.reason.value,
            "command_id": self.command_id,
            "detail": self.detail,
        }
