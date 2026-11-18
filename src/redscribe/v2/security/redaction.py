"""Redaction rules and helpers for privacy-aware rendering and export."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RedactionRule:
    """A deterministic rule for masking sensitive content."""

    name: str
    pattern: re.Pattern[str]
    replacement: str = "[REDACTED]"
    description: str = ""
    scope: str = "all"
    priority: int = 100
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)

    def apply(self, text: str) -> tuple[str, int]:
        if not self.enabled:
            return text, 0
        redacted, count = self.pattern.subn(self.replacement, text)
        return redacted, count

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "regex": self.pattern.pattern,
            "replacement": self.replacement,
            "description": self.description,
            "scope": self.scope,
            "priority": self.priority,
            "enabled": self.enabled,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class RedactionSummary:
    """Result of applying one or more redaction rules."""

    text: str
    applied: tuple[str, ...]
    counts: Mapping[str, int]
    total_replacements: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "applied": list(self.applied),
            "counts": dict(self.counts),
            "total_replacements": self.total_replacements,
        }


def _rule(
    name: str,
    pattern: str,
    replacement: str,
    description: str,
    *,
    scope: str = "all",
    priority: int = 100,
    tags: tuple[str, ...] = (),
    flags: int = 0,
) -> RedactionRule:
    return RedactionRule(
        name=name,
        pattern=re.compile(pattern, flags),
        replacement=replacement,
        description=description,
        scope=scope,
        priority=priority,
        tags=tags,
    )


_DEFAULT_RULES: tuple[RedactionRule, ...] = (
    _rule(
        "private_key",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        "PEM private key blocks.",
        priority=10,
        tags=("crypto", "critical"),
    ),
    _rule(
        "jwt",
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "[REDACTED_JWT]",
        "JSON Web Token values.",
        priority=20,
        tags=("auth", "token"),
    ),
    _rule(
        "aws_access_key",
        r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        "[REDACTED_AWS_ACCESS_KEY]",
        "AWS access key identifiers.",
        priority=20,
        tags=("cloud", "aws"),
    ),
    _rule(
        "authorization_bearer",
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-+/=]+",
        r"\1[REDACTED_TOKEN]",
        "Bearer authorization headers.",
        priority=30,
        tags=("auth", "header"),
    ),
    _rule(
        "basic_auth_url",
        r"([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@",
        r"\1[REDACTED_USER]:[REDACTED_PASS]@",
        "Embedded credentials in URLs.",
        priority=30,
        tags=("url", "credential"),
        flags=re.IGNORECASE,
    ),
    _rule(
        "password_assignment",
        r"(?i)(password|passwd|pwd|passphrase\s*[:=]\s*)(['\"]?)([^\s'\"`,;]{4,})(['\"]?)",
        r"\1\2[REDACTED_PASSWORD]\4",
        "Password and passphrase assignments.",
        priority=40,
        tags=("auth", "password"),
    ),
    _rule(
        "secret_assignment",
        r"(?i)((?:api[_-]?key|token|secret|client[_-]?secret|access[_-]?token)\s*[:=]\s*)(['\"]?)([A-Za-z0-9._\-+/=]{8,})(['\"]?)",
        r"\1\2[REDACTED_SECRET]\4",
        "Generic token and secret assignments.",
        priority=40,
        tags=("credential", "secret"),
    ),
    _rule(
        "email",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[REDACTED_EMAIL]",
        "Email addresses.",
        priority=60,
        tags=("pii", "contact"),
    ),
    _rule(
        "ipv4",
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
        "[REDACTED_IPV4]",
        "IPv4 addresses.",
        priority=70,
        tags=("network", "endpoint"),
    ),
    _rule(
        "uuid",
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
        "[REDACTED_UUID]",
        "UUID identifiers.",
        priority=80,
        tags=("identifier",),
    ),
    _rule(
        "credit_card_like",
        r"\b(?:\d[ -]*?){13,19}\b",
        "[REDACTED_NUMBER]",
        "Long numeric sequences resembling payment cards.",
        priority=90,
        tags=("pii", "payment"),
    ),
)


def builtin_redaction_rules() -> tuple[RedactionRule, ...]:
    """Return the default redaction rule catalog."""
    return _DEFAULT_RULES


def normalize_rules(rules: Sequence[RedactionRule] | None) -> tuple[RedactionRule, ...]:
    if rules is None:
        return _DEFAULT_RULES
    return tuple(sorted(rules, key=lambda rule: (rule.priority, rule.name)))


def apply_redactions(
    text: str,
    rules: Sequence[RedactionRule] | None = None,
    *,
    scopes: Sequence[str] | None = None,
) -> RedactionSummary:
    """Apply deterministic redaction rules to a text payload."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    allowed_scopes = {scope.strip().lower() for scope in scopes or () if scope.strip()}
    ordered = normalize_rules(rules)
    current = text
    applied: list[str] = []
    counts: dict[str, int] = {}
    total = 0
    for rule in ordered:
        if not rule.enabled:
            continue
        if (
            allowed_scopes
            and rule.scope.lower() not in allowed_scopes
            and "all" not in allowed_scopes
        ):
            continue
        current, count = rule.apply(current)
        if count:
            applied.append(rule.name)
            counts[rule.name] = counts.get(rule.name, 0) + count
            total += count
    return RedactionSummary(
        text=current,
        applied=tuple(applied),
        counts=counts,
        total_replacements=total,
    )


def redact_mapping(
    payload: Mapping[str, Any],
    *,
    rules: Sequence[RedactionRule] | None = None,
    keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Redact selected string fields inside a mapping."""
    selected = set(keys) if keys is not None else None
    result: dict[str, Any] = {}
    totals = 0
    per_field: dict[str, Any] = {}
    for key, value in payload.items():
        name = str(key)
        if selected is not None and name not in selected:
            result[name] = value
            continue
        if isinstance(value, str):
            summary = apply_redactions(value, rules=rules)
            result[name] = summary.text
            if summary.total_replacements:
                per_field[name] = summary.as_dict()
                totals += summary.total_replacements
        elif isinstance(value, list):
            redacted_items: list[Any] = []
            field_total = 0
            for item in value:
                if isinstance(item, str):
                    summary = apply_redactions(item, rules=rules)
                    redacted_items.append(summary.text)
                    field_total += summary.total_replacements
                else:
                    redacted_items.append(item)
            result[name] = redacted_items
            if field_total:
                per_field[name] = {"total_replacements": field_total}
                totals += field_total
        else:
            result[name] = value
    return {"data": result, "total_replacements": totals, "fields": per_field}
