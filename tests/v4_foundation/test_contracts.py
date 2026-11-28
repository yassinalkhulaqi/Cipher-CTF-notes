from __future__ import annotations

import pytest

from redscribe.v4.api_v4 import RouteRegistry, global_registry, register_routes
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    EntityKind,
    EntityLink,
    EntityRef,
    EnvelopeDecoder,
    ErrorCode,
    PageMeta,
    fail,
    is_entity_id,
    new_entity_id,
    ok,
)
from redscribe.v4.events import (
    DomainEvent,
    EventBus,
    EventKind,
    InMemoryOutbox,
    default_redactor,
    event_from_dataclass,
    utc_now,
)


def test_entity_kind_parse_and_label() -> None:
    assert EntityKind.parse(" finding ") is EntityKind.FINDING
    assert EntityKind.FINDING.label == "Finding"
    with pytest.raises(ValueError):
        EntityKind.parse("unknown")


def test_entity_id_generation_and_validation() -> None:
    value = new_entity_id()
    assert is_entity_id(value)
    assert not is_entity_id("not-an-id")


def test_entity_ref_round_trip() -> None:
    ref = EntityRef(kind=EntityKind.FINDING, id=new_entity_id(), label="SQLi")
    data = ref.to_dict()
    assert EntityRef.from_dict(data) == ref
    with pytest.raises(ValueError):
        EntityRef(kind=EntityKind.NOTE, id="bad")


def test_entity_link_validation() -> None:
    source = EntityRef(kind=EntityKind.FINDING, id=new_entity_id())
    target = EntityRef(kind=EntityKind.EVIDENCE, id=new_entity_id())
    link = EntityLink(source=source, target=target, relation="proven_by", weight=0.8)
    assert link.to_dict()["relation"] == "proven_by"
    with pytest.raises(ValueError):
        EntityLink(source=source, target=target, relation="Bad Relation")
    with pytest.raises(ValueError):
        EntityLink(source=source, target=target, relation="ok", weight=2.0)


def test_envelope_success_and_failure() -> None:
    meta = PageMeta(request_id="r1", page=2, page_size=25, etag="etag-1")
    envelope = ok({"x": 1}, meta)
    assert envelope["data"] == {"x": 1}
    assert envelope["meta"]["page"] == 2
    decoder = EnvelopeDecoder()
    assert decoder.decode(envelope) == {"x": 1}
    error = ApiError(ErrorCode.NOT_FOUND, "missing", ("id",))
    assert fail(error)["error"]["code"] == "not_found"
    with pytest.raises(ApiError):
        decoder.decode(fail(error))
    with pytest.raises(ValueError):
        PageMeta(request_id="r", page=0)


def test_envelope_version_conflict() -> None:
    meta = PageMeta(request_id="r1", version="v3")
    with pytest.raises(ApiError) as exc:
        EnvelopeDecoder("v4").decode(ok({}, meta))
    assert exc.value.code is ErrorCode.CONFLICT


def test_capability_set() -> None:
    caps = CapabilitySet(frozenset({Capability.READ}))
    assert caps.allows(Capability.READ)
    caps.require(Capability.READ)
    with pytest.raises(ApiError) as exc:
        caps.require(Capability.WRITE)
    assert exc.value.code is ErrorCode.FORBIDDEN
    assert CapabilitySet.full().allows(Capability.ADMIN)


def test_error_status_codes() -> None:
    assert ErrorCode.NOT_FOUND.http_status == 404
    assert ErrorCode.INVALID_INPUT.http_status == 400
    assert ErrorCode.CONFLICT.http_status == 409
    assert str(ApiError(ErrorCode.INTERNAL, "boom")) == "internal: boom"


def test_timestamp_format() -> None:
    stamp = utc_now()
    assert stamp.endswith("Z")
    assert "T" in stamp


def test_domain_event_round_trip() -> None:
    event = DomainEvent(
        kind=EventKind.FINDING_CREATED,
        aggregate_id=new_entity_id(),
        aggregate_kind=EntityKind.FINDING,
        payload={"title": "SQLi"},
    )
    data = event.to_dict()
    assert DomainEvent.from_dict(data) == event
    with pytest.raises(ValueError):
        DomainEvent(
            kind=EventKind.CAPTURE_CREATED, aggregate_id="", aggregate_kind=EntityKind.CAPTURE
        )


def test_default_redactor_strips_secrets() -> None:
    payload = {"title": "note", "password": "hunter2", "nested": {"token": "abc", "n": 1}}
    redacted = default_redactor(payload)
    assert redacted["password"] == "[redacted]"
    assert redacted["nested"]["token"] == "[redacted]"
    assert redacted["nested"]["n"] == 1


def test_event_bus_subscribers_and_isolation() -> None:
    bus = EventBus()
    seen: list[DomainEvent] = []

    def good(event: DomainEvent) -> None:
        seen.append(event)

    def bad(event: DomainEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe(EventKind.CAPTURE_CREATED, good)
    bus.subscribe(EventKind.CAPTURE_CREATED, bad)
    event = DomainEvent(
        kind=EventKind.CAPTURE_CREATED,
        aggregate_id=new_entity_id(),
        aggregate_kind=EntityKind.CAPTURE,
    )
    with pytest.raises(RuntimeError):
        bus.publish(event)
    assert bus.subscriber_count(EventKind.CAPTURE_CREATED) == 2
    bus.unsubscribe(EventKind.CAPTURE_CREATED, bad)
    bus.publish(event)
    assert len(seen) == 2


def test_outbox_caps_and_replays() -> None:
    outbox = InMemoryOutbox(capacity=2)
    for index in range(5):
        outbox.append(
            DomainEvent(
                kind=EventKind.RUN_STARTED,
                aggregate_id=new_entity_id(),
                aggregate_kind=EntityKind.RUN,
                payload={"index": index, "secret": "hide"},
            )
        )
    assert len(outbox.records()) == 2
    replayed = outbox.replay(EventKind.RUN_STARTED)
    assert len(replayed) == 2
    assert replayed[0].payload["secret"] == "[redacted]"
    outbox.clear()
    assert outbox.records() == []


def test_event_from_dataclass() -> None:
    from dataclasses import dataclass

    @dataclass
    class Payload:
        value: int

    event = event_from_dataclass(
        EventKind.QUERY_SAVED, new_entity_id(), EntityKind.QUERY, Payload(7)
    )
    assert event.payload == {"value": 7}
    with pytest.raises(TypeError):
        event_from_dataclass(EventKind.QUERY_SAVED, "id", EntityKind.QUERY, 1)


def test_route_registry_is_additive() -> None:
    registry = RouteRegistry()
    route = registry.register("inbox", "Inbox")
    assert route.full_path == "/api/v4/inbox"
    assert len(registry) == 1
    assert registry.get("/api/v4/inbox") == route
    assert registry.serialize()[0]["name"] == "Inbox"
    with pytest.raises(ValueError):
        registry.register("inbox", "duplicate")
    with pytest.raises(ValueError):
        registry.register("Bad Route", "bad")


def test_global_registry_helper() -> None:
    before = len(global_registry())
    register_routes("kernel-test", "Kernel Test")
    assert len(global_registry()) == before + 1
