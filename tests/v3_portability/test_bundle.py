"""Tests for encrypted portable bundle round-trips and tamper detection."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityId, EntityLink, LinkKind
from redscribe.v3.portability.bundle import (
    BundleHeader,
    BundlePayload,
    PortableBundle,
    create_bundle,
    open_bundle,
    read_bundle,
    write_bundle,
)
from redscribe.v3.portability.device import DeviceIdentity
from redscribe.v3.portability.errors import BundleError, DecryptionError, VerificationError
from tests.v3_portability.conftest import TEST_PASSPHRASE, make_entity

LINKS = (
    EntityLink(
        source=EntityId.parse("note:1"),
        target=EntityId.parse("finding:1"),
        kind=LinkKind.EVIDENCES,
        label="supports",
    ),
)


def build_bundle(device: DeviceIdentity, clock: FixedClock) -> PortableBundle:
    entities = (
        make_entity("note:1", title="Secret note", body="secret body", vector={"alpha": 2}),
        make_entity("finding:1", title="Finding", vector={"beta": 1}),
    )
    return create_bundle(
        entities,
        LINKS,
        device=device,
        passphrase=TEST_PASSPHRASE,
        clock=clock,
        iterations=1_000,
        metadata={"engagement": "test"},
    )


def test_bundle_round_trip_fidelity(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    payload = open_bundle(bundle, TEST_PASSPHRASE)
    assert payload.report.ok
    assert [entity.ref for entity in payload.entities] == ["finding:1", "note:1"]
    assert payload.entities[1].title == "Secret note"
    assert payload.entities[1].body == "secret body"
    assert payload.links == LINKS
    assert payload.manifest.metadata["engagement"] == "test"
    assert payload.counts()["families"] == 2


def test_bundle_bytes_are_encrypted(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    data = bundle.to_bytes()
    assert b"Secret note" not in data
    assert b"secret body" not in data
    assert data.startswith(b"{")
    assert bundle.size() == len(data)


def test_bundle_deserialization_round_trip(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    restored = PortableBundle.from_bytes(bundle.to_bytes())
    assert restored.as_dict() == bundle.as_dict()
    assert open_bundle(restored, TEST_PASSPHRASE).report.ok


def test_wrong_passphrase_refused(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    with pytest.raises(DecryptionError):
        open_bundle(bundle, "Definitely-Wrong-123")


def test_tampered_bundle_payload_detected(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    from dataclasses import replace

    from redscribe.v3.portability.errors import DecryptionError

    tampered_envelope = replace(bundle.envelope, ciphertext=b"x" * 16)
    tampered = PortableBundle(
        header=bundle.header,
        manifest=bundle.manifest,
        envelope=tampered_envelope,
        origin=bundle.origin,
    )
    with pytest.raises(DecryptionError):
        open_bundle(tampered, TEST_PASSPHRASE)


def test_manifest_tamper_detected_on_parse(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    payload = bundle.as_dict()
    payload["manifest"]["entity_count"] = 99
    with pytest.raises(VerificationError):
        PortableBundle.from_dict(payload)


def test_unknown_bundle_format_refused() -> None:
    with pytest.raises(BundleError):
        PortableBundle.from_dict({"format": "unknown"})


def test_malformed_bundle_bytes_refused() -> None:
    with pytest.raises(BundleError):
        PortableBundle.from_bytes(b"not json")
    with pytest.raises(BundleError):
        PortableBundle.from_bytes(b"[1, 2, 3]")


def test_unsupported_bundle_version_refused(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    payload = bundle.as_dict()
    payload["header"]["bundle_version"] = "v9.0"
    with pytest.raises(BundleError):
        PortableBundle.from_dict(payload)


def test_bundle_inspect_without_passphrase(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    info = bundle.inspect()
    assert info["source_device"] == "alpha"
    assert info["entity_count"] == 2
    assert info["link_count"] == 1
    assert info["algorithm"] == bundle.envelope.algorithm
    assert info["size_bytes"] > 0


def test_bundle_file_write_and_read(
    device: DeviceIdentity, clock: FixedClock, tmp_path: object
) -> None:
    bundle = build_bundle(device, clock)
    path = tmp_path / "bundles" / "roundtrip.encbundle"  # type: ignore[operator]
    written = write_bundle(path, bundle)
    assert written == bundle.size()
    restored = read_bundle(path)
    payload = open_bundle(restored, TEST_PASSPHRASE)
    assert payload.report.ok
    assert len(payload.entities) == 2


def test_missing_bundle_file_refused(tmp_path: object) -> None:
    with pytest.raises(BundleError):
        read_bundle(tmp_path / "missing.encbundle")  # type: ignore[operator]


def test_empty_bundle_round_trip(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = create_bundle(
        (), (), device=device, passphrase=TEST_PASSPHRASE, clock=clock, iterations=1_000
    )
    payload = open_bundle(bundle, TEST_PASSPHRASE)
    assert payload.entities == ()
    assert payload.links == ()
    assert payload.report.ok


def test_bundle_payload_summary(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    payload: BundlePayload = open_bundle(bundle, TEST_PASSPHRASE)
    summary = payload.as_dict()
    assert summary["origin_device"] == "alpha"
    assert summary["verification"]["ok"]
    assert summary["manifest"]["bundle_id"] == bundle.header.bundle_id


def test_header_serialization_round_trip(device: DeviceIdentity, clock: FixedClock) -> None:
    bundle = build_bundle(device, clock)
    header = BundleHeader.from_dict(bundle.header.as_dict())
    assert header.as_dict() == bundle.header.as_dict()
