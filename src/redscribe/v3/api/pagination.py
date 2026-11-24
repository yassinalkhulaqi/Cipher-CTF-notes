"""Opaque cursor pagination helpers for the V3 API."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, TypeVar

from redscribe.v3.api.envelope import PageMeta
from redscribe.v3.api.errors import V3Error, V3ErrorCode

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Validated pagination inputs."""

    offset: int = 0
    size: int = DEFAULT_PAGE_SIZE
    cursor: str = ""

    @classmethod
    def parse(
        cls,
        *,
        offset: Any = None,
        size: Any = None,
        cursor: str = "",
    ) -> PageRequest:
        """Parse and validate user-supplied pagination inputs."""
        if cursor:
            decoded = decode_cursor(cursor)
            return cls(offset=decoded.offset, size=decoded.size, cursor=cursor)
        parsed_offset = 0 if offset is None else _as_int(offset, "offset")
        parsed_size = DEFAULT_PAGE_SIZE if size is None else _as_int(size, "size")
        if parsed_offset < 0:
            raise V3Error(V3ErrorCode.INVALID_REQUEST, "Offset cannot be negative", field="offset")
        if parsed_size < 1 or parsed_size > MAX_PAGE_SIZE:
            raise V3Error(
                V3ErrorCode.INVALID_REQUEST,
                f"Size must be between 1 and {MAX_PAGE_SIZE}",
                field="size",
            )
        return cls(offset=parsed_offset, size=parsed_size)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"offset": self.offset, "size": self.size, "cursor": self.cursor}


@dataclass(frozen=True, slots=True)
class DecodedCursor:
    """Decoded cursor payload."""

    offset: int
    size: int
    filter_hash: str = ""


def _as_int(value: Any, field_name: str) -> int:
    """Convert a query parameter to an integer."""
    if isinstance(value, bool):
        raise V3Error(
            V3ErrorCode.INVALID_TYPE, f"'{field_name}' must be an integer", field=field_name
        )
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise V3Error(
            V3ErrorCode.INVALID_TYPE,
            f"'{field_name}' must be an integer",
            field=field_name,
        ) from error


def encode_cursor(offset: int, size: int, *, filter_hash: str = "") -> str:
    """Encode a cursor with a checksum so tampering is detected."""
    payload = {"o": offset, "s": size, "f": filter_hash}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    checksum = hashlib.blake2b(raw, digest_size=6).hexdigest()
    combined = {"p": payload, "c": checksum}
    encoded = json.dumps(combined, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> DecodedCursor:
    """Decode and verify a cursor."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        combined = json.loads(raw.decode("utf-8"))
        payload = combined["p"]
        checksum = combined["c"]
        expected = hashlib.blake2b(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            digest_size=6,
        ).hexdigest()
        if checksum != expected:
            raise ValueError("cursor checksum mismatch")
        offset = int(payload["o"])
        size = int(payload["s"])
        filter_hash = str(payload.get("f", ""))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        raise V3Error(V3ErrorCode.INVALID_CURSOR, "Invalid cursor") from error
    if offset < 0 or size < 1 or size > MAX_PAGE_SIZE:
        raise V3Error(V3ErrorCode.INVALID_CURSOR, "Cursor is out of range")
    return DecodedCursor(offset=offset, size=size, filter_hash=filter_hash)


def paginate(
    items: tuple[T, ...],
    request: PageRequest,
    *,
    filter_hash: str = "",
) -> tuple[tuple[T, ...], PageMeta, str]:
    """Slice a sequence and return items, meta, and the next cursor."""
    start = min(request.offset, len(items))
    end = min(start + request.size, len(items))
    window = items[start:end]
    meta = PageMeta.for_window(start, request.size, len(items))
    next_cursor = encode_cursor(end, request.size, filter_hash=filter_hash) if meta.has_next else ""
    return window, meta, next_cursor


def filter_hash(query: str, kinds: tuple[str, ...] = ()) -> str:
    """Derive a stable hash representing a query's filters."""
    raw = json.dumps({"q": query, "k": sorted(kinds)}, sort_keys=True)
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()
