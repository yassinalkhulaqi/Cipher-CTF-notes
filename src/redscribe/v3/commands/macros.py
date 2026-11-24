"""Macro recorder that stores command sequences as data, never shell text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.commands.types import CommandInvocation
from redscribe.v3.entities.ids import new_value
from redscribe.v3.entities.types import EntityKind

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
MAX_MACRO_STEPS = 64


class MacroError(ValueError):
    """Raised for invalid or unsafe macro data."""


@dataclass(frozen=True, slots=True)
class MacroStep:
    """One recorded command invocation as plain data."""

    command_id: str
    arguments: dict[str, str] = field(default_factory=dict)
    context_mode: str = "inherit"
    note: str = ""

    def __post_init__(self) -> None:
        if not self.command_id or len(self.command_id) > 120:
            raise MacroError("Macro step needs a command id")
        if self.context_mode not in ("inherit", "explicit", "pane"):
            raise MacroError(f"Unknown context mode: {self.context_mode}")
        if any(not isinstance(value, str) for value in self.arguments.values()):
            raise MacroError("Macro arguments must be strings")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "command_id": self.command_id,
            "arguments": dict(self.arguments),
            "context_mode": self.context_mode,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class Macro:
    """A named, replayable sequence of command invocations."""

    id: str
    name: str
    steps: tuple[MacroStep, ...]
    description: str = ""
    tags: tuple[str, ...] = ()
    created_at: float = 0.0
    author: str = "local"
    version: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip() or len(self.name) > 120:
            raise MacroError("Macro name must be 1-120 characters")
        if not self.steps:
            raise MacroError("A macro needs at least one step")
        if len(self.steps) > MAX_MACRO_STEPS:
            raise MacroError(f"A macro supports at most {MAX_MACRO_STEPS} steps")
        if self.version < 1:
            raise MacroError("Macro version must be positive")

    @property
    def command_ids(self) -> tuple[str, ...]:
        """Command ids in playback order."""
        return tuple(step.command_id for step in self.steps)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "name": self.name,
            "steps": [step.as_dict() for step in self.steps],
            "description": self.description,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "author": self.author,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Macro:
        """Rebuild a macro from persisted data with full validation."""
        raw_steps = payload.get("steps", ())
        if not isinstance(raw_steps, list):
            raise MacroError("Macro steps must be a list")
        steps: list[MacroStep] = []
        for raw in raw_steps:
            if not isinstance(raw, dict):
                raise MacroError("Macro step must be an object")
            arguments = raw.get("arguments", {})
            if not isinstance(arguments, dict):
                raise MacroError("Macro step arguments must be an object")
            steps.append(
                MacroStep(
                    command_id=str(raw.get("command_id", "")),
                    arguments={str(key): str(value) for key, value in arguments.items()},
                    context_mode=str(raw.get("context_mode", "inherit")),
                    note=str(raw.get("note", "")),
                )
            )
        raw_tags = payload.get("tags", ())
        if not isinstance(raw_tags, (list, tuple)):
            raise MacroError("Macro tags must be a list")
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            steps=tuple(steps),
            description=str(payload.get("description", "")),
            tags=tuple(str(tag) for tag in raw_tags),
            created_at=float(payload.get("created_at", 0.0)),
            author=str(payload.get("author", "local")),
            version=int(payload.get("version", 1)),
        )


@dataclass(slots=True)
class MacroRecorder:
    """Captures structured invocations into a macro."""

    clock: Clock = field(default_factory=SystemClock)
    _name: str = ""
    _description: str = ""
    _author: str = "local"
    _started_at: float = 0.0
    _steps: list[MacroStep] = field(default_factory=list)

    @property
    def is_recording(self) -> bool:
        """Whether a recording is in progress."""
        return bool(self._name)

    @property
    def size(self) -> int:
        """Number of captured steps."""
        return len(self._steps)

    def start(self, name: str, *, description: str = "", author: str = "local") -> None:
        """Begin a new recording session."""
        if self.is_recording:
            raise MacroError("A macro recording is already in progress")
        if not name.strip():
            raise MacroError("Macro name cannot be blank")
        self._name = name.strip()
        self._description = description
        self._author = author
        self._started_at = self.clock.now_timestamp()
        self._steps = []

    def capture(self, invocation: CommandInvocation, *, note: str = "") -> MacroStep:
        """Capture one invocation as data."""
        if not self.is_recording:
            raise MacroError("No macro recording in progress")
        if len(self._steps) >= MAX_MACRO_STEPS:
            raise MacroError("Macro step limit reached")
        step = MacroStep(
            command_id=invocation.command_id,
            arguments=dict(invocation.arguments),
            note=note,
        )
        self._steps.append(step)
        return step

    def stop(self) -> Macro:
        """Finish the recording and return an immutable macro."""
        if not self.is_recording:
            raise MacroError("No macro recording in progress")
        if not self._steps:
            raise MacroError("Cannot stop a recording with no steps")
        macro = Macro(
            id=new_value(EntityKind.SNIPPET, prefix="macro"),
            name=self._name,
            steps=tuple(self._steps),
            description=self._description,
            created_at=self._started_at,
            author=self._author,
        )
        self.cancel()
        return macro

    def cancel(self) -> None:
        """Discard the in-progress recording."""
        self._name = ""
        self._description = ""
        self._author = "local"
        self._started_at = 0.0
        self._steps = []


@dataclass(slots=True)
class MacroLibrary:
    """In-memory macro store with snapshot support."""

    _macros: dict[str, Macro] = field(default_factory=dict)

    def add(self, macro: Macro) -> Macro:
        """Store a macro by id."""
        if macro.id in self._macros:
            raise MacroError(f"Macro already exists: {macro.id}")
        self._macros[macro.id] = macro
        return macro

    def get(self, macro_id: str) -> Macro:
        """Return a macro or raise."""
        macro = self._macros.get(macro_id)
        if macro is None:
            raise MacroError(f"Unknown macro: {macro_id}")
        return macro

    def find_by_name(self, name: str) -> Macro | None:
        """Find a macro by case-insensitive name."""
        needle = name.strip().casefold()
        return next(
            (macro for macro in self._macros.values() if macro.name.casefold() == needle),
            None,
        )

    def remove(self, macro_id: str) -> bool:
        """Remove a macro, returning whether it existed."""
        return self._macros.pop(macro_id, None) is not None

    def all(self) -> tuple[Macro, ...]:
        """Return macros in name order."""
        return tuple(
            sorted(self._macros.values(), key=lambda macro: (macro.name.casefold(), macro.id))
        )

    def by_tag(self, tag: str) -> tuple[Macro, ...]:
        """Return macros carrying a tag."""
        needle = tag.strip().casefold()
        return tuple(macro for macro in self.all() if needle in {t.casefold() for t in macro.tags})

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable macro library snapshot."""
        return {"macros": [macro.as_dict() for macro in self.all()]}

    def load(self, snapshot: dict[str, Any]) -> None:
        """Restore macros from a snapshot."""
        raw = snapshot.get("macros", ())
        if not isinstance(raw, list):
            raise MacroError("Snapshot macros must be a list")
        restored: dict[str, Macro] = {}
        for payload in raw:
            if not isinstance(payload, dict):
                raise MacroError("Snapshot macro must be an object")
            macro = Macro.from_dict(payload)
            restored[macro.id] = macro
        self._macros = restored

    def size(self) -> int:
        """Return the number of stored macros."""
        return len(self._macros)


def expand_macro(macro: Macro, values: dict[str, str]) -> tuple[CommandInvocation, ...]:
    """Expand placeholder arguments into concrete data-only invocations."""
    invocations: list[CommandInvocation] = []
    for step in macro.steps:
        arguments: dict[str, str] = {}
        for name, template in step.arguments.items():
            required = PLACEHOLDER_PATTERN.findall(template)
            missing = sorted({key for key in required if key not in values})
            if missing:
                raise MacroError(
                    f"Macro '{macro.name}' step '{step.command_id}' needs: {', '.join(missing)}"
                )
            arguments[name] = PLACEHOLDER_PATTERN.sub(
                lambda match: values[match.group(1)], template
            )
        invocations.append(
            CommandInvocation(command_id=step.command_id, arguments=arguments, source="macro")
        )
    return tuple(invocations)


def macro_steps_as_data(macro: Macro) -> list[dict[str, str]]:
    """Prove a macro contains only serializable command data."""
    return [
        {"command_id": step.command_id, "arguments": str(sorted(step.arguments.items()))}
        for step in macro.steps
    ]
