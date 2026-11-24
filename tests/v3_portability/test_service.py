"""End-to-end tests for the portability service facade."""

from __future__ import annotations

import base64

import pytest

from redscribe.v3.capabilities import Capabilities, CapabilityError
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityId, EntityLink, LinkKind
from redscribe.v3.events.bus import EventBus
from redscribe.v3.portability.errors import (
    DecryptionError,
    DeviceError,
    PortabilityError,
    TransferError,
)
from redscribe.v3.portability.service import PortabilityService
from tests.v3_portability.conftest import TEST_PASSPHRASE, make_entity


def service(clock: FixedClock | None = None, bus: EventBus | None = None) -> PortabilityService:
    """Build a test service with a cheap KDF."""
    return PortabilityService(
        clock=clock or FixedClock(1_700_000_000.0),
        bus=bus,
        kdf_iterations=1_000,
    )


def test_health_reports_capabilities_and_catalogs() -> None:
    api = service()
    health = api.health()
    assert health["available"]
    assert "field_both_edited" in health["reason_codes"]
    assert "keep_local" in health["strategies"]
    assert health["ledger_intact"]
    assert health["bundles"] == 0


def test_weak_passphrase_rejected() -> None:
    api = service()
    with pytest.raises(PortabilityError, match="Passphrase is too weak"):
        api.create_bundle((make_entity("note:1"),), passphrase="short")


def test_device_registration_and_trust() -> None:
    api = service()
    api.register_device("beta", "Beta desktop", platform="desktop")
    registered = next(item for item in api.devices()["devices"] if item["device_id"] == "beta")
    assert not registered["trusted"]
    with pytest.raises(DeviceError):
        api.create_bundle((make_entity("note:1"),), passphrase=TEST_PASSPHRASE, device_id="beta")
    api.trust_device("beta")
    assert api.devices()["trusted"] == ["beta", "local"]
    created = api.create_bundle(
        (make_entity("note:1"),), passphrase=TEST_PASSPHRASE, device_id="beta"
    )
    assert created["source_device"] == "beta"


def test_bundle_create_inspect_verify_and_receipt() -> None:
    api = service()
    entity = make_entity("note:1", title="Secret title")
    link = EntityLink(EntityId.parse("note:1"), EntityId.parse("finding:1"), LinkKind.RELATES)
    created = api.create_bundle(
        (entity, make_entity("finding:1")), (link,), passphrase=TEST_PASSPHRASE
    )
    assert created["sealed"]
    assert created["entity_count"] == 2
    inspected = api.inspect_bundle(created["bundle_id"])
    assert inspected["bundle_id"] == created["bundle_id"]
    verified = api.verify_bundle(created["bundle_id"], TEST_PASSPHRASE)
    assert verified["receipt"]["ok"]
    assert verified["origin_trusted"]
    receipt_id = verified["receipt"]["receipt_id"]
    assert api.receipt(receipt_id)["bundle_id"] == created["bundle_id"]
    assert api.receipts()["count"] == 1


def test_verify_wrong_passphrase_does_not_create_receipt() -> None:
    api = service()
    created = api.create_bundle((make_entity("note:1"),), passphrase=TEST_PASSPHRASE)
    with pytest.raises(DecryptionError):
        api.verify_bundle(created["bundle_id"], "Wrong-Passphrase-42")
    assert api.receipts()["count"] == 0


def test_compare_vectors_relation_and_merge() -> None:
    api = service()
    result = api.compare_vectors({"alpha": 2, "beta": 1}, {"alpha": 1, "gamma": 3})
    assert result["relation"] == "concurrent"
    assert result["concurrent"]
    assert result["merged"] == {"alpha": 2, "beta": 1, "gamma": 3}
    assert result["distance"] == 5
    assert result["changed_devices"] == ["alpha", "beta", "gamma"]


def test_detect_conflicts_reports_reason_codes() -> None:
    api = service()
    base = make_entity("note:1", title="Base")
    local = base.apply_fields({"title": "Local"}, vector=base.vector.bump("alpha"))
    remote = base.apply_fields({"title": "Remote"}, vector=base.vector.bump("beta"))
    report = api.detect_conflicts((base,), (local,), (remote,))
    assert report["count"] == 1
    assert report["reasons"] == ["field_both_edited"]
    assert "note:1" in report["groups"] or report["conflicts"][0]["ref"] == "note:1"


