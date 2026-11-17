from __future__ import annotations

from pathlib import Path

from redscribe.storage.db import Vault
from redscribe.storage.events import (
    EntityEvent,
    list_events,
    list_request_audit,
    record_event,
    record_request_audit,
)


def test_event_payload_round_trip(vault: Vault) -> None:
    event = record_event(
        vault.connection,
        kind="note",
        entity_type="node",
        entity_id=7,
        action="created",
        payload={"b": 2, "a": 1},
        request_id="req-1",
        now="2026-01-01T00:00:00+00:00",
    )
    assert event.id > 0
    assert event.kind == "note"
    assert event.entity_type == "node"
    assert event.entity_id == 7
    assert event.action == "created"
    assert event.payload == '{"a": 1, "b": 2}'
    assert event.request_id == "req-1"
    assert event.created_at == "2026-01-01T00:00:00+00:00"
    assert event.as_dict() == {
        "id": event.id,
        "kind": "note",
        "entity_type": "node",
        "entity_id": 7,
        "action": "created",
        "payload": {"a": 1, "b": 2},
        "request_id": "req-1",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    assert list_events(vault.connection) == [event]


def test_event_payload_is_deterministic_and_defaults_to_empty(vault: Vault) -> None:
    first = record_event(
        vault.connection,
        kind="node",
        entity_type="note",
        action="first",
        payload={"z": 1, "a": 2},
    )
    second = record_event(
        vault.connection,
        kind="node",
        entity_type="note",
        action="second",
        payload={"a": 2, "z": 1},
    )
    defaulted = record_event(
        vault.connection,
        kind="node",
        entity_type="note",
        action="third",
    )
    assert first.payload == second.payload == '{"a": 2, "z": 1}'
    assert defaulted.payload == "{}"
    assert defaulted.as_dict()["payload"] == {}
    assert defaulted.request_id == ""


def test_as_dict_handles_invalid_payload() -> None:
    event = EntityEvent(
        id=1,
        kind="node",
        entity_type="note",
        entity_id=None,
        action="broken",
        payload="{not json",
        request_id="",
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert event.as_dict()["payload"] == {}


def test_list_events_orders_filters_and_limits(vault: Vault) -> None:
    first = record_event(
        vault.connection, kind="node", entity_type="note", entity_id=1, action="first"
    )
    second = record_event(
        vault.connection, kind="node", entity_type="target", entity_id=1, action="second"
    )
    third = record_event(
        vault.connection, kind="node", entity_type="note", entity_id=2, action="third"
    )

    assert [event.id for event in list_events(vault.connection)] == [
        first.id,
        second.id,
        third.id,
    ]
    assert [event.id for event in list_events(vault.connection, since_id=first.id)] == [
        second.id,
        third.id,
    ]
    assert [event.id for event in list_events(vault.connection, entity_type="note")] == [
        first.id,
        third.id,
    ]
    assert [
        event.id for event in list_events(vault.connection, entity_type="note", entity_id=2)
    ] == [third.id]
    assert [event.id for event in list_events(vault.connection, entity_id=1)] == [
        first.id,
        second.id,
    ]
    assert [event.id for event in list_events(vault.connection, limit=2)] == [
        first.id,
        second.id,
    ]
    assert list_events(vault.connection, limit=0) == []


def test_request_audit_round_trip(vault: Vault) -> None:
    record_request_audit(
        vault.connection,
        request_id="req-1",
        method="POST",
        path="/api/nodes",
        outcome="success",
        duration_ms=12.5,
        client="127.0.0.1",
        now="2026-01-01T00:00:00+00:00",
    )
    record_request_audit(
        vault.connection,
        request_id="req-2",
        method="GET",
        path="/api/nodes",
        outcome="not_found",
    )
    rows = list_request_audit(vault.connection)
    assert [row["request_id"] for row in rows] == ["req-2", "req-1"]
    assert rows[0] == {
        "id": rows[0]["id"],
        "request_id": "req-2",
        "method": "GET",
        "path": "/api/nodes",
        "outcome": "not_found",
        "duration_ms": 0.0,
        "client": "",
        "created_at": rows[0]["created_at"],
    }
    assert rows[1]["duration_ms"] == 12.5
    assert rows[1]["client"] == "127.0.0.1"
    assert list_request_audit(vault.connection, limit=1) == [rows[0]]


def test_vault_event_and_audit_wrappers_persist(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    with Vault(path) as vault:
        event = vault.record_event(
            kind="node",
            entity_type="note",
            entity_id=3,
            action="updated",
            payload={"title": "x"},
            request_id="req",
        )
        vault.record_request(
            request_id="req",
            method="PATCH",
            path="/api/nodes/3",
            outcome="success",
            duration_ms=4.5,
            client="tester",
        )
        assert vault.list_events()[0].id == event.id
        assert vault.list_request_audit()[0]["request_id"] == "req"

    with Vault(path) as reopened:
        events = reopened.list_events()
        assert len(events) == 1
        assert events[0].as_dict()["payload"] == {"title": "x"}
        audit = reopened.list_request_audit()
        assert len(audit) == 1
        assert audit[0]["duration_ms"] == 4.5
