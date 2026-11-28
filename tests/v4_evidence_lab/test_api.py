"""API envelope, pagination, capability, and event tests for evidence lab."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.clock import Clock
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    EnvelopeDecoder,
    ErrorCode,
    new_entity_id,
)
from redscribe.v4.events import DomainEvent, EventBus, EventKind, InMemoryOutbox
from redscribe.v4.evidence_lab.api import (
    EvidenceApi,
    EvidenceRequest,
    decode_bytes_hex,
    handle_get,
    handle_post,
    register,
)
from redscribe.v4.evidence_lab.service import CustodyGraph, HashVerifier, HexDumper
from redscribe.v4.evidence_lab.storage import StoreError
from redscribe.v4.evidence_lab.types import EvidenceRecord, HashAlgorithm
from redscribe.v4.pagination import Cursor, weak_etag

FROZEN = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
SHA256_A = "a" * 64
SHA256_B = "b" * 64
IDENTIFIER = "11111111-1111-1111-1111-111111111111"


def make_api() -> tuple[EvidenceApi, EventBus, InMemoryOutbox, Clock]:
    clock = Clock(frozen_at=FROZEN)
    outbox = InMemoryOutbox()
    bus = EventBus(outbox=outbox)
    api = EvidenceApi(bus=bus, clock=clock)
    return api, bus, outbox, clock


def make_request(
    method: str = "GET",
    path: str = "/evidence",
    query: dict[str, object] | None = None,
    body: dict[str, object] | None = None,
    capabilities: CapabilitySet | None = None,
    feature_gate: FeatureGate | None = None,
) -> EvidenceRequest:
    return EvidenceRequest(
        method=method,
        path=path,
        query=query or {},
        body=body or {},
        capabilities=capabilities or CapabilitySet.full(),
        request_id="req-fixed",
        feature_gate=feature_gate,
    )


def seed(api: EvidenceApi, name: str = "disk.img", digest: str = SHA256_A) -> EvidenceRecord:
    return api.store.add(EvidenceRecord("ev-1", name, 10, digest, "2024-05-01T12:00:00.000Z"))


def digest_of(text: str) -> str:
    return HashVerifier().compute(text.encode(), HashAlgorithm.SHA256)


def expect_api_error(action: Callable[[], object], message: str) -> ApiError:
    captured: ApiError | None = None
    try:
        action()
    except ApiError as exc:
        captured = exc
    if captured is None:
        pytest.fail(f"expected ApiError containing {message!r}")
    assert message in str(captured)
    return captured


def test_evidence_request_helpers() -> None:
    request = make_request(
        query={"page": 2, "tag": "Disk"},
        body={"name": "x"},
        capabilities=CapabilitySet(frozenset({Capability.READ})),
    )
    assert request.param("tag") == "Disk"
    assert request.param("missing", "fallback") == "fallback"
    assert request.request_id == "req-fixed"
    assert request.method == "GET"
    request.require(Capability.READ)
    expect_api_error(lambda: request.require(Capability.WRITE), "missing capability: write")


def test_decode_bytes_hex_validation() -> None:
    assert decode_bytes_hex("41 42") == b"AB"
    assert decode_bytes_hex(None) == b""
    expect_api_error(lambda: decode_bytes_hex("abc"), "odd length")
    expect_api_error(lambda: decode_bytes_hex("zz"), "not hexadecimal")
    expect_api_error(lambda: decode_bytes_hex("41" * 65537), "exceeds lab limit")


def test_list_evidence_empty_envelope() -> None:
    api, _, _, _ = make_api()
    envelope = api.list_evidence(make_request())
    assert "data" in envelope
    assert "meta" in envelope
    assert envelope["meta"]["version"] == "v4"
    assert envelope["meta"]["request_id"] == "req-fixed"
    assert envelope["meta"]["etag"]
    assert envelope["data"]["total"] == 0
    assert envelope["data"]["items"] == []
    assert envelope["data"]["not_modified"] is False
    assert EnvelopeDecoder().decode(envelope)["total"] == 0


def test_list_evidence_pagination_and_cursor() -> None:
    api, _, _, _ = make_api()
    for index in range(5):
        api.store.add(
            EvidenceRecord(
                f"ev-{index:02d}", f"item-{index:02d}.bin", 1, SHA256_A, "t", ("triage",)
            )
        )
    first = api.list_evidence(make_request(query={"page": 1, "page_size": 2}))
    assert first["data"]["total"] == 5
    assert len(first["data"]["items"]) == 2
    assert first["data"]["next_cursor"]
    assert first["meta"]["page_size"] == 2
    cursor = first["data"]["next_cursor"]
    assert Cursor.decode(cursor).offset == 2
    second = api.list_evidence(make_request(query={"page": 1, "page_size": 2, "cursor": cursor}))
    assert second["data"]["items"][0]["id"] == "ev-02"
    assert api.list_evidence(make_request(query={"tag": "triage"}))["data"]["total"] == 5
    assert api.list_evidence(make_request(query={"tag": "missing"}))["data"]["total"] == 0


def test_list_evidence_etag_not_modified() -> None:
    api, _, _, _ = make_api()
    seed(api)
    first = api.list_evidence(make_request())
    etag = first["meta"]["etag"]
    second = api.list_evidence(make_request(query={"if_none_match": etag}))
    assert second["data"]["not_modified"] is True
    assert second["data"]["items"] == []
    assert weak_etag("x") != weak_etag("y")


def test_list_evidence_invalid_pagination_envelope() -> None:
    api, _, _, _ = make_api()
    for query in ({"page": 0}, {"page_size": 0}, {"page_size": 501}, {"page": "abc"}):
        envelope = api.dispatch(make_request(query=query))
        assert envelope["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_list_evidence_requires_read_capability() -> None:
    api, _, _, _ = make_api()
    limited = CapabilitySet(frozenset({Capability.WRITE}))
    envelope = api.dispatch(make_request(capabilities=limited))
    assert envelope["error"]["code"] == ErrorCode.FORBIDDEN.value
    assert "feature disabled" in envelope["error"]["message"]


def test_list_evidence_requires_read_after_gate_satisfied() -> None:
    api, _, _, _ = make_api()
    gate = FeatureGate(CapabilitySet.full())
    limited = CapabilitySet(frozenset({Capability.EXPORT}))
    envelope = api.dispatch(make_request(capabilities=limited, feature_gate=gate))
    assert envelope["error"]["code"] == ErrorCode.FORBIDDEN.value
    assert "missing capability: read" in envelope["error"]["message"]


def test_create_evidence_emits_events() -> None:
    api, bus, outbox, _ = make_api()
    seen: list[DomainEvent] = []
    subscriber: Callable[[DomainEvent], None] = seen.append
    bus.subscribe(EventKind.EVIDENCE_ADDED, subscriber)
    bus.subscribe(EventKind.EVIDENCE_HASHED, subscriber)
    digest = digest_of("hello")
    envelope = api.create_evidence(
        make_request(
            method="POST",
            body={
                "id": IDENTIFIER,
                "name": "hello.bin",
                "size": 5,
                "sha256": digest,
                "bytes_hex": "68 65 6c 6c 6f",
                "tags": ["Disk", "disk"],
            },
        )
    )
    assert "data" in envelope
    assert envelope["data"]["evidence"]["id"] == IDENTIFIER
    assert envelope["data"]["evidence"]["tags"] == ["disk"]
    assert envelope["data"]["verification"]["matches"] is True
    assert len(seen) == 3
    assert seen[0].kind is EventKind.EVIDENCE_ADDED
    assert seen[0].aggregate_kind.value == "evidence"
    assert all(event.aggregate_id == IDENTIFIER for event in seen)
    assert len(outbox.records(EventKind.EVIDENCE_HASHED)) == 2
    assert api.store.contains(IDENTIFIER)


def test_create_evidence_without_payload_computes_digest() -> None:
    api, _, _, _ = make_api()
    request = make_request(
        method="POST",
        body={"name": "empty.bin", "size": 0, "sha256": SHA256_B, "acquired_at": "fixed"},
    )
    envelope = api.create_evidence(request)
    assert "verification" not in envelope["data"]
    assert envelope["data"]["evidence"]["acquired_at"] == "fixed"
    assert envelope["data"]["evidence"]["sha256"] == SHA256_B


def test_create_evidence_requires_write_capability() -> None:
    api, _, _, _ = make_api()
    limited = CapabilitySet(frozenset({Capability.READ}))
    gate = FeatureGate(CapabilitySet.full())
    envelope = api.dispatch(
        make_request(
            method="POST",
            body={"name": "x", "size": 1, "sha256": SHA256_A},
            capabilities=limited,
            feature_gate=gate,
        )
    )
    assert envelope["error"]["code"] == ErrorCode.FORBIDDEN.value
    assert "missing capability: write" in envelope["error"]["message"]
    assert len(api.store) == 0


def test_create_evidence_conflict_and_validation_errors() -> None:
    api, _, _, _ = make_api()
    seed(api)
    conflict = api.dispatch(
        make_request(method="POST", body={"id": "ev-1", "name": "x", "size": 1, "sha256": SHA256_A})
    )
    assert conflict["error"]["code"] == ErrorCode.CONFLICT.value
    cases: list[dict[str, object]] = [
        {"name": " ", "size": 1, "sha256": SHA256_A},
        {"name": "x", "size": -1, "sha256": SHA256_A},
        {"name": "x", "size": 1, "sha256": "bad"},
        {"name": "x", "size": 1, "sha256": SHA256_A, "tags": ["bad tag"]},
        {"name": "x", "size": 1, "sha256": SHA256_A, "bytes_hex": "0"},
        {"name": "x", "size": 1, "sha256": SHA256_A, "bytes_hex": "zz"},
    ]
    for body in cases:
        envelope = api.dispatch(make_request(method="POST", body=body))
        assert envelope["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_get_evidence_and_missing() -> None:
    api, _, _, _ = make_api()
    seed(api)
    found = api.get_evidence(make_request(), "ev-1")
    assert found["data"]["name"] == "disk.img"
    assert found["meta"]["etag"]
    missing = api.dispatch(make_request(path="/evidence/does-not-exist"))
    assert missing["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert "evidence not found" in missing["error"]["message"]


def test_inspect_uses_cached_result() -> None:
    api, _, _, _ = make_api()
    record = seed(api)
    payload = b"hello world"
    record_with_digest = record.with_hash(digest_of("hello world"))
    api.store.put(record_with_digest)
    first = api.inspect(make_request(body={"bytes_hex": payload.hex()}), record.id)
    assert first["data"]["hex_rows"]
    assert first["data"]["strings"]
    assert first["data"]["summary"]["cells"] == 11
    assert first["data"]["verifications"][0]["matches"] is True
    assert api.store.inspection(record.id) is not None
    second = api.inspect(make_request(), record.id)
    assert second["data"]["hex_rows"] == first["data"]["hex_rows"]
    assert "not_modified" not in second["data"]


def test_inspect_max_rows_and_invalid_hex() -> None:
    api, _, _, _ = make_api()
    record = seed(api)
    envelope = api.dispatch(
        make_request(path=f"/evidence/{record.id}/inspect", query={"max_rows": 1})
    )
    assert envelope["data"]["summary"]["rows"] == 0
    api.store.invalidate(record.id)
    bad = api.dispatch(
        make_request(
            path=f"/evidence/{record.id}/inspect",
            body={"bytes_hex": "not-hex"},
        )
    )
    assert bad["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_custody_route_and_chain() -> None:
    api, _, _, _ = make_api()
    record = seed(api)
    api.store.record_custody(record.id, "alice", "acquired", "2024-05-01T12:00:00.000Z")
    api.store.record_custody(record.id, "bob", "transferred", "2024-05-01T12:05:00.000Z")
    envelope = api.custody(make_request(), record.id)
    assert envelope["data"]["verification"]["valid"] is True
    assert len(envelope["data"]["entries"]) == 2
    assert api.store.verify_custody(record.id)


def test_manifest_requires_export_capability() -> None:
    api, _, _, _ = make_api()
    seed(api)
    limited = CapabilitySet(frozenset({Capability.READ}))
    gate = FeatureGate(CapabilitySet.full())
    denied = api.dispatch(
        make_request(path="/evidence-manifest", capabilities=limited, feature_gate=gate)
    )
    assert denied["error"]["code"] == ErrorCode.FORBIDDEN.value
    allowed = api.manifest(make_request())
    assert allowed["data"]["schema"] == "redscribe.evidence-lab/v4"
    assert len(allowed["data"]["records"]) == 1
    assert "hash_index" in allowed["data"]


def test_dispatch_routes_and_unknown_paths() -> None:
    api, _, _, _ = make_api()
    record = seed(api)
    assert api.dispatch(make_request(method="GET", path="/evidence"))["data"]["total"] == 1
    assert api.dispatch(make_request(path=f"/evidence/{record.id}"))["data"]["name"] == "disk.img"
    assert api.dispatch(make_request(path=f"/evidence/{record.id}/inspect"))["data"]["evidence_id"]
    assert (
        api.dispatch(make_request(path=f"/evidence/{record.id}/custody"))["data"]["entries"] == []
    )
    assert api.dispatch(make_request(path="/evidence-manifest"))["data"]["schema"]
    unknown = api.dispatch(make_request(path="/other"))
    assert unknown["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert (
        api.dispatch(make_request(method="PUT", path="/evidence"))["error"]["code"] == "not_found"
    )


def test_dispatch_converts_domain_errors() -> None:
    api, _, _, _ = make_api()
    api.store.add(EvidenceRecord("ev-1", "x", 1, SHA256_A, "t"))
    api.store.cache_inspection(_inspection("ev-1"))
    envelope = api.dispatch(make_request(path="/evidence/ev-1/inspect"))
    assert "data" in envelope
    with pytest.raises(StoreError, match="evidence not found"):
        api.store.get("missing")


def _inspection(identifier: str) -> Any:
    from redscribe.v4.evidence_lab.types import InspectionResult

    return InspectionResult(evidence_id=identifier, generated_at="t")


def test_module_level_handlers_use_default_api() -> None:
    listing = handle_get(make_request())
    created = handle_post(
        make_request(
            method="POST",
            body={
                "id": new_entity_id(),
                "name": "global.bin",
                "size": 1,
                "sha256": SHA256_A,
            },
        )
    )
    assert listing["meta"]["version"] == "v4"
    assert "data" in created
    assert created["data"]["evidence"]["name"] == "global.bin"


def test_register_routes_is_idempotent() -> None:
    registry = RouteRegistry()
    register(registry)
    register(registry)
    paths = [route.full_path for route in registry.all()]
    assert paths == ["/api/v4/evidence", "/api/v4/evidence/create"]
    assert registry.get("/api/v4/evidence") is not None
    assert registry.get("/api/v4/evidence/create") is not None
    assert registry.serialize()[0]["name"] == "evidence-lab"


def test_register_without_registry_does_not_raise() -> None:
    register(object())
    assert FeatureFlag.EVIDENCE_LAB.value == "evidence_lab"
    assert EventKind.EVIDENCE_ADDED.value == "evidence.added"
    assert EventKind.EVIDENCE_HASHED.value == "evidence.hashed"
    assert CustodyGraph.genesis_hash("ev-1") == CustodyGraph.genesis_hash("ev-1")
    assert HexDumper().bytes_per_row == 16
