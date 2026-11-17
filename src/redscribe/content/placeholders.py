"""Shared placeholder expansion and target normalization.

Templates and command snippets use the same ``{{name}}`` syntax. Keeping the
resolver in one module guarantees consistent target, domain, URL, and slug
derivation across both content features.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from redscribe.domain.models import PlaceholderToken, ValidationIssue
from redscribe.domain.utils import slugify

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_OPEN = "{{"
_CLOSE = "}}"
_ESCAPED_OPEN = "\\{{"
_PATH_RE = re.compile(r"[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*")
FILTER_NAMES: frozenset[str] = frozenset(
    {"upper", "lower", "trim", "strip", "slug", "title", "default", "prefix", "suffix"}
)


def placeholder_names(text: str) -> list[str]:
    """Return placeholder names in first-use order, without duplicates."""
    names: list[str] = []
    seen: set[str] = set()
    for match in PLACEHOLDER_RE.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def interpolate(text: str, values: Mapping[str, str]) -> str:
    """Replace known placeholders, leaving unknown or blank values intact."""

    def replace(match: re.Match[str]) -> str:
        value = values.get(match.group(1), "").strip()
        return value if value else match.group(0)

    return PLACEHOLDER_RE.sub(replace, text)


def target_values(target: str) -> dict[str, str]:
    """Derive the placeholder context for a host or URL target."""
    cleaned = target.strip()
    if not cleaned:
        return {}
    host = _hostname(cleaned)
    values = {
        "target": cleaned,
        "slug": slugify(cleaned),
    }
    if host:
        values["domain"] = host
    values["url"] = _target_url(cleaned)
    return values


def _hostname(target: str) -> str:
    candidate = target if _SCHEME_RE.match(target) else f"//{target}"
    try:
        return urlsplit(candidate).hostname or ""
    except ValueError:
        return ""


def _target_url(target: str) -> str:
    if _SCHEME_RE.match(target):
        return target.rstrip("/")
    return f"https://{target.lstrip('/')}".rstrip("/")


@dataclass(frozen=True, slots=True)
class ExpressionRenderResult:
    """The output of rendering nested placeholder expressions."""

    text: str
    unresolved: tuple[str, ...]
    tokens: tuple[PlaceholderToken, ...]


def _split_expression(expression: str) -> tuple[str, tuple[str, ...]]:
    parts = [part.strip() for part in expression.split("|")]
    path = parts[0]
    if not path or _PATH_RE.fullmatch(path) is None:
        return "", ()
    return path, tuple(part for part in parts[1:] if part)


def parse_placeholders(text: str) -> tuple[PlaceholderToken, ...]:
    """Tokenize text into literal spans and placeholder expressions."""
    tokens: list[PlaceholderToken] = []
    buffer: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text.startswith(_ESCAPED_OPEN, index):
            if not buffer:
                start = index
            buffer.append(_OPEN)
            index += len(_ESCAPED_OPEN)
            continue
        if text.startswith(_OPEN, index):
            end = text.find(_CLOSE, index + len(_OPEN))
            if end == -1:
                if not buffer:
                    start = index
                buffer.append(text[index])
                index += 1
                continue
            if buffer:
                tokens.append(
                    PlaceholderToken(
                        kind="text",
                        raw="".join(buffer),
                        name="",
                        expression="",
                        filters=(),
                        position=start,
                    )
                )
                buffer = []
            expression = text[index + len(_OPEN) : end].strip()
            path, filters = _split_expression(expression)
            tokens.append(
                PlaceholderToken(
                    kind="placeholder" if path else "text",
                    raw=text[index : end + len(_CLOSE)],
                    name=path,
                    expression=expression,
                    filters=filters,
                    position=index,
                )
            )
            index = end + len(_CLOSE)
            continue
        if not buffer:
            start = index
        buffer.append(text[index])
        index += 1
    if buffer:
        tokens.append(
            PlaceholderToken(
                kind="text",
                raw="".join(buffer),
                name="",
                expression="",
                filters=(),
                position=start,
            )
        )
    return tuple(tokens)


def resolve_path(path: str, values: Mapping[str, object]) -> str:
    """Resolve a dotted placeholder path against a value mapping."""
    head, _, tail = path.partition(".")
    raw: object = values.get(head, "")
    for part in filter(None, tail.split(".")):
        raw = raw.get(part, "") if isinstance(raw, Mapping) else ""
    return "" if raw is None else str(raw).strip()


def apply_filters(value: str, filters: tuple[str, ...]) -> str:
    """Apply a chain of placeholder filters from left to right."""
    result = value
    for spec in filters:
        name, _, argument = spec.partition(":")
        key = name.strip().lower()
        if key == "upper":
            result = result.upper()
        elif key == "lower":
            result = result.lower()
        elif key in ("trim", "strip"):
            result = result.strip()
        elif key == "slug":
            result = slugify(result)
        elif key == "title":
            result = result.title()
        elif key == "default" and not result:
            result = argument
        elif key == "prefix":
            result = f"{argument}{result}"
        elif key == "suffix":
            result = f"{result}{argument}"
    return result


def render_expressions(
    text: str, values: Mapping[str, object], *, keep_unresolved: bool = True
) -> ExpressionRenderResult:
    """Render nested expressions while reporting unresolved names."""
    tokens = parse_placeholders(text)
    chunks: list[str] = []
    unresolved: list[str] = []
    for token in tokens:
        if token.kind == "text":
            chunks.append(token.raw)
            continue
        value = resolve_path(token.name, values)
        resolved = apply_filters(value, token.filters) if value or token.filters else ""
        if not resolved:
            unresolved.append(token.name)
            if keep_unresolved:
                chunks.append(token.raw)
            continue
        chunks.append(resolved)
    return ExpressionRenderResult(
        text="".join(chunks),
        unresolved=tuple(dict.fromkeys(unresolved)),
        tokens=tokens,
    )


def expression_names(text: str) -> list[str]:
    """Return unique dotted expression names in first-use order."""
    return list(
        dict.fromkeys(
            token.name
            for token in parse_placeholders(text)
            if token.kind == "placeholder" and token.name
        )
    )


def base_name(path: str) -> str:
    """Return the root variable name of a dotted expression."""
    return path.split(".", 1)[0]


def validate_expression(expression: str) -> tuple[ValidationIssue, ...]:
    """Check an expression for a valid path and known filters."""
    path, filters = _split_expression(expression.strip())
    issues: list[ValidationIssue] = []
    if not path:
        issues.append(ValidationIssue("invalid-path", "Expression has no valid name."))
    for spec in filters:
        name = spec.partition(":")[0].strip().lower()
        if name not in FILTER_NAMES:
            issues.append(
                ValidationIssue(
                    code="unknown-filter",
                    message=f"Unknown placeholder filter: {name}",
                    severity="warning",
                )
            )
    return tuple(issues)


def escape_placeholders(text: str) -> str:
    """Escape opening delimiters so they render literally."""
    return text.replace(_OPEN, _ESCAPED_OPEN)


def unescape_placeholders(text: str) -> str:
    """Remove placeholder escaping from a string."""
    return text.replace(_ESCAPED_OPEN, _OPEN)
