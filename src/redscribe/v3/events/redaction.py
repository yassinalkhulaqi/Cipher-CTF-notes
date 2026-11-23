"""Redaction of event payloads before display or export."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

DEFAULT_SENSITIVE_KEYS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "privatekey",
    "private_key",
    "credential",
    "recoverycode",
    "recovery_code",
)

_REDACTED = "[redacted]"
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+")
_FLAG_PATTERN = re.compile(r"\bflag\{[^}]{1,200}\}", re.IGNORECASE)


def is_sensitive_key(key: str) -> bool:
    """Return whether a payload key looks sensitive."""
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(sensitive in normalized for sensitive in DEFAULT_SENSITIVE_KEYS)


def redact_text(value: str) -> str:
    """Remove common secret shapes from free text."""
    redacted = _EMAIL_PATTERN.sub("[email]", value)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    return _FLAG_PATTERN.sub("[flag-redacted]", redacted)


def redact_payload(payload: Mapping[str, Any], *, depth: int = 0) -> dict[str, Any]:
    """Recursively redact sensitive keys and values."""
    if depth > 12:
        return {"_truncated": True}
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if is_sensitive_key(key):
            result[key] = _REDACTED
        elif isinstance(value, str):
            result[key] = redact_text(value)
        elif isinstance(value, Mapping):
            result[key] = redact_payload(value, depth=depth + 1)
        elif isinstance(value, (list, tuple)):
            result[key] = [
                redact_payload(item, depth=depth + 1)
                if isinstance(item, Mapping)
                else redact_text(item)
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class RedactionPolicy:
    """Configurable payload redactor."""

    def __init__(self, *, extra_keys: tuple[str, ...] = (), enabled: bool = True) -> None:
        self._extra = tuple(key.casefold() for key in extra_keys)
        self._enabled = enabled

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Apply the policy to a payload mapping."""
        if not self._enabled:
            return dict(payload)
        cleaned = redact_payload(payload)
        for key in list(cleaned):
            if key.casefold() in self._extra:
                cleaned[key] = _REDACTED
        return cleaned

    @property
    def enabled(self) -> bool:
        """Whether redaction is active."""
        return self._enabled
