"""Tests for bundle manifests and integrity verification."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityId, EntityLink, LinkKind
from redscribe.v3.portability.canonical import digest_entity
from redscribe.v3.portability.errors import ManifestError, VerificationError
from redscribe.v3.portability.manifest import MANIFEST_VERSION, BundleManifest
from redscribe.v3.portability.vectors import VersionVector
from tests.v3_portability.conftest import make_entity

LINKS = (
    EntityLink(
        source=EntityId.parse("note:base"),
        target=EntityId.parse("finding:fm"),
        kind=LinkKind.EVIDENCES,
    ),
)


def build_manifest() -> tuple[BundleManifest, tuple[object, ...]]:
    entities = (make_entity("note:base"), make_entity("finding:fm"))
    manifest = BundleManifest.build(
        "bundle_test",
        entities,  # type: ignore[arg-type]
        LINKS,
        created_at=100.0,
        source_device="alpha",
        vector=VersionVector({"alpha": 1}),
        metadata={"label": "round-trip"},
    )
    return manifest, entities


def test_manifest_build_captures_inventory() -> None:
    manifest, entities = build_manifest()
    assert manifest.bundle_id == "bundle_test"
    assert manifest.entity_count == 2
    assert manifest.link_count == 1
    assert manifest.families == ("finding", "note")
    assert set(manifest.checksums) == {entity.ref for entity in entities}
    assert manifest.manifest_version == MANIFEST_VERSION
    assert manifest.vector.as_dict() == {"alpha": 1}


def test_manifest_verifies_unchanged_payload() -> None:
    manifest, entities = build_manifest()
    report = manifest.verify(entities, LINKS)  # type: ignore[arg-type]
    assert report.ok
    assert report.checked_entities == 2
    assert report.checked_links == 1
    assert report.codes == ()
    report.require_ok()


def test_manifest_detects_missing_record() -> None:
    manifest, entities = build_manifest()
    report = manifest.verify(entities[:1], LINKS)  # type: ignore[arg-type]
    assert not report.ok
    assert "MISSING_RECORD" in report.codes
    assert "COUNT_MISMATCH" in report.codes


def test_manifest_detects_extra_record() -> None:
    manifest, entities = build_manifest()
    extras = (*entities, make_entity("note:extra"))
    report = manifest.verify(extras, LINKS)  # type: ignore[arg-type]
    assert "EXTRA_RECORD" in report.codes


def test_manifest_detects_checksum_mismatch() -> None:
    manifest, entities = build_manifest()
    edited = entities[0].apply_fields(
        {"title": "Edited title"},
        vector=entities[0].vector,  # type: ignore[union-attr]
    )
    report = manifest.verify((edited, *entities[1:]), LINKS)  # type: ignore[arg-type]
    assert "CHECKSUM_MISMATCH" in report.codes
    assert "PAYLOAD_DIGEST_MISMATCH" in report.codes
    with pytest.raises(VerificationError):
        report.require_ok()


def test_manifest_detects_link_count_change() -> None:
    manifest, entities = build_manifest()
    report = manifest.verify(entities, ())  # type: ignore[arg-type]
    assert "COUNT_MISMATCH" in report.codes


def test_manifest_digest_is_stable() -> None:
    manifest, _ = build_manifest()
    assert manifest.digest() == manifest.digest()
    assert manifest.origin_digest() == manifest.origin_digest()
    assert len(manifest.origin_digest()) == 24


def test_manifest_serialization_round_trip() -> None:
    manifest, _ = build_manifest()
    payload = manifest.as_dict()
    restored = BundleManifest.from_dict(payload)
    assert restored.as_dict() == payload
    assert restored.verify(  # type: ignore[arg-type]
        (make_entity("note:base"), make_entity("finding:fm")), LINKS
    ).ok


def test_manifest_rejects_unknown_version() -> None:
    manifest, _ = build_manifest()
    payload = manifest.as_dict()
    payload["manifest_version"] = "v9.9"
    with pytest.raises(ManifestError, match="Unsupported manifest version"):
        BundleManifest.from_dict(payload)


def test_manifest_rejects_newer_schema() -> None:
    manifest, _ = build_manifest()
    payload = manifest.as_dict()
    payload["schema_version"] = 999
    with pytest.raises(ManifestError, match="newer than supported"):
        BundleManifest.from_dict(payload)


def test_manifest_rejects_malformed_payload() -> None:
    with pytest.raises(ManifestError):
        BundleManifest.from_dict({"bundle_id": "x"})
    with pytest.raises(ManifestError):
        BundleManifest(
            bundle_id="  ",
            created_at=0,
            source_device="a",
            entity_count=0,
            link_count=0,
            checksums={},
            payload_digest="x",
        )


def test_checksum_helper_is_stable() -> None:
    entity = make_entity("note:base")
    assert digest_entity(entity.as_dict()) == digest_entity(entity.as_dict())
    assert digest_entity(entity.as_dict()) != digest_entity(
        make_entity("note:base", title="Other").as_dict()
    )
