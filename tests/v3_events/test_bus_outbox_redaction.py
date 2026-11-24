"""Tests for event dispatch, outbox persistence, and redaction."""

from __future__ import annotations

import json

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityId, EntityKind
from redscribe.v3.events.bus import EventBus, EventBusError
from redscribe.v3.events.outbox import (
    JsonFileOutbox,
    MemoryOutbox,
    OutboxWriter,
)
from redscribe.v3.events.redaction import (
    RedactionPolicy,
    is_sensitive_key,
    redact_payload,
    redact_text,
)
from redscribe.v3.events.types import DomainEvent, EventRecord, EventSeverity, make_event


def test_domain_event_validation_and_dict() -> None:
    subject = EntityId(EntityKind.FINDING, "f-1")
    event = make_event("finding.created", subject, title="SQLi", severity="info")
    assert event.subject_ref == "finding:f-1"
    assert event.payload["title"] == "SQLi"
    assert event.as_dict()["kind"] == "finding.created"
    with pytest.raises(ValueError):
        DomainEvent(kind="")
    with pytest.raises(ValueError):
        DomainEvent(kind="a", actor="")


def test_event_severity_rank() -> None:
    assert EventSeverity.TRACE.rank < EventSeverity.INFO.rank
    assert EventSeverity.CRITICAL.rank == 4
    assert EventSeverity("warning") is EventSeverity.WARNING


def test_event_record_validation() -> None:
    event = DomainEvent(kind="note.created")
    record = EventRecord(sequence=1, event=event, timestamp=1.0, request_id="req_1")
    assert record.kind == "note.created"
    assert record.subject_ref == ""
    assert record.as_dict()["request_id"] == "req_1"
    with pytest.raises(ValueError):
        EventRecord(sequence=0, event=event, timestamp=0.0)


def test_event_bus_dispatch_and_sequence() -> None:
    bus = EventBus(clock=FixedClock(start=10.0, step=1.0))
    seen: list[str] = []
    bus.subscribe("note.created", lambda record: seen.append(record.kind))
    bus.subscribe_all(lambda record: seen.append("all"))
    first = bus.publish(make_event("note.created"), request_id="req_1")
    second = bus.publish(make_event("note.updated"))
    assert first.sequence == 1
    assert second.sequence == 2
    assert first.timestamp == 10.0
    assert second.timestamp == 11.0
    assert seen == ["note.created", "all", "all"]
    assert bus.last() == second
    assert bus.size() == 2


def test_event_bus_isolates_subscriber_failures() -> None:
    bus = EventBus()

    def broken(record: EventRecord) -> None:
        raise RuntimeError("boom")

    bus.subscribe("x", broken)
    bus.subscribe("x", lambda record: None)
    bus.publish(DomainEvent(kind="x"))
    assert len(bus.errors()) == 1
    assert bus.errors()[0]["error_type"] == "RuntimeError"


def test_event_bus_unsubscribe_and_filters() -> None:
    bus = EventBus()
    seen: list[int] = []

    def callback(record: EventRecord) -> None:
        seen.append(record.sequence)

    bus.subscribe("a", callback)
    with pytest.raises(EventBusError):
        bus.subscribe("", callback)
    bus.publish(DomainEvent(kind="a"))
    assert bus.unsubscribe("a", callback) is True
    assert bus.unsubscribe("a", callback) is False
    bus.publish(DomainEvent(kind="a"))
    assert seen == [1]
    assert len(bus.of_kind("a")) == 2
    assert len(bus.records_since(1)) == 1


def test_event_bus_snapshot_and_clear() -> None:
    bus = EventBus()
    bus.publish(DomainEvent(kind="a"))
    snapshot = bus.snapshot()
    assert snapshot["sequence"] == 1
    assert len(snapshot["events"]) == 1
    bus.clear()
    assert bus.size() == 0
    assert bus.last() is None


def test_memory_outbox_and_writer() -> None:
    outbox = MemoryOutbox()
    writer = OutboxWriter(outbox)
    record = EventRecord(sequence=1, event=DomainEvent(kind="a"), timestamp=1.0)
    assert writer.write(record) is True
    assert writer.write(record) is False
    assert writer.contains(1) is True
    assert outbox.checkpoint() == 1
    assert writer.checkpoint() == 1
    assert writer.write_many((record,)) == 0
    outbox.clear()
    assert outbox.all() == ()


def test_json_file_outbox_roundtrip(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "events.jsonl"
    outbox = JsonFileOutbox(path)
    event = DomainEvent(
        kind="finding.created",
        subject=EntityId(EntityKind.FINDING, "f-1"),
        payload={"title": "SQLi"},
    )
    outbox.append(EventRecord(sequence=1, event=event, timestamp=1.0))
    outbox.append(EventRecord(sequence=2, event=DomainEvent(kind="note.created"), timestamp=2.0))
    records = outbox.all()
    assert len(records) == 2
    assert records[0].event.subject_ref == "finding:f-1"
    assert records[0].event.payload["title"] == "SQLi"
    assert outbox.checkpoint() == 2
    path.write_text('{"bad": true}\n' + path.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(outbox.all()) == 2


def test_sensitive_key_detection() -> None:
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("Authorization")
    assert is_sensitive_key("private-key")
    assert not is_sensitive_key("title")


def test_redact_text_shapes() -> None:
    redacted = redact_text("mail alice@example.com with flag{secret} using Bearer abc123")
    assert "alice@example.com" not in redacted
    assert "flag{secret}" not in redacted
    assert "abc123" not in redacted
    assert "[email]" in redacted


def test_redact_payload_recursive() -> None:
    payload = {
        "title": "Report",
        "token": "abc",
        "nested": {"password": "hunter2", "note": "user@example.com"},
        "items": [{"secret": "x"}, "ok"],
    }
    result = redact_payload(payload)
    assert result["token"] == "[redacted]"
    assert result["nested"]["password"] == "[redacted]"
    assert result["nested"]["note"] == "[email]"
    assert result["items"][0]["secret"] == "[redacted]"
    assert result["items"][1] == "ok"
    assert payload["token"] == "abc"


def test_redaction_policy() -> None:
    policy = RedactionPolicy(extra_keys=("internal_id",))
    assert policy.enabled is True
    result = policy.apply({"title": "x", "internal_id": "abc", "token": "t"})
    assert result["internal_id"] == "[redacted]"
    disabled = RedactionPolicy(enabled=False)
    assert disabled.apply({"token": "t"}) == {"token": "t"}


def test_json_outbox_line_format(tmp_path: object) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "outbox.jsonl"
    outbox = JsonFileOutbox(path)
    outbox.append(EventRecord(sequence=1, event=DomainEvent(kind="a"), timestamp=1.0))
    line = path.read_text(encoding="utf-8").strip()
    assert json.loads(line)["kind"] == "a"
