"""Value objects for the command grammar and completion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandKind(str, Enum):
    """Categories used to group palette commands."""

    SEARCH = "search"
    NAVIGATION = "navigation"
    SAVED = "saved"
    ACTION = "action"
    FILTER = "filter"
    HELP = "help"


@dataclass(frozen=True, slots=True)
class ArgumentSpec:
    """The declaration of one command argument."""

    name: str
    required: bool = False
    repeatable: bool = False
    choices: tuple[str, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "repeatable": self.repeatable,
            "choices": list(self.choices),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """A command name, aliases, and its argument grammar."""

    name: str
    kind: CommandKind = CommandKind.ACTION
    description: str = ""
    usage: str = ""
    aliases: tuple[str, ...] = ()
    arguments: tuple[ArgumentSpec, ...] = ()
    examples: tuple[str, ...] = ()
    min_args: int = 0
    max_args: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "description": self.description,
            "usage": self.usage or f"/{self.name}",
            "aliases": list(self.aliases),
            "arguments": [item.as_dict() for item in self.arguments],
            "examples": list(self.examples),
            "min_args": self.min_args,
            "max_args": self.max_args,
        }


@dataclass(frozen=True, slots=True)
class LexToken:
    """One token produced by the command lexer."""

    text: str
    start: int
    end: int
    kind: str = "word"
    quoted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "quoted": self.quoted,
        }


@dataclass(frozen=True, slots=True)
class ParseIssue:
    """A machine-readable grammar or validation issue."""

    code: str
    message: str
    position: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "position": self.position}


@dataclass(frozen=True, slots=True)
class CommandArgument:
    """A parsed positional or named command argument."""

    name: str
    value: str
    position: int
    quoted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "position": self.position,
            "quoted": self.quoted,
        }


@dataclass(frozen=True, slots=True)
class CommandNode:
    """A parsed command invocation."""

    name: str
    arguments: tuple[CommandArgument, ...] = ()
    raw: str = ""
    leading: str = "/"
    options: dict[str, str] = field(default_factory=dict)

    @property
    def positional(self) -> tuple[CommandArgument, ...]:
        return tuple(item for item in self.arguments if item.name.isdigit())

    @property
    def text(self) -> str:
        return " ".join(item.value for item in self.positional)

    def option(self, name: str, default: str = "") -> str:
        return self.options.get(name.removeprefix("--"), default)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": [item.as_dict() for item in self.arguments],
            "options": dict(self.options),
            "raw": self.raw,
            "leading": self.leading,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """The result of parsing one command line."""

    raw: str
    node: CommandNode | None = None
    issues: tuple[ParseIssue, ...] = ()
    tokens: tuple[LexToken, ...] = ()

    @property
    def ok(self) -> bool:
        return self.node is not None and not any(
            issue.code != "unknown-command" for issue in self.issues
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "ok": self.ok,
            "node": self.node.as_dict() if self.node is not None else None,
            "issues": [issue.as_dict() for issue in self.issues],
            "tokens": [token.as_dict() for token in self.tokens],
        }


@dataclass(frozen=True, slots=True)
class CommandSuggestion:
    """One ranked completion candidate."""

    label: str
    value: str
    kind: str = "command"
    description: str = ""
    score: float = 0.0
    insert_text: str = ""
    start: int = 0
    end: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "kind": self.kind,
            "description": self.description,
            "score": round(self.score, 3),
            "insert_text": self.insert_text,
            "start": self.start,
            "end": self.end,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    """All suggestions for one command-line cursor position."""

    text: str
    cursor: int
    prefix: str
    suggestions: tuple[CommandSuggestion, ...]
    context: str = "command"

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "cursor": self.cursor,
            "prefix": self.prefix,
            "context": self.context,
            "suggestions": [item.as_dict() for item in self.suggestions],
        }


@dataclass(frozen=True, slots=True)
class CommandPlan:
    """A side-effect-free execution plan for a parsed command."""

    name: str
    action: str
    query: str = ""
    filters: tuple[str, ...] = ()
    target: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "action": self.action,
            "query": self.query,
            "filters": list(self.filters),
            "target": self.target,
            "message": self.message,
            "metadata": dict(self.metadata),
        }
