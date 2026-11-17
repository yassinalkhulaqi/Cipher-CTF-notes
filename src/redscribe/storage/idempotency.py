"""Idempotency keys for safely replayable mutating requests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast

from redscribe.domain.utils import parse_timestamp


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """One stored request response keyed by an idempotency key."""

    key: str
    method: str
    request_hash: str
    status: int
    response: dict[str, object]
    created_at: str
    expires_at: str


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def hash_request(method: str, body: object) -> str:
    """Return a stable hash over the method and canonicalized request body."""
    canonical = _canonical_json({"method": method.strip().upper(), "body": body})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_datetime(now: str | datetime | None) -> datetime:
    if now is None:
        moment = datetime.now(timezone.utc)
    elif isinstance(now, datetime):
        moment = now
    else:
        parsed = parse_timestamp(now)
        if parsed is None:
            raise ValueError(f"Invalid idempotency timestamp: {now}")
        moment = parsed
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0)


def _format(moment: datetime) -> str:
    return moment.isoformat()


def _encode_response(response: dict[str, object]) -> str:
    return _canonical_json(response)


def _decode_response(raw: object) -> dict[str, object]:
    try:
        decoded = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    if isinstance(decoded, dict):
        return cast(dict[str, object], decoded)
    return {}


def _record_from_row(row: sqlite3.Row) -> IdempotencyRecord:
    return IdempotencyRecord(
        key=str(row["key"]),
        method=str(row["method"]),
        request_hash=str(row["request_hash"]),
        status=int(row["status"]),
        response=_decode_response(row["response"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
    )


def get_record(connection: sqlite3.Connection, key: str) -> IdempotencyRecord | None:
    """Return the record for ``key``, including records awaiting pruning."""
    row = connection.execute(
        "SELECT key, method, request_hash, status, response, created_at, expires_at "
        "FROM idempotency_keys WHERE key = ?",
        (key,),
    ).fetchone()
    return _record_from_row(row) if row is not None else None


def put_record(
    connection: sqlite3.Connection,
    *,
    key: str,
    method: str,
    request_hash: str,
    status: int,
    response: dict[str, object],
    ttl_seconds: int = 86400,
    now: str | datetime | None = None,
) -> IdempotencyRecord:
    """Store or replace an idempotency record and return its stored form."""
    created = _to_datetime(now)
    expires = created + timedelta(seconds=ttl_seconds)
    created_at = _format(created)
    expires_at = _format(expires)
    encoded = _encode_response(response)
    with connection:
        connection.execute(
            "INSERT INTO idempotency_keys "
            "(key, method, request_hash, status, response, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "method = excluded.method, "
            "request_hash = excluded.request_hash, "
            "status = excluded.status, "
            "response = excluded.response, "
            "created_at = excluded.created_at, "
            "expires_at = excluded.expires_at",
            (key, method, request_hash, status, encoded, created_at, expires_at),
        )
    return IdempotencyRecord(
        key=key,
        method=method,
        request_hash=request_hash,
        status=status,
        response=dict(response),
        created_at=created_at,
        expires_at=expires_at,
    )


def prune_expired(connection: sqlite3.Connection, *, now: str | datetime | None = None) -> int:
    """Delete expired idempotency records and return how many were removed."""
    current = _format(_to_datetime(now))
    with connection:
        cursor = connection.execute(
            "DELETE FROM idempotency_keys WHERE datetime(expires_at) <= datetime(?)",
            (current,),
        )
    return max(0, int(cursor.rowcount))
