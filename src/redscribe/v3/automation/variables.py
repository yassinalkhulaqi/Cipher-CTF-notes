"""Typed variable validation, coercion and template interpolation.

Variables are JSON values only. Interpolation supports ``{{ name }}``,
``{{ vars.name }}`` and step outputs such as ``{{ steps.collect.ref }}``. When a
template consists of exactly one placeholder the resolved *type* is preserved;
embedded placeholders are rendered to text. Secrets are masked in every
representation that can reach a trace, record or API response.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from redscribe.v3.automation.encoding import copy_value, digest
from redscribe.v3.automation.errors import VariableResolutionError
from redscribe.v3.automation.parsing import issue
from redscribe.v3.automation.types import (
    PlaybookDefinition,
    ValidationIssue,
    Value,
    VariableDefinition,
    VariableKind,
    as_text,
)

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def collect_placeholders(template: str) -> tuple[str, ...]:
    """Return distinct placeholder paths in a template."""
    found: list[str] = []
    for match in _PLACEHOLDER.finditer(template):
        key = match.group(1).strip()
        if key not in found:
            found.append(key)
    return tuple(found)


def _lookup(context: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve a dotted placeholder path against the resolution context."""
    parts = path.split(".")
    root = parts[0]
    if root in ("vars", "steps"):
        current: Any = context.get(root, {})
        remainder = parts[1:]
    else:
        current = context.get("vars", {})
        remainder = parts
        if root in context and root not in current:
            current = context
    for part in remainder:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def interpolate(template: str, context: Mapping[str, Any], *, strict: bool = True) -> Any:
    """Interpolate a string template, preserving the type of a sole value."""
    matches = list(_PLACEHOLDER.finditer(template))
    if not matches:
        return template
    if len(matches) == 1 and matches[0].span() == (0, len(template)):
        key = matches[0].group(1).strip()
        found, value = _lookup(context, key)
        if not found:
            if strict:
                raise VariableResolutionError(f"Unresolved variable: {key}", path=key)
            return ""
        return copy_value(value)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        found, value = _lookup(context, key)
        if not found:
            if strict:
                raise VariableResolutionError(f"Unresolved variable: {key}", path=key)
            return ""
        return as_text(value)

    return _PLACEHOLDER.sub(replace, template)


def _coerce(
    value: Value, definition: VariableDefinition, path: str
) -> tuple[Value, ValidationIssue | None]:
    """Coerce and validate one value against its definition."""
    kind = definition.kind
    if kind is VariableKind.NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return value, issue(
                "invalid_type", f"Expected a number for {definition.key}", path=path
            )
        try:
            number = float(value)
        except ValueError:
            return value, issue(
                "invalid_type", f"Expected a number for {definition.key}", path=path
            )
        if definition.minimum is not None and number < definition.minimum:
            return value, issue("out_of_range", f"{definition.key} is below its minimum", path=path)
        if definition.maximum is not None and number > definition.maximum:
            return value, issue("out_of_range", f"{definition.key} is above its maximum", path=path)
        return int(number) if number.is_integer() else number, None
    if kind is VariableKind.BOOLEAN:
        if isinstance(value, bool):
            return value, None
        if isinstance(value, int) and value in (0, 1):
            return bool(value), None
        if isinstance(value, str) and value.strip().casefold() in (
            "true",
            "false",
            "yes",
            "no",
            "on",
            "off",
            "1",
            "0",
        ):
            return value.strip().casefold() in ("true", "yes", "on", "1"), None
        return value, issue("invalid_type", f"Expected a boolean for {definition.key}", path=path)
    if kind is VariableKind.CHOICE:
        text = as_text(value)
        if text not in definition.choices:
            return value, issue(
                "invalid_choice",
                f"{definition.key} must be one of: {', '.join(definition.choices)}",
                path=path,
            )
        return text, None
    if kind is VariableKind.LIST:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items, None
        if isinstance(value, list):
            return deepcopy(value), None
        return value, issue("invalid_type", f"Expected a list for {definition.key}", path=path)
    if kind is VariableKind.ENTITY_REF:
        from redscribe.v3.entities.types import EntityId

        text = as_text(value)
        try:
            EntityId.parse(text)
        except ValueError:
            return value, issue(
                "invalid_ref", f"{definition.key} must be a kind:value reference", path=path
            )
        return text, None
    text = as_text(value)
    if definition.pattern:
        import re as _re

        if _re.fullmatch(definition.pattern, text) is None:
            return value, issue(
                "invalid_pattern", f"{definition.key} does not match its pattern", path=path
            )
    if definition.choices and text not in definition.choices:
        return value, issue(
            "invalid_choice",
            f"{definition.key} must be one of: {', '.join(definition.choices)}",
            path=path,
        )
    return text, None


