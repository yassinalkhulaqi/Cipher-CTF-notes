"""Cursor pagination and ETag concurrency helpers for the v4 API.

Cursors are opaque, deterministic, and reversible without a network round trip.
They encode an offset and a sort key so pages remain stable while items are
added at the head of a list.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class PaginationError(Exception):
    """Raised for malformed cursors or invalid page arguments."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """An opaque pagination cursor."""

    offset: int
    sort_key: str
    version: int = 1

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise PaginationError("offset must be >= 0")
        if self.version < 1:
            raise PaginationError("version must be >= 1")

    def encode(self) -> str:
        payload = {"o": self.offset, "k": self.sort_key, "v": self.version}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return f"v{self.version}.{token}"

    @classmethod
    def decode(cls, token: str) -> Cursor:
        if "." not in token:
            raise PaginationError("malformed cursor")
        prefix, encoded = token.split(".", 1)
        if not prefix.startswith("v") or not prefix[1:].isdigit():
            raise PaginationError("malformed cursor version")
        version = int(prefix[1:])
        padding = "=" * (-len(encoded) % 4)
        try:
            raw = base64.urlsafe_b64decode(encoded + padding)
            payload = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise PaginationError("undecodable cursor") from exc
        return cls(
            offset=int(payload.get("o", 0)),
            sort_key=str(payload.get("k", "")),
            version=version,
        )


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """A single page of results with navigation metadata."""

    items: tuple[T, ...]
    total: int
    page: int
    page_size: int
    next_cursor: str = ""
    etag: str = ""

    @property
    def has_more(self) -> bool:
        return bool(self.next_cursor)

    def to_dict(self, serialize: Any = None) -> dict[str, Any]:
        convert = serialize or (lambda item: item)
        return {
            "items": [convert(item) for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "next_cursor": self.next_cursor,
            "etag": self.etag,
        }


def paginate(items: Sequence[T], page: int = 1, page_size: int = 50) -> PageResult[T]:
    """Return a page of ``items`` with a cursor for the next page."""
    if page < 1:
        raise PaginationError("page must be >= 1")
    if not 1 <= page_size <= 500:
        raise PaginationError("page_size must be between 1 and 500")
    start = (page - 1) * page_size
    chunk = tuple(items[start : start + page_size])
    next_cursor = ""
    if start + page_size < len(items):
        last = chunk[-1] if chunk else items[start - 1]
        sort_key = str(getattr(last, "id", last)) if chunk else ""
        next_cursor = Cursor(offset=start + page_size, sort_key=sort_key).encode()
    digest = hashlib.sha256(f"{page}:{page_size}:{len(items)}:{next_cursor}".encode()).hexdigest()[
        :16
    ]
    return PageResult(
        items=chunk,
        total=len(items),
        page=page,
        page_size=page_size,
        next_cursor=next_cursor,
        etag=digest,
    )


def apply_cursor(items: Sequence[T], cursor: str | None) -> Sequence[T]:
    """Decode a cursor and slice ``items`` from its offset."""
    if not cursor:
        return items
    decoded = Cursor.decode(cursor)
    return items[decoded.offset :]


def weak_etag(value: str) -> str:
    """Build a stable weak ETag for a serialized resource."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f'W/"{digest}"'


def _normalize_etag(value: str) -> str:
    return value.strip().removeprefix("W/").strip('"')


def etag_matches(if_none_match: str, etag: str) -> bool:
    """Compare two ETags, ignoring the weak prefix and surrounding quotes."""
    return _normalize_etag(if_none_match) == _normalize_etag(etag)
