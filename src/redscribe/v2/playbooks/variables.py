"""Variable discovery, coercion, and validation for playbook runs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from redscribe.v2.playbooks.interpolate import mask_values
from redscribe.v2.playbooks.types import (
    Issue,
    Value,
    Values,
    VariableDefinition,
    VariableKind,
)

BUILTIN_KEYS: tuple[str, ...] = (
    "target",
    "host",
    "domain",
    "url",
    "ip",
    "port",
    "scheme",
    "path",
    "slug",
    "date",
    "time",
    "user",
    "password",
    "lhost",
    "lport",
    "flag",
    "note",
    "engagement",
    "operator",
)

BUILTIN_DEFINITIONS: tuple[VariableDefinition, ...] = (
    VariableDefinition("target", "Target", description="Host, IP, URL, or CIDR in scope"),
    VariableDefinition("domain", "Domain", description="Primary DNS name"),
    VariableDefinition("url", "URL", description="Base URL including scheme"),
    VariableDefinition("port", "Port", description="Primary service port"),
    VariableDefinition("user", "Username", description="Known account name"),
    VariableDefinition("password", "Password", kind=VariableKind.SECRET, secret=True),
    VariableDefinition("lhost", "Listener host", description="Local address for callbacks"),
    VariableDefinition("lport", "Listener port", description="Local port for callbacks"),
    VariableDefinition("flag", "Flag", description="Captured flag value"),
    VariableDefinition("note", "Note", description="Short working note"),
)

_TRUE_VALUES = frozenset({"true", "yes", "on", "1", "y", "t"})
_FALSE_VALUES = frozenset({"false", "no", "off", "0", "n", "f", ""})


@dataclass(frozen=True, slots=True)
class Resolution:
    """The outcome of resolving values for a playbook or template."""

    values: Values
    missing: tuple[str, ...] = ()
    invalid: tuple[Issue, ...] = ()
    warnings: tuple[Issue, ...] = ()
    derived: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing and not any(issue.is_error for issue in self.invalid)

    def as_dict(self, *, reveal_secrets: bool = False) -> dict[str, Any]:
        display = dict(self.values)
        return {
            "values": display if reveal_secrets else mask_known(display, ()),
            "missing": list(self.missing),
            "invalid": [issue.as_dict() for issue in self.invalid],
            "warnings": [issue.as_dict() for issue in self.warnings],
            "derived": list(self.derived),
            "ok": self.ok,
        }


def normalize_value(value: object) -> Value | None:
    """Convert an untrusted JSON value into a supported variable value."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return str(value)


def normalize_values(values: Any) -> Values:
    """Normalize a mapping of untrusted values into a variable context."""
    if not isinstance(values, dict):
        return {}
    result: Values = {}
    for key, raw in values.items():
        name = str(key).strip()
        normalized = normalize_value(raw)
        if name and normalized is not None:
            result[name] = normalized
    return result


def derive_values(target: str = "", *, base: Values | None = None) -> Values:
    """Build a context of useful variables derived from a target string."""
    values: Values = dict(base or {})
    now = datetime.now(timezone.utc)
    values.setdefault("date", now.date().isoformat())
    values.setdefault("time", now.strftime("%H:%M:%SZ"))
    values.setdefault("operator", "redscribe")
    cleaned = target.strip()
    if not cleaned:
        return values
    values.setdefault("target", cleaned)
    parsed = urlparse(cleaned if "://" in cleaned else f"//{cleaned}")
    hostname = (parsed.hostname or "").strip("[]")
    if parsed.scheme and parsed.scheme not in ("", "tcp", "udp"):
        values.setdefault("scheme", parsed.scheme)
        values.setdefault(
            "url", f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.netloc else cleaned
        )
    else:
        values.setdefault("url", f"http://{cleaned}" if hostname else cleaned)
    if hostname:
        values.setdefault("host", hostname)
        values.setdefault("domain", hostname)
        if _is_ip(hostname):
            values.setdefault("ip", hostname)
    if parsed.port:
        values.setdefault("port", parsed.port)
    host = _as_text(values.get("host", cleaned))
    values.setdefault("slug", re.sub(r"[^a-zA-Z0-9]+", "-", host).strip("-").lower())
    if parsed.path:
        values.setdefault("path", parsed.path)
    return values


