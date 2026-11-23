"""Idempotency keys and ETag concurrency for the V3 API."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from redscribe.v3.api.errors import V3Error, V3ErrorCode

MAX_KEY_LENGTH = 200


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Cached result of a previously executed write."""

    key: str
    fingerprint: str
    payload: dict[str, Any]
    status: int = 200


class IdempotencyStore(Protocol):
    """Storage contract for idempotency records."""

    def get(self, key: str) -> IdempotencyRecord | None:
        """Return a cached record by key."""
        ...

    def put(self, record: IdempotencyRecord) -> None:
        """Store a record."""
        ...


class MemoryIdempotencyStore:
    """In-memory implementation used by services and tests."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}

    def get(self, key: str) -> IdempotencyRecord | None:
        """Return a cached record."""
        return self._records.get(key)

    def put(self, record: IdempotencyRecord) -> None:
        """Store a record."""
        self._records[record.key] = record

    def size(self) -> int:
        """Return the number of cached records."""
        return len(self._records)

    def clear(self) -> None:
        """Drop all records."""
        self._records.clear()


class IdempotencyGuard:
    """Ensures repeated writes with the same key return the cached result."""

    def __init__(self, store: IdempotencyStore | None = None) -> None:
        self._store: IdempotencyStore = store or MemoryIdempotencyStore()

    @staticmethod
    def fingerprint(payload: Any) -> str:
        """Compute a stable fingerprint of a request payload."""
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.blake2b(raw.encode("utf-8"), digest_size=16).hexdigest()

    def execute(
        self,
        key: str,
        payload: Any,
        operation: Any,
    ) -> tuple[dict[str, Any], bool]:
        """Return cached result or run the operation and cache its result."""
        if not key or len(key) > MAX_KEY_LENGTH:
            raise V3Error(
                V3ErrorCode.INVALID_REQUEST,
                f"Idempotency key must be 1-{MAX_KEY_LENGTH} characters",
                field="idempotency_key",
            )
        fingerprint = self.fingerprint(payload)
        cached = self._store.get(key)
        if cached is not None:
            if cached.fingerprint != fingerprint:
                raise V3Error(
                    V3ErrorCode.IDEMPOTENCY_CONFLICT,
                    "Idempotency key was reused with a different payload",
                )
            return dict(cached.payload), True
        result = operation()
        if not isinstance(result, dict):
            raise V3Error(V3ErrorCode.INTERNAL, "Idempotent operation must return a mapping")
        self._store.put(IdempotencyRecord(key=key, fingerprint=fingerprint, payload=result))
        return dict(result), False


def compute_etag(payload: Any) -> str:
    """Compute a strong ETag for a response body."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.blake2b(raw.encode("utf-8"), digest_size=16).hexdigest()
    return f'"{digest}"'


def etag_matches(if_none_match: str, etag: str) -> bool:
    """Return whether a conditional header matches an ETag."""
    if not if_none_match or if_none_match.strip() == "*":
        return bool(if_none_match.strip())
    candidates = [item.strip() for item in if_none_match.split(",")]
    return etag in candidates or f"W/{etag}" in candidates


def version_etag(version: int, updated_at: float) -> str:
    """Build an ETag from a record version and timestamp."""
    return compute_etag({"version": version, "updated_at": updated_at})