class VariableResolution:
    """Result of validating and coercing all player-supplied variables."""

    __slots__ = ("issues", "secrets", "values")

    def __init__(
        self,
        *,
        values: dict[str, Value],
        issues: tuple[ValidationIssue, ...],
        secrets: frozenset[str],
    ) -> None:
        self.values = values
        self.issues = issues
        self.secrets = secrets

    @property
    def ok(self) -> bool:
        """Whether every variable is valid."""
        return not any(entry.is_error for entry in self.issues)

    def raise_if_invalid(self) -> None:
        """Raise when one or more variables are invalid."""
        if not self.ok:
            messages = "; ".join(entry.message for entry in self.issues if entry.is_error)
            raise VariableResolutionError(messages, path="variables")

    def context(self, outputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Build an interpolation context with vars and step outputs."""
        return {"vars": copy_value(self.values), "steps": copy_value(dict(outputs or {}))}

    def as_dict(self) -> dict[str, Any]:
        """Return a safe, redacted representation."""
        return {
            "values": {
                key: ("***" if key in self.secrets else value) for key, value in self.values.items()
            },
            "issues": [entry.as_dict() for entry in self.issues],
            "ok": self.ok,
        }


def validate_values(
    playbook: PlaybookDefinition,
    supplied: Mapping[str, Value] | None = None,
) -> VariableResolution:
    """Validate supplied values, apply defaults and coerce to declared types."""
    values: dict[str, Value] = {}
    issues: list[ValidationIssue] = []
    definitions = {definition.key: definition for definition in playbook.variables}
    extras = sorted(set(supplied or {}) - set(definitions))
    for key in extras:
        issues.append(
            issue("unknown_variable", f"Unknown variable: {key}", path=f"variables.{key}")
        )
    for definition in playbook.variables:
        path = f"variables.{definition.key}"
        if definition.required and definition.key not in (supplied or {}):
            issues.append(
                issue("missing_variable", f"Missing required variable: {definition.key}", path=path)
            )
            continue
        raw = (
            supplied[definition.key]
            if supplied is not None and definition.key in supplied
            else deepcopy(definition.default)
        )
        coerced, problem = _coerce(raw, definition, path)
        if problem is not None:
            issues.append(problem)
        values[definition.key] = coerced
    return VariableResolution(
        values=values,
        issues=tuple(issues),
        secrets=frozenset(
            definition.key for definition in playbook.variables if definition.is_secret
        ),
    )


def resolve_inputs(
    inputs: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Resolve every string in a nested input structure."""
    result: dict[str, Any] = {}
    for key, value in inputs.items():
        result[key] = _resolve_value(value, context, strict=strict)
    return result


def _resolve_value(value: Any, context: Mapping[str, Any], *, strict: bool) -> Any:
    """Recursively resolve one input value."""
    if isinstance(value, str):
        return interpolate(value, context, strict=strict)
    if isinstance(value, list):
        return [_resolve_value(item, context, strict=strict) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _resolve_value(item, context, strict=strict) for key, item in value.items()
        }
    return copy_value(value)


def fingerprint_values(values: Mapping[str, Any]) -> str:
    """Return a stable fingerprint of raw variable values."""
    return digest({"variables": dict(values)})


def placeholder_report(inputs: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """List placeholders used by each input field."""
    report: dict[str, tuple[str, ...]] = {}
    for key, value in inputs.items():
        if isinstance(value, str):
            report[key] = collect_placeholders(value)
        elif isinstance(value, (list, dict)):
            report[key] = collect_placeholders(str(value))
    return report
