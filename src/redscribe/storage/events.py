"""Append-only entity events and request audit records."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from redscribe.domain.utils import utc_now


@dataclass(frozen=True, slots=True)
class EntityEvent:
    """One persisted entity change event."""

    id: int
    kind: str
    entity_type: str
    entity_id: int | None
    action: str
    payload: str
    request_id: str
    created_at: str

    def as_dict(self) -> dict[str, object]:
        """Return the event with its payload decoded from JSON."""
        try:
            payload: object = json.loads(self.payload)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return {
            "id": self.id,
            "kind": self.kind,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "payload": payload,
            "request_id": self.request_id,
            "created_at": self.created_at,
        }


def _timestamp(now: str | datetime | None) -> str:
    if now is None:
        return utc_now()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    return now


def _encode_payload(payload: object | None) -> str:
    value = {} if payload is None else payload
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _event_from_row(row: sqlite3.Row) -> EntityEvent:
    entity_id = row["entity_id"]
    return EntityEvent(
        id=int(row["id"]),
        kind=str(row["kind"]),
        entity_type=str(row["entity_type"]),
        entity_id=int(entity_id) if entity_id is not None else None,
        action=str(row["action"]),
        payload=str(row["payload"]),
        request_id=str(row["request_id"]),
        created_at=str(row["created_at"]),
    )


def record_event(
    connection: sqlite3.Connection,
    *,
    kind: str,
    entity_type: str,
    entity_id: int | None = None,
    action: str,
    payload: object | None = None,
    request_id: str = "",
    now: str | datetime | None = None,
) -> EntityEvent:
    """Persist one entity event and return its stored representation."""
    created_at = _timestamp(now)
    encoded = _encode_payload(payload)
    with connection:
        cursor = connection.execute(
            "INSERT INTO entity_events "
            "(kind, entity_type, entity_id, action, payload, request_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, entity_type, entity_id, action, encoded, request_id, created_at),
        )
    return EntityEvent(
        id=int(cast(int, cursor.lastrowid)),
        kind=kind,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        payload=encoded,
        request_id=request_id,
        created_at=created_at,
    )


def list_events(
    connection: sqlite3.Connection,
    *,
    since_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    limit: int = 100,
) -> list[EntityEvent]:
    """Return events in append order, optionally after a cursor and filtered."""
    clauses: list[str] = []
    parameters: list[object] = []
    if since_id is not None:
        clauses.append("id > ?")
        parameters.append(since_id)
    if entity_type is not None:
        clauses.append("entity_type = ?")
        parameters.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        parameters.append(entity_id)
    query = "SELECT * FROM entity_events"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id ASC LIMIT ?"
    parameters.append(limit)
    rows = connection.execute(query, parameters).fetchall()
    return [_event_from_row(row) for row in rows]


def record_request_audit(
    connection: sqlite3.Connection,
    *,
    request_id: str,
    method: str,
    path: str,
    outcome: str,
    duration_ms: float = 0.0,
    client: str = "",
    now: str | datetime | None = None,
) -> None:
    """Persist one request audit row."""
    created_at = _timestamp(now)
    with connection:
        connection.execute(
            "INSERT INTO request_audit "
            "(request_id, method, path, outcome, duration_ms, client, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, method, path, outcome, duration_ms, client, created_at),
        )


def list_request_audit(
    connection: sqlite3.Connection, *, limit: int = 100
) -> list[dict[str, object]]:
    """Return the most recent request audit rows first."""
    rows = connection.execute(
        "SELECT id, request_id, method, path, outcome, duration_ms, client, created_at "
        "FROM request_audit ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "request_id": str(row["request_id"]),
            "method": str(row["method"]),
            "path": str(row["path"]),
            "outcome": str(row["outcome"]),
            "duration_ms": float(row["duration_ms"]),
            "client": str(row["client"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]
