"""Deterministic text interpolation for playbooks, steps, and templates.

Placeholders use ``{{ name | filter(args) }}`` syntax. Rendering is pure text
transformation: no shell, network, or filesystem operation is ever performed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from urllib.parse import quote as url_quote

from redscribe.v2.playbooks.errors import InterpolationError
from redscribe.v2.playbooks.types import Issue, Value, Values

_PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_FILTERS = frozenset(
    {
        "upper",
        "lower",
        "title",
        "capitalize",
        "trim",
        "slug",
        "quote",
        "shell",
        "json",
        "base64",
        "urlencode",
        "mask",
        "length",
        "default",
        "coalesce",
        "prefix",
        "suffix",
        "replace",
        "join",
        "escape",
        "sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FilterCall:
    """A single filter and its literal arguments."""

    name: str
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpressionToken:
    """A parsed placeholder expression."""

    name: str
    filters: tuple[FilterCall, ...] = ()
    raw: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "filters": [
                {"name": item.name, "arguments": list(item.arguments)} for item in self.filters
            ],
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class RenderResult:
    """The output and diagnostics of one render operation."""

    text: str
    used: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    issues: tuple[Issue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.is_error for issue in self.issues)

    def as_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "used": list(self.used),
            "unresolved": list(self.unresolved),
            "issues": [issue.as_dict() for issue in self.issues],
        }


def parse_expression(source: str) -> ExpressionToken:
    """Parse the inside of one ``{{ ... }}`` placeholder."""
    parts = _split_filters(source.strip())
    if not parts:
        raise InterpolationError("Placeholder expression is empty")
    head = parts[0].strip()
    if not head:
        raise InterpolationError("Placeholder has no variable name")
    name, inline_argument = _split_inline_argument(head)
    if not _NAME_RE.match(name) and not _is_literal(name):
        raise InterpolationError(f"Invalid placeholder name: {name}")
    filters: list[FilterCall] = []
    if inline_argument is not None:
        filters.append(FilterCall("default", (inline_argument,)))
    for part in parts[1:]:
        filters.append(_parse_filter(part))
    return ExpressionToken(name=name, filters=tuple(filters), raw=source.strip())


def parse_tokens(source: str) -> tuple[str | ExpressionToken, ...]:
    """Split a template into literal text and parsed placeholder tokens."""
    result: list[str | ExpressionToken] = []
    cursor = 0
    for match in _PLACEHOLDER_RE.finditer(source):
        if match.start() > cursor:
            result.append(source[cursor : match.start()])
        result.append(parse_expression(match.group(1)))
        cursor = match.end()
    if cursor < len(source):
        result.append(source[cursor:])
    return tuple(result)


def variables_in(source: str) -> tuple[str, ...]:
    """Return unique variable names referenced by a template."""
    names: list[str] = []
    for token in parse_tokens(source):
        if (
            isinstance(token, ExpressionToken)
            and not _is_literal(token.name)
            and _NAME_RE.match(token.name)
            and token.name not in names
        ):
            names.append(token.name)
    return tuple(names)


def validate_source(source: str) -> tuple[Issue, ...]:
    """Report malformed placeholders and unknown filters."""
    issues: list[Issue] = []
    for token in parse_tokens(source):
        if isinstance(token, ExpressionToken):
            for call in token.filters:
                if call.name not in _FILTERS:
                    issues.append(
                        Issue(
                            code="unknown-filter",
                            message=f"Unknown interpolation filter: {call.name}",
                            severity="warning",
                        )
                    )
    if source.count("{{") != source.count("}}"):
        issues.append(Issue("unbalanced-placeholder", "Template has unbalanced braces."))
    return tuple(issues)


def render(
    source: str,
    values: Values | None = None,
    *,
    undefined: str = "",
    mask_secrets: bool = False,
) -> RenderResult:
    """Render a template with resolved values, tolerating missing names."""
    context = dict(values or {})
    used: list[str] = []
    unresolved: list[str] = []
    issues: list[Issue] = []
    pieces: list[str] = []
    for token in parse_tokens(source):
        if isinstance(token, str):
            pieces.append(token)
            continue
        raw_value: Value
        if _is_literal(token.name):
            raw_value = _literal(token.name)
        elif token.name in context:
            raw_value = context[token.name]
            if token.name not in used:
                used.append(token.name)
        else:
            raw_value = undefined
            unresolved.append(token.name)
            issues.append(
                Issue(
                    code="unresolved-variable",
                    message=f"Unresolved variable: {token.name}",
                    severity="warning",
                )
            )
        current: Value = raw_value
        for call in token.filters:
            arguments = tuple(_resolve_argument(arg, context) for arg in call.arguments)
            try:
                current = apply_filter(call.name, current, arguments)
            except InterpolationError as exc:
                issues.append(Issue("filter-error", str(exc), severity="warning"))
        if mask_secrets and any(call.name == "mask" for call in token.filters):
            current = "***"
        pieces.append(_as_text(current))
    return RenderResult(
        text="".join(pieces),
        used=tuple(used),
        unresolved=tuple(unresolved),
        issues=tuple(issues),
    )


def render_strict(
    source: str,
    values: Values | None = None,
    *,
    mask_secrets: bool = False,
) -> RenderResult:
    """Render a template, raising when a variable is unresolved."""
    result = render(source, values, mask_secrets=mask_secrets)
    if result.unresolved:
        raise InterpolationError(
            f"Unresolved variables: {', '.join(result.unresolved)}",
            details={"keys": list(result.unresolved)},
        )
    return result


def apply_filter(name: str, value: Value, arguments: tuple[str, ...] = ()) -> Value:
    """Apply one whitelisted text filter."""
    text = _as_text(value)
    if name == "upper":
        return text.upper()
    if name == "lower":
        return text.lower()
    if name == "title":
        return text.title()
    if name == "capitalize":
        return text.capitalize()
    if name == "trim":
        return text.strip()
    if name == "slug":
        return _slug(text)
    if name == "quote":
        return json.dumps(text, ensure_ascii=False)
    if name == "shell":
        return shlex.quote(text)
    if name == "json":
        return json.dumps(text, ensure_ascii=False, sort_keys=True)
    if name == "base64":
        return base64.b64encode(text.encode("utf-8")).decode("ascii")
    if name == "urlencode":
        return url_quote(text, safe="")
    if name == "mask":
        return _mask(text)
    if name == "length":
        return len(text)
    if name == "default":
        return text or (arguments[0] if arguments else "")
    if name == "coalesce":
        for candidate in (text, *arguments):
            if candidate:
                return candidate
        return text
    if name == "prefix":
        return f"{arguments[0] if arguments else ''}{text}"
    if name == "suffix":
        return f"{text}{arguments[0] if arguments else ''}"
    if name == "replace":
        if len(arguments) < 2:
            return text
        return text.replace(arguments[0], arguments[1])
    if name == "join":
        if isinstance(value, tuple):
            return (arguments[0] if arguments else ",").join(_as_text(item) for item in value)
        return text
    if name == "escape":
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if name == "sha256":
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    raise InterpolationError(f"Unknown filter: {name}")


def mask_values(values: Values, *, visible: int = 2) -> dict[str, str]:
    """Return a display-safe copy that masks every value."""
    return {key: _mask(_as_text(value), visible=visible) for key, value in values.items()}


def _mask(text: str, *, visible: int = 2) -> str:
    if not text:
        return ""
    if len(text) <= visible:
        return "*" * len(text)
    return f"{text[:visible]}{'*' * min(8, len(text) - visible)}"


def _slug(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return normalized.strip("-")


def _as_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return ",".join(_as_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _is_literal(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'")


def _literal(value: str) -> str:
    return value[1:-1] if _is_literal(value) else value


def _split_filters(source: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    depth = 0
    for char in source:
        if quote is not None:
            buffer.append(char)
            if char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
            buffer.append(char)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "|" and depth == 0:
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)
    parts.append("".join(buffer))
    return parts


def _split_inline_argument(head: str) -> tuple[str, str | None]:
    quote: str | None = None
    for index, char in enumerate(head):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
        elif char in (":", "="):
            return head[:index].strip(), head[index + 1 :].strip().strip("\"'")
    return head.strip(), None


def _parse_filter(part: str) -> FilterCall:
    source = part.strip()
    if not source:
        raise InterpolationError("Empty filter in placeholder")
    match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*(.*)$", source, re.DOTALL)
    if match is None:
        raise InterpolationError(f"Invalid filter: {source}")
    name, remainder = match.group(1), match.group(2).strip()
    if not remainder:
        return FilterCall(name)
    if remainder.startswith("(") and remainder.endswith(")"):
        remainder = remainder[1:-1]
    arguments = tuple(_clean_argument(item) for item in _split_arguments(remainder))
    return FilterCall(name, arguments)


def _split_arguments(source: str) -> list[str]:
    arguments: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    for char in source:
        if quote is not None:
            buffer.append(char)
            if char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
            buffer.append(char)
            continue
        if char == ",":
            arguments.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(char)
    tail = "".join(buffer).strip()
    if tail:
        arguments.append(tail)
    return arguments


def _clean_argument(value: str) -> str:
    value = value.strip()
    if _is_literal(value):
        return value[1:-1]
    if value.casefold() == "true":
        return "true"
    if value.casefold() == "false":
        return "false"
    return value


def _resolve_argument(argument: str, context: Values) -> str:
    if argument in context:
        return _as_text(context[argument])
    return argument
