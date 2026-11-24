"""Request identity, validation, and rate-limit helpers for the V3 API."""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.envelope import MAX_REQUEST_ID_LENGTH
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.entities.validation import clean_text, normalize_tags

_HEADER_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")


def new_request_id() -> str:
    """Generate a request identifier."""
    return f"req_{secrets.token_hex(12)}"


def normalize_request_id(value: str | None) -> str:
    """Validate or generate a request identifier."""
    if not value:
        return new_request_id()
    if len(value) > MAX_REQUEST_ID_LENGTH or not _HEADER_TOKEN_PATTERN.fullmatch(value):
        raise V3Error(V3ErrorCode.INVALID_REQUEST, "Invalid request id", field="x-request-id")
    return value


def require_str(payload: Mapping[str, Any], key: str, *, limit: int = 240) -> str:
    """Read a required string field."""
    value = payload.get(key)
    if not isinstance(value, str):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a string", field=key)
    if not value.strip():
        raise V3Error(V3ErrorCode.MISSING_FIELD, f"'{key}' cannot be blank", field=key)
    try:
        return clean_text(value, limit=limit)
    except ValueError as error:
        raise V3Error(V3ErrorCode.FIELD_TOO_LONG, str(error), field=key) from error


def optional_str(
    payload: Mapping[str, Any], key: str, *, default: str = "", limit: int = 4000
) -> str:
    """Read an optional string field."""
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a string", field=key)
    try:
        return clean_text(value, limit=limit)
    except ValueError as error:
        raise V3Error(V3ErrorCode.FIELD_TOO_LONG, str(error), field=key) from error


def require_choice(payload: Mapping[str, Any], key: str, choices: tuple[str, ...]) -> str:
    """Read a required field that must match a fixed choice set."""
    value = require_str(payload, key)
    if value not in choices:
        raise V3Error(
            V3ErrorCode.INVALID_CHOICE,
            f"'{key}' must be one of: {', '.join(choices)}",
            field=key,
        )
    return value


def optional_tags(payload: Mapping[str, Any], key: str = "tags") -> tuple[str, ...]:
    """Read and normalize an optional tag list."""
    value = payload.get(key, ())
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a list", field=key)
    try:
        return normalize_tags(str(tag) for tag in value)
    except ValueError as error:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(error), field=key) from error


def require_bool(payload: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    """Read a boolean field."""
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be a boolean", field=key)
    return value


class RateLimiter:
    """Fixed-window rate limiter for local API calls."""

    def __init__(self, *, limit: int = 120, window_seconds: float = 60.0) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Rate limits must be positive")
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}

    def allow(self, identity: str, now: float) -> bool:
        """Record a hit and return whether it is allowed."""
        start, count = self._hits.get(identity, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        if count >= self._limit:
            self._hits[identity] = (start, count)
            return False
        self._hits[identity] = (start, count + 1)
        return True

    def enforce(self, identity: str, now: float) -> None:
        """Raise a rate-limit error when the caller is over budget."""
        if not self.allow(identity, now):
            raise V3Error(V3ErrorCode.RATE_LIMITED, "Too many requests", retryable=True)

    def remaining(self, identity: str, now: float) -> int:
        """Return remaining requests for an identity."""
        start, count = self._hits.get(identity, (now, 0))
        if now - start >= self._window:
            return self._limit
        return max(0, self._limit - count)

    def reset(self, identity: str | None = None) -> None:
        """Clear rate state."""
        if identity is None:
            self._hits.clear()
        else:
            self._hits.pop(identity, None)