def test_two_independently_edited_vaults_merge_with_auditable_resolution() -> None:
    bus = EventBus()
    api = service(bus=bus)
    base = make_entity("note:1", title="Base", body="base")
    local = base.apply_fields({"title": "Local"}, vector=base.vector.bump("alpha"))
    remote = base.apply_fields({"title": "Remote"}, vector=base.vector.bump("beta"))
    created = api.create_bundle((remote,), passphrase=TEST_PASSPHRASE, device_id="local")
    preview = api.preview_import(created["bundle_id"], TEST_PASSPHRASE, (base,), (local,))
    assert not preview["valid"]
    assert preview["conflicts"][0]["reason"] == "field_both_edited"
    preview_id = preview["preview_id"]
    resolved = api.resolve_preview(
        preview_id,
        {"note:1": "keep_local"},
        actor="alice",
        device="alpha",
    )
    assert resolved["merge"]["conflicts"] == []
    assert resolved["merge"]["entities"][0]["record"]["title"] == "Local"
    assert resolved["ledger_intact"]
    assert resolved["receipt"]["ok"]
    assert len(api.audit()["resolutions"]["entries"]) == 1
    assert len(bus.of_kind("portability.merge.completed")) == 1


def test_preview_import_can_filter_by_family() -> None:
    api = service()
    note = make_entity("note:1")
    finding = make_entity("finding:1")
    created = api.create_bundle((note, finding), passphrase=TEST_PASSPHRASE)
    preview = api.preview_import(
        created["bundle_id"], TEST_PASSPHRASE, (note, finding), (note, finding), families=("note",)
    )
    assert [change["ref"] for change in preview["changes"]] == ["note:1"]


def test_transfer_lifecycle_through_service() -> None:
    api = service()
    created = api.create_bundle((make_entity("note:1"),), passphrase=TEST_PASSPHRASE)
    started = api.begin_transfer(created["bundle_id"], chunk_size=128)
    transfer_id = started["transfer_id"]
    assert started["state"] == "active"
    assert api.pause_transfer(transfer_id)["state"] == "paused"
    resumed = api.resume_transfer(transfer_id)
    assert resumed["state"] == "active"
    raw = api._bundles[created["bundle_id"]].to_bytes()
    for index in range(started["total_chunks"]):
        chunk = raw[index * 128 : (index + 1) * 128]
        status = api.push_chunk(transfer_id, index, base64.b64encode(chunk).decode("ascii"))
        assert status["received_chunks"] == index + 1
    finished = api.finish_transfer(transfer_id)
    assert finished["status"] == "complete"
    assert finished["bundle"] == created["bundle_id"]


def test_transfer_checkpoint_and_cancel() -> None:
    api = service()
    created = api.create_bundle((make_entity("note:1"),), passphrase=TEST_PASSPHRASE)
    started = api.begin_transfer(created["bundle_id"], chunk_size=64)
    checkpoint = api.transfer_checkpoint(started["transfer_id"])
    assert checkpoint["resumable"]
    assert api.cancel_transfer(started["transfer_id"])["state"] == "cancelled"
    with pytest.raises(TransferError):
        api.resume_transfer(started["transfer_id"])


def test_audit_events_are_redacted() -> None:
    api = service()
    api._emit(
        "portability.test.event",
        {"token": "super-secret-token", "note": "flag{do-not-leak}"},
    )
    events = api.audit()["events"]
    assert events[0]["token"] == "[redacted]"
    assert "do-not-leak" not in str(events)
    assert events[0]["kind"] == "portability.test.event"


def test_capability_gate_blocks_operations() -> None:
    api = PortabilityService(capabilities=Capabilities(enabled=frozenset()), kdf_iterations=1_000)
    with pytest.raises(CapabilityError):
        api.create_bundle((make_entity("note:1"),), passphrase=TEST_PASSPHRASE)
    with pytest.raises(CapabilityError):
        api.plan_bundle((make_entity("note:1"),))


def test_bus_events_record_bundle_and_receipt() -> None:
    bus = EventBus()
    api = service(bus=bus)
    created = api.create_bundle((make_entity("note:1"),), passphrase=TEST_PASSPHRASE)
    api.verify_bundle(created["bundle_id"], TEST_PASSPHRASE)
    snapshot = api.bus_snapshot()
    assert snapshot["sequence"] >= 2
    assert [item["kind"] for item in bus_snapshot_events(snapshot)] == [
        "portability.bundle.created",
        "portability.bundle.verified",
    ]


def bus_snapshot_events(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Extract event dictionaries from a bus snapshot."""
    return [dict(item) for item in snapshot["events"]]  # type: ignore[union-attr]
