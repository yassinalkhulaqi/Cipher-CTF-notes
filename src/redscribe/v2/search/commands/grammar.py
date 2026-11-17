"""Lexer and parser for slash-command syntax."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from redscribe.v2.search.commands.models import (
    ArgumentSpec,
    CommandArgument,
    CommandNode,
    CommandSpec,
    LexToken,
    ParsedCommand,
    ParseIssue,
)

_WORD_RE = re.compile(r"[^\s\"'|>:]+", re.UNICODE)
_OPTION_RE = re.compile(r"^--(?P<name>[A-Za-z][A-Za-z0-9_-]*)(?:=(?P<value>.*))?$")


def lex_command(text: str) -> tuple[LexToken, ...]:
    """Tokenize a command line, preserving quote and operator information."""
    tokens: list[LexToken] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        start = index
        if character in "|:>":
            tokens.append(LexToken(character, start, index + 1, kind="operator"))
            index += 1
            continue
        if character == '"':
            index += 1
            buffer: list[str] = []
            while index < length:
                current = text[index]
                if current == "\\" and index + 1 < length:
                    buffer.append(text[index + 1])
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                buffer.append(current)
                index += 1
            tokens.append(LexToken("".join(buffer), start, index, kind="word", quoted=True))
            continue
        match = _WORD_RE.match(text, index)
        if match is None:
            index += 1
            continue
        raw = match.group(0)
        if raw.startswith("--"):
            kind = "option"
        elif ":" in raw:
            kind = "field"
        else:
            kind = "word"
        tokens.append(LexToken(raw, start, match.end(), kind=kind))
        index = match.end()
    return tuple(tokens)


def _parse_options(tokens: Sequence[LexToken]) -> tuple[dict[str, str], list[LexToken]]:
    options: dict[str, str] = {}
    remaining: list[LexToken] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        match = _OPTION_RE.match(token.text)
        if match is not None:
            name = match.group("name")
            value = match.group("value")
            if value is None and index + 1 < len(tokens) and tokens[index + 1].kind != "option":
                index += 1
                value = tokens[index].text
            options[name] = value or "true"
            index += 1
            continue
        remaining.append(token)
        index += 1
    return options, remaining


def _argument_name(token: LexToken, position: int) -> tuple[str, str]:
    if token.kind == "field" and ":" in token.text:
        name, value = token.text.split(":", 1)
        if name and value:
            return name.casefold(), value
    return str(position), token.text


def parse_command(
    text: str,
    *,
    spec: CommandSpec | None = None,
    known_names: Iterable[str] = (),
) -> ParsedCommand:
    """Parse one command line into a node and validation issues."""
    raw = text or ""
    stripped = raw.strip()
    tokens = lex_command(stripped)
    issues: list[ParseIssue] = []
    leading = "/"
    if stripped.startswith("/"):
        leading = "/"
    elif stripped.startswith(":"):
        leading = ":"
    elif stripped:
        issues.append(ParseIssue("missing-prefix", "Commands should start with '/'", 0))

    if not tokens:
        issues.append(ParseIssue("empty-command", "Command is empty", 0))
        return ParsedCommand(raw=raw, issues=tuple(issues), tokens=tokens)

    head = tokens[0]
    name = head.text.removeprefix("/").removeprefix(":").casefold()
    if ":" in name:
        name, inline = name.split(":", 1)
        tokens = (LexToken(inline, head.end, head.end), *tokens[1:])
    options, remaining = _parse_options(tokens[1:])
    arguments: list[CommandArgument] = []
    position = 0
    for token in remaining:
        if token.kind == "operator":
            continue
        arg_name, value = _argument_name(token, position)
        if arg_name.isdigit():
            position += 1
        arguments.append(
            CommandArgument(
                name=arg_name,
                value=value,
                position=token.start,
                quoted=token.quoted,
            )
        )

    if spec is None and known_names:
        known = {value.casefold() for value in known_names}
        if name not in known:
            issues.append(ParseIssue("unknown-command", f"Unknown command: {name}", head.start))
    if spec is not None:
        positional = [item for item in arguments if item.name.isdigit()]
        if len(positional) < spec.min_args:
            issues.append(
                ParseIssue(
                    "missing-argument",
                    f"{spec.name} needs at least {spec.min_args} argument(s)",
                    head.end,
                )
            )
        if spec.max_args is not None and len(positional) > spec.max_args:
            issues.append(
                ParseIssue(
                    "too-many-arguments",
                    f"{spec.name} accepts at most {spec.max_args} argument(s)",
                    head.end,
                )
            )
        for declaration in spec.arguments:
            if declaration.required and declaration.name not in {
                item.name for item in arguments
            } | set(options):
                issues.append(
                    ParseIssue(
                        "missing-argument",
                        f"Missing required argument: {declaration.name}",
                        head.end,
                    )
                )

    node = CommandNode(
        name=name,
        arguments=tuple(arguments),
        raw=stripped,
        leading=leading,
        options=options,
    )
    return ParsedCommand(raw=raw, node=node, issues=tuple(issues), tokens=tokens)


def format_command(node: CommandNode) -> str:
    """Serialize a parsed command node back into canonical syntax."""
    pieces = [f"{node.leading}{node.name}"]
    for argument in node.arguments:
        value = argument.value
        if any(character.isspace() for character in value):
            value = f'"{value}"'
        if argument.name.isdigit():
            pieces.append(value)
        else:
            pieces.append(f"{argument.name}:{value}")
    for name, value in sorted(node.options.items()):
        pieces.append(f"--{name}={value}")
    return " ".join(pieces)


def validate_arguments(
    node: CommandNode,
    spec: CommandSpec,
    *,
    declarations: Sequence[ArgumentSpec] | None = None,
) -> tuple[ParseIssue, ...]:
    """Validate argument choices against a command specification."""
    rules = declarations if declarations is not None else spec.arguments
    issues: list[ParseIssue] = []
    by_name = {rule.name: rule for rule in rules}
    for argument in node.arguments:
        rule = by_name.get(argument.name)
        if rule is None or not rule.choices:
            continue
        if argument.value.casefold() not in {value.casefold() for value in rule.choices}:
            issues.append(
                ParseIssue(
                    "invalid-choice",
                    f"{argument.name} must be one of: {', '.join(rule.choices)}",
                    argument.position,
                )
            )
    return tuple(issues)


def command_grammar() -> dict[str, object]:
    """Describe the command grammar for API consumers and help text."""
    return {
        "prefixes": ["/", ":"],
        "tokens": [
            {"kind": "word", "description": "Bare word or quoted phrase"},
            {"kind": "field", "description": "Named argument such as tag:web"},
            {"kind": "option", "description": "Flag such as --limit=20"},
            {"kind": "operator", "description": "Pipe or redirect separator"},
        ],
        "rules": [
            "A command starts with '/' or ':' followed by its name.",
            "Positional arguments are separated by whitespace.",
            "Named arguments use name:value and options use --name=value.",
            "Quoted arguments preserve spaces and support backslash escapes.",
            "Unknown commands are reported with an unknown-command issue.",
        ],
        "examples": ["/search flag --limit=20", "/saved run weekly", "/tag:web status:active"],
    }


def split_pipeline(text: str) -> tuple[str, ...]:
    """Split a command pipeline on unquoted pipe characters."""
    parts: list[str] = []
    buffer: list[str] = []
    quoted = False
    escaped = False
    for character in text:
        if escaped:
            buffer.append(character)
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            buffer.append(character)
            continue
        if character == "|" and not quoted:
            parts.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(character)
    parts.append("".join(buffer).strip())
    return tuple(part for part in parts if part)


def argument_map(node: CommandNode) -> dict[str, str]:
    """Return positional arguments keyed by one-based ordinal."""
    return {str(index + 1): item.value for index, item in enumerate(node.positional)}


def command_context(text: str, cursor: int) -> str:
    """Return whether a cursor is on a command, argument, or option."""
    if cursor < 0 or cursor > len(text):
        return "command"
    prefix = text[:cursor]
    tokens = lex_command(prefix)
    if not tokens:
        return "command"
    last = tokens[-1]
    if last.kind == "option":
        return "option"
    if len(tokens) == 1 and not prefix[last.end :].strip():
        return "command"
    return "argument"
