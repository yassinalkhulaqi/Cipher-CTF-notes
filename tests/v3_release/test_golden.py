"""Tests for the deterministic golden-path vault."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityKind, LinkKind
from redscribe.v3.release.golden import (
    GoldenBundle,
    GoldenPathError,
    GoldenPathVault,
    ImportResult,
    MergeResult,
)


def _vault(prefix: str = "golden", start: float = 1000.0) -> GoldenPathVault:
    return GoldenPathVault(prefix=prefix, clock=FixedClock(start=start, step=1.0))


def _drive(vault: GoldenPathVault) -> GoldenBundle:
    vault.capture_note()
    vault.create_finding()
    vault.attach_evidence()
    vault.compose_report()
    return vault.export_bundle(source="device-a")


def test_vault_prefix_validation() -> None:
    with pytest.raises(GoldenPathError):
        GoldenPathVault(prefix="")
    with pytest.raises(GoldenPathError):
        GoldenPathVault(prefix="bad prefix")


def test_capture_note_is_idempotent() -> None:
    vault = _vault()
    first = vault.capture_note()
    second = vault.capture_note()
    assert first["cached"] is False
    assert second["cached"] is True
    assert first["entity_id"] == second["entity_id"]
    assert vault.stats()["entities"] == 1
    assert vault.stats()["events"] == 1
    assert "golden.captured" in vault.event_kinds()


def test_capture_with_distinct_key_creates_second_note() -> None:
    vault = _vault()
    vault.capture_note()
    vault.capture_note(
        title="Another note", idempotency_key="other-key", value="golden-note-second"
    )
    assert vault.stats()["entities"] == 2


def test_finding_links_back_to_note() -> None:
    vault = _vault()
    vault.capture_note()
    finding = vault.create_finding(severity="critical", score=9.1)
    note_ref = vault.ref_for(EntityKind.NOTE, "note-capture")
    finding_ref = vault.ref_for(EntityKind.FINDING, "finding")
    assert finding["severity"] == "critical"
    assert finding["cvss"] == 9.1
    assert vault.has_link(note_ref, finding_ref, LinkKind.DERIVES) is True
    assert vault.has_link(finding_ref, note_ref, LinkKind.DERIVES) is False


def test_evidence_payload_contains_secret_before_redaction() -> None:
    vault = _vault()
    vault.capture_note()
    vault.create_finding()
    evidence = vault.attach_evidence(path="proof.bin", digest="a" * 64)
    raw = vault.events.records()[-1].event.payload
    assert raw["api_key"] == "should-not-be-exported"
    assert evidence["sha256"] == "a" * 64
    finding_ref = vault.ref_for(EntityKind.FINDING, "finding")
    evidence_ref = vault.ref_for(EntityKind.EVIDENCE, "evidence")
    assert vault.has_link(evidence_ref, finding_ref, LinkKind.EVIDENCES) is True


def test_report_contains_and_references() -> None:
    vault = _vault()
    _drive(vault)
    report_ref = vault.ref_for(EntityKind.REPORT, "report")
    finding_ref = vault.ref_for(EntityKind.FINDING, "finding")
    note_ref = vault.ref_for(EntityKind.NOTE, "note-capture")
    assert vault.has_link(report_ref, finding_ref, LinkKind.CONTAINS) is True
    assert vault.has_link(report_ref, note_ref, LinkKind.REFERENCES) is True
    assert vault.stats()["links"] == 4


def test_bundle_shape_and_digest() -> None:
    vault = _vault()
    bundle = _drive(vault)
    assert bundle.version == "3.0"
    assert len(bundle.records) == 4
    assert len(bundle.links) == 4
    assert len(bundle.events) == 4
    assert bundle.digest.startswith('"')
    assert GoldenPathVault.verify_bundle(bundle) is True
    assert bundle.canonical() == bundle.canonical()
    payload = bundle.as_dict()
    assert payload["digest"] == bundle.digest
    assert "source" in payload


def test_bundle_rejects_unsupported_version() -> None:
    vault = _vault()
    valid = _drive(vault)
    old = GoldenBundle(
        source=valid.source,
        version="2.0",
        records=valid.records,
        links=valid.links,
        events=valid.events,
        digest=valid.digest,
    )
    assert GoldenPathVault.verify_bundle(old) is False
    with pytest.raises(GoldenPathError):
        GoldenPathVault.from_bundle(old)


def test_bundle_detects_record_tampering() -> None:
    vault = _vault()
    valid = _drive(vault)
    altered = GoldenBundle(
        source=valid.source,
        version=valid.version,
        records=(dict(valid.records[0], title="tampered"), *valid.records[1:]),
        links=valid.links,
        events=valid.events,
        digest=valid.digest,
    )
    assert GoldenPathVault.verify_bundle(altered) is False
    with pytest.raises(GoldenPathError):
        GoldenPathVault.from_bundle(altered)


def test_import_restores_state_and_correlation() -> None:
    bundle = _drive(_vault())
    restored, result = GoldenPathVault.from_bundle(bundle, correlation_id="import-42")
    assert isinstance(result, ImportResult)
    assert result.restored == 4
    assert result.links_restored == 4
    assert result.event_count == 4
    assert restored.stats()["entities"] == 4
    assert restored.stats()["links"] == 4
    assert restored.stats()["correlation_id"] == "import-42"
    assert result.as_dict()["source"] == "device-a"
    assert "golden.imported" in restored.event_kinds()


def test_merge_adds_peer_records() -> None:
    local_bundle = _drive(_vault())
    local, _ = GoldenPathVault.from_bundle(local_bundle)
    peer_bundle = _drive(_vault(prefix="peer", start=2000.0))
    result = local.merge_bundle(peer_bundle, source="device-b")
    assert isinstance(result, MergeResult)
    assert result.added == 4
    assert result.skipped == 0
    assert result.links_added == 4
    assert result.ok is True
    assert local.stats()["entities"] == 8
    assert result.as_dict()["source"] == "device-b"


def test_merge_replay_is_idempotent() -> None:
    bundle = _drive(_vault())
    local, _ = GoldenPathVault.from_bundle(bundle)
    result = local.merge_bundle(bundle, source="device-a-replay")
    assert result.added == 0
    assert result.skipped == 4
    assert result.links_added == 0
    assert result.links_skipped == 4
    assert result.ok is True
    assert local.stats()["entities"] == 4


def test_merge_rejects_bad_digest() -> None:
    local = _vault()
    bad = GoldenBundle("", "3.0", (), (), (), '"bad"')
    with pytest.raises(GoldenPathError):
        local.merge_bundle(bad)


def test_empty_merge_result_is_not_ok() -> None:
    result = MergeResult(source="x", added=0, skipped=0, links_added=0, links_skipped=0)
    assert result.ok is False


def test_stats_include_outbox_checkpoint() -> None:
    vault = _vault()
    vault.capture_note()
    vault.create_finding()
    stats = vault.stats()
    assert stats["events"] == 2
    assert stats["checkpoint"] == 2
    assert stats["outbox"] == 2
    assert stats["prefix"] == "golden"


def test_export_with_custom_source() -> None:
    vault = _vault()
    _drive(vault)
    bundle = vault.export_bundle(source="custom-device")
    assert bundle.source == "custom-device"
    assert vault.last_bundle is not None
    assert vault.last_bundle.digest == bundle.digest
