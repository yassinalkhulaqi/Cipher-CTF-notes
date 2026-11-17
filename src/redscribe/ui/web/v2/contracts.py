"""Contracts, envelopes, and pagination helpers for the v2 API.

The v2 surface keeps the existing RPC style but adds stable error codes,
request IDs, opaque cursors, ETags, and a single success/error envelope. It is
intentionally independent from :mod:`redscribe.ui.web.api` so the v1 dispatch
table keeps its established behavior.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

API_VERSION = "2.0"

MAX_BODY_BYTES = 8 * 1024 * 1024
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_REQUEST_ID_LENGTH = 128
MAX_IDEMPOTENCY_KEY_LENGTH = 200


class V2ErrorCode(str, Enum):
    """Stable machine-readable categories for v2 failures."""

    UNKNOWN_ROUTE = "unknown_route"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    INVALID_JSON = "invalid_json"
    INVALID_TYPE = "invalid_type"
    MISSING_FIELD = "missing_field"
    INVALID_CHOICE = "invalid_choice"
    FIELD_TOO_LONG = "field_too_long"
    INVALID_CURSOR = "invalid_cursor"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    CONFLICT = "conflict"
    INTERNAL = "internal"


class V2Error(Exception):
    """An error that can be rendered as a stable v2 error envelope."""

    def __init__(
        self,
        status: int = 400,
        code: str | V2ErrorCode = V2ErrorCode.INVALID_REQUEST,
        message: str = "Invalid request",
        *,
        details: Mapping[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code.value if isinstance(code, V2ErrorCode) else code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "retryable": self.retryable,
        }


def _field_error(
    status: int,
    code: V2ErrorCode,
    message: str,
    field: str,
) -> V2Error:
    return V2Error(status, code, message, details={"field": field})


def require_str(
    body: Mapping[str, Any],
    key: str,
    *,
    default: str | None = None,
    max_length: int | None = None,
) -> str:
    """Return a required string field or raise a stable v2 error."""
    if key not in body:
        if default is not None:
            return default
        raise _field_error(400, V2ErrorCode.MISSING_FIELD, f"Missing '{key}'", key)
    value = body[key]
    if not isinstance(value, str):
        raise _field_error(400, V2ErrorCode.INVALID_TYPE, f"'{key}' must be a string", key)
    if max_length is not None and len(value) > max_length:
        raise _field_error(
            400,
            V2ErrorCode.FIELD_TOO_LONG,
            f"{key} exceeds {max_length} characters",
            key,
        )
    return value


def optional_str(
    body: Mapping[str, Any],
    key: str,
    *,
    default: str | None = None,
    max_length: int | None = None,
) -> str | None:
    """Return an optional string field, or ``default`` when absent/null."""
    if key not in body or body[key] is None:
        return default
    value = body[key]
    if not isinstance(value, str):
        raise _field_error(400, V2ErrorCode.INVALID_TYPE, f"'{key}' must be a string", key)
    if max_length is not None and len(value) > max_length:
        raise _field_error(
            400,
            V2ErrorCode.FIELD_TOO_LONG,
            f"{key} exceeds {max_length} characters",
            key,
        )
    return value


def require_int(body: Mapping[str, Any], key: str) -> int:
    """Return a required integer field, rejecting booleans."""
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _field_error(
            400,
            V2ErrorCode.INVALID_TYPE,
            f"'{key}' must be an integer",
            key,
        )
    return int(value)


def optional_int(body: Mapping[str, Any], key: str) -> int | None:
    """Return an optional integer field, rejecting booleans."""
    if key not in body or body[key] is None:
        return None
    return require_int(body, key)


def require_bool(body: Mapping[str, Any], key: str) -> bool:
    """Return a required boolean field."""
    value = body.get(key)
    if not isinstance(value, bool):
        raise _field_error(
            400,
            V2ErrorCode.INVALID_TYPE,
            f"'{key}' must be a boolean",
            key,
        )
    return value


def encode_cursor(value: Any) -> str:
    """Encode a cursor payload as an opaque, URL-safe base64 string."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Any:
    """Decode an opaque cursor, raising a stable error when malformed."""
    if not isinstance(cursor, str) or not cursor:
        raise V2Error(400, V2ErrorCode.INVALID_CURSOR, "Invalid cursor")
    padding = "=" * ((4 - len(cursor) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeError, json.JSONDecodeError) as exc:
        raise V2Error(400, V2ErrorCode.INVALID_CURSOR, "Invalid cursor") from exc


def cursor_offset(cursor: str | None) -> int:
    """Return the offset encoded in a cursor, defaulting to zero."""
    if cursor is None or cursor == "":
        return 0
    value = decode_cursor(cursor)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        if isinstance(value, Mapping):
            raw = value.get("offset")
            if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
                return raw
        raise V2Error(400, V2ErrorCode.INVALID_CURSOR, "Invalid cursor")
    return value


@dataclass(frozen=True, slots=True)
class Page:
    """Pagination metadata for one list response."""

    cursor: str | None = None
    next: str | None = None
    total: int | None = None
    limit: int | None = None
    has_more: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "cursor": self.cursor,
            "next": self.next,
            "total": self.total,
            "limit": self.limit,
            "has_more": self.has_more,
        }


ItemT = TypeVar("ItemT")


def paginate(
    items: Sequence[ItemT],
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[ItemT], Page]:
    """Slice an ordered sequence with an opaque offset cursor."""
    start = min(cursor_offset(cursor), len(items))
    end = min(start + limit, len(items))
    has_more = end < len(items)
    page = Page(
        cursor=encode_cursor({"offset": start}),
        next=encode_cursor({"offset": end}) if has_more else None,
        total=len(items),
        limit=limit,
        has_more=has_more,
    )
    return list(items[start:end]), page


def compute_etag(value: Any) -> str:
    """Return a deterministic ETag for a JSON-serializable value."""
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


class Envelope(dict[str, Any]):
    """A v2 envelope that also carries its HTTP status and ETag."""

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        status: int = 200,
        etag: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(payload)
        self.status = status
        self.etag = etag
        self.headers: dict[str, str] = dict(headers or {})


def envelope(
    data: Any,
    *,
    request_id: str,
    page: Page | Mapping[str, Any] | None = None,
    etag: str | None = None,
) -> Envelope:
    """Build the v2 success envelope."""
    meta: dict[str, Any] = {
        "request_id": request_id,
        "api_version": API_VERSION,
    }
    if page is not None:
        meta["page"] = page.as_dict() if isinstance(page, Page) else dict(page)
    if etag is not None:
        meta["etag"] = etag
    return Envelope({"ok": True, "data": data, "meta": meta}, etag=etag)


def error_envelope(
    error: V2Error | str | None = None,
    *,
    request_id: str,
    status: int = 400,
    code: str | V2ErrorCode = V2ErrorCode.INVALID_REQUEST,
    message: str = "",
    details: Mapping[str, Any] | None = None,
    retryable: bool = False,
) -> Envelope:
    """Build the v2 error envelope from an error or explicit fields."""
    if isinstance(error, V2Error):
        failure = error
    else:
        failure = V2Error(
            status,
            code,
            message or (error if isinstance(error, str) and error else "Request failed"),
            details=details,
            retryable=retryable,
        )
    payload = {
        "ok": False,
        "error": {
            **failure.as_dict(),
            "request_id": request_id,
        },
    }
    return Envelope(payload, status=failure.status)