def resolve_variables(
    definitions: tuple[VariableDefinition, ...] | list[VariableDefinition],
    provided: Any,
    *,
    target: str = "",
    strict: bool = False,
) -> Resolution:
    """Resolve, coerce, and validate values against declared definitions."""
    context = derive_values(target, base=normalize_values(provided))
    derived = tuple(key for key in context if key not in normalize_values(provided))
    missing: list[str] = []
    invalid: list[Issue] = []
    warnings: list[Issue] = []
    for definition in definitions:
        if definition.key not in context or _is_empty(context[definition.key]):
            if definition.required:
                missing.append(definition.key)
                continue
            if definition.default != "":
                coerced, default_issues = coerce_value(definition, definition.default)
                invalid.extend(default_issues)
                if coerced is not None:
                    context[definition.key] = coerced
            continue
        coerced, issues = coerce_value(definition, context[definition.key])
        invalid.extend(issues)
        if coerced is not None:
            context[definition.key] = coerced
    unknown = set(context) - {item.key for item in definitions} - set(BUILTIN_KEYS)
    if unknown and strict:
        for key in sorted(unknown):
            warnings.append(
                Issue(
                    code="unknown-variable",
                    message=f"Variable is not declared: {key}",
                    severity="warning",
                )
            )
    return Resolution(
        values=context,
        missing=tuple(missing),
        invalid=tuple(invalid),
        warnings=tuple(warnings),
        derived=derived,
    )


def coerce_value(
    definition: VariableDefinition, value: Value
) -> tuple[Value | None, tuple[Issue, ...]]:
    """Coerce one value to its declared type and validate constraints."""
    issues: list[Issue] = []
    kind = definition.kind
    if kind in (VariableKind.TEXT, VariableKind.SECRET):
        result: Value = _as_text(value)
    elif kind == VariableKind.NUMBER:
        try:
            text = _as_text(value).strip()
            result = float(text) if "." in text else int(text)
        except (TypeError, ValueError):
            issues.append(Issue("invalid-number", f"{definition.key} must be a number"))
            return None, tuple(issues)
    elif kind == VariableKind.BOOLEAN:
        text = _as_text(value).strip().casefold()
        if text in _TRUE_VALUES:
            result = True
        elif text in _FALSE_VALUES:
            result = False
        else:
            issues.append(Issue("invalid-boolean", f"{definition.key} must be true or false"))
            return None, tuple(issues)
    elif kind == VariableKind.LIST:
        if isinstance(value, tuple):
            result = tuple(_as_text(item) for item in value)
        else:
            result = tuple(part.strip() for part in _as_text(value).split(",") if part.strip())
    else:
        result = _as_text(value)
    if definition.choices and _as_text(result) not in definition.choices:
        issues.append(
            Issue(
                code="invalid-choice",
                message=f"{definition.key} must be one of: {', '.join(definition.choices)}",
            )
        )
    if definition.pattern:
        try:
            if re.search(definition.pattern, _as_text(result)) is None:
                issues.append(
                    Issue("pattern-mismatch", f"{definition.key} does not match its pattern")
                )
        except re.error:
            issues.append(Issue("invalid-pattern", f"{definition.key} has an invalid pattern"))
    if kind == VariableKind.NUMBER and isinstance(result, (int, float)):
        number = float(result)
        if definition.minimum is not None and number < definition.minimum:
            issues.append(Issue("below-minimum", f"{definition.key} is below the minimum"))
        if definition.maximum is not None and number > definition.maximum:
            issues.append(Issue("above-maximum", f"{definition.key} is above the maximum"))
    return result, tuple(issues)


def variable_options(definitions: tuple[VariableDefinition, ...]) -> list[dict[str, Any]]:
    """Return editor-ready metadata for a set of variables."""
    return [definition.as_dict() for definition in definitions]


def suggest_variables(
    definitions: tuple[VariableDefinition, ...], query: str, *, limit: int = 10
) -> list[VariableDefinition]:
    """Rank variables by label, key, and description relevance."""
    needle = query.strip().casefold()
    if not needle:
        return list(definitions[:limit])
    scored: list[tuple[int, VariableDefinition]] = []
    for definition in definitions:
        label = definition.label.casefold()
        key = definition.key.casefold()
        description = definition.description.casefold()
        score = 0
        if key.startswith(needle):
            score += 6
        if needle in key:
            score += 4
        if needle in label:
            score += 3
        if needle in description:
            score += 1
        if score:
            scored.append((score, definition))
    scored.sort(key=lambda item: (-item[0], item[1].key))
    return [definition for _, definition in scored[:limit]]


def mask_known(values: Values, secrets: tuple[str, ...]) -> dict[str, str]:
    """Mask secret and explicitly protected variable values."""
    protected = set(secrets) | {
        key for key, value in values.items() if isinstance(value, str) and key in SECRET_HINTS
    }
    output: dict[str, str] = {}
    for key, value in values.items():
        output[key] = "***" if key in protected else _as_text(value)
    return output


def masked_values(values: Values) -> dict[str, str]:
    """Mask every value in a context for display in shared previews."""
    return mask_values(values, visible=1)


SECRET_HINTS: frozenset[str] = frozenset(
    {"password", "passwd", "secret", "token", "api_key", "apikey", "credential"}
)


def _is_empty(value: Value) -> bool:
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, tuple):
        return not value
    return False


def _is_ip(value: str) -> bool:
    parts = value.split(".")
    if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
        return True
    return ":" in value and all(char in "0123456789abcdefABCDEF:" for char in value)


def _as_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return ",".join(_as_text(item) for item in value)
    if value is None:
        return ""
    return str(value)
