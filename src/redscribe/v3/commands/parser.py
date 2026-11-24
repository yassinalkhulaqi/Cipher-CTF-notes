"""Tokenizer and binder for the command bar's text input."""

from __future__ import annotations

import re
from dataclasses import dataclass

from redscribe.v3.commands.types import ArgumentSpec, CommandInvocation, CommandSpec

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,2}$")
_SEQUENCE_MARKER = re.compile(r"^\s*(?:(?:\d+[.)]|[-*])\s+)+")


class ParseError(ValueError):
    """Raised when command-bar text cannot be tokenized."""


class BindingError(ValueError):
    """Raised when parsed tokens do not satisfy a command contract."""


@dataclass(frozen=True, slots=True)
class Token:
    """One decoded token with its source position."""

    value: str
    position: int

    @property
    def is_flag(self) -> bool:
        """Whether the token is a long-form flag."""
        return self.value.startswith("--")


@dataclass(frozen=True, slots=True)
class ParsedInput:
    """Unbound command text split into a command id and arguments."""

    command_id: str
    named: dict[str, str]
    positional: tuple[str, ...]
    raw: str = ""

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation."""
        return {
            "command_id": self.command_id,
            "named": dict(self.named),
            "positional": list(self.positional),
            "raw": self.raw,
        }


def tokenize(text: str) -> tuple[Token, ...]:
    """Split command text into tokens, honoring quotes and escapes."""
    tokens: list[Token] = []
    buffer: list[str] = []
    start = 0
    index = 0
    quoted = False
    while index < len(text):
        char = text[index]
        if char in ('"', "'"):
            quoted = not quoted
            index += 1
            continue
        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if quoted or following in ('"', "'", "\\", " "):
                buffer.append(following)
                index += 2
                continue
        if char.isspace() and not quoted:
            if buffer:
                tokens.append(Token("".join(buffer), start))
                buffer = []
            index += 1
            start = index
            continue
        buffer.append(char)
        index += 1
    if quoted:
        raise ParseError("Unterminated quote in command text")
    if buffer:
        tokens.append(Token("".join(buffer), start))
    return tuple(tokens)


def canonicalize_command_id(raw: str) -> str:
    """Normalize ``/group:action`` forms to ``group.action``."""
    candidate = raw.strip()
    while candidate.startswith(("/", ">")):
        candidate = candidate[1:].strip()
    candidate = candidate.replace(":", ".").replace(" ", ".").casefold()
    candidate = re.sub(r"\.+", ".", candidate).strip(".")
    if not _ID_PATTERN.fullmatch(candidate):
        raise ParseError(f"Invalid command id: {raw}")
    return candidate


def _split_named(token: Token) -> tuple[str, str] | None:
    """Split a ``--name=value`` or ``name=value`` token."""
    value = token.value
    if value.startswith("--"):
        value = value[2:]
    if "=" not in value:
        return None
    name, assigned = value.split("=", 1)
    if not name or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ParseError(f"Invalid argument name at position {token.position}")
    return name, assigned


def parse_command(text: str) -> ParsedInput:
    """Parse one line of command-bar text without validating against a spec."""
    tokens = tokenize(text)
    if not tokens:
        raise ParseError("Command text cannot be empty")
    command_id = canonicalize_command_id(tokens[0].value)
    named: dict[str, str] = {}
    positional: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        pair = _split_named(token)
        if pair is not None:
            name, value = pair
            if name in named:
                raise ParseError(f"Duplicate argument '{name}'")
            named[name] = value
            index += 1
            continue
        if token.is_flag:
            name = token.value[2:]
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                raise ParseError(f"Invalid flag at position {token.position}")
            if name in named:
                raise ParseError(f"Duplicate argument '{name}'")
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            if following is None or following.is_flag:
                named[name] = "true"
                index += 1
                continue
            named[name] = following.value
            index += 2
            continue
        positional.append(token.value)
        index += 1
    return ParsedInput(command_id=command_id, named=named, positional=tuple(positional), raw=text)


def _coerce(value: str, spec: ArgumentSpec) -> str:
    """Normalize common textual boolean forms."""
    if spec.arg_type.value == "boolean":
        lowered = value.casefold()
        mapping = {"yes": "true", "1": "true", "no": "false", "0": "false"}
        value = mapping.get(lowered, lowered)
    return spec.validate_value(value)


def bind_arguments(parsed: ParsedInput, spec: CommandSpec) -> CommandInvocation:
    """Bind parsed tokens to a command spec and return an invocation."""
    if parsed.command_id != spec.id and parsed.command_id not in spec.aliases:
        raise BindingError(f"Command '{parsed.command_id}' does not match '{spec.id}'")
    known = set(spec.argument_names)
    unknown = sorted(set(parsed.named) - known)
    if unknown:
        raise BindingError(f"Unknown argument(s): {', '.join(unknown)}")
    values: dict[str, str] = {}
    for name, value in parsed.named.items():
        argument = spec.argument(name)
        if argument is not None:
            values[name] = _coerce(value, argument)
    remaining = [name for name in spec.argument_names if name not in values]
    if len(parsed.positional) > len(remaining):
        raise BindingError(
            f"Command '{spec.id}' accepts at most {len(remaining)} positional values"
        )
    for name, value in zip(remaining, parsed.positional, strict=False):
        argument = spec.argument(name)
        if argument is not None:
            values[name] = _coerce(value, argument)
    missing = [name for name in spec.required_argument_names if name not in values]
    if missing:
        raise BindingError(f"Missing required argument(s): {', '.join(missing)}")
    for argument in spec.arguments:
        if argument.name not in values and argument.default:
            values[argument.name] = argument.default
    return CommandInvocation(command_id=spec.id, arguments=values, source="palette")


def _quote(value: str) -> str:
    """Quote a value only when the tokenizer would otherwise split it."""
    if not value:
        return '""'
    if any(char.isspace() for char in value) or any(char in value for char in ('"', "'", "\\")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def render_command(invocation: CommandInvocation, spec: CommandSpec | None = None) -> str:
    """Render an invocation back into canonical command-bar text."""
    ordered = list(invocation.arguments.items())
    if spec is not None:
        order = {name: index for index, name in enumerate(spec.argument_names)}
        ordered.sort(key=lambda item: order.get(item[0], len(order)))
    parts = [f"/{invocation.command_id}"]
    parts.extend(f"--{name} {_quote(value)}" for name, value in ordered)
    return " ".join(parts)


def parse_sequence(text: str) -> tuple[ParsedInput, ...]:
    """Parse a numbered or bulleted list of commands into data steps."""
    parsed: list[ParsedInput] = []
    for line in text.splitlines():
        candidate = _SEQUENCE_MARKER.sub("", line).strip()
        if not candidate:
            continue
        parsed.append(parse_command(candidate))
    return tuple(parsed)
