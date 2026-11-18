from __future__ import annotations

from typing import Any, cast

import pytest

from redscribe.v2.evidence.errors import ConflictError, ManifestError, ValidationError
from redscribe.v2.evidence.links import (
    FindingLink,
    FindingLinkIndex,
    group_by_type,
    link_key,
    link_sort_key,
    link_summary,
    link_weight,
    update_link,
    validate_link,
)
from redscribe.v2.evidence.manifests import (
    compare_manifests,
    manifest_stats,
    manifest_to_json,
    manifest_to_jsonl,
    parse_manifest,
    validate_manifest,
    verify_manifest_checksum,
)
from redscribe.v2.evidence.models import (
    AcquisitionMethod,
    DispositionAction,
    LinkType,
    RetentionBasis,
)
from redscribe.v2.evidence.provenance import (
    acquisition_timeline,
    compare_provenance,
    merge_provenance,
    missing_provenance_fields,
    provenance_checklist,
    provenance_summary,
    provenance_tags,
    update_provenance,
    validate_case_reference,
)
from redscribe.v2.evidence.retention import (
    RetentionManager,
    build_policy,
    days_remaining,
    describe_policy,
    evaluate_policy,
    extend_policy,
    retention_summary,
    set_legal_hold,
    validate_retain_days,
)
from redscribe.v2.evidence.services import create_service


def test_link_index_add_update_and_summary() -> None:
    index = FindingLinkIndex()
    first = index.add(
        evidence_id="ev_alpha0001",
        finding_id="F-001",
        finding_title="Weak ACL",
        link_type=LinkType.SUPPORTS,
        strength=0.8,
    )
    second = index.add(
        evidence_id="ev_alpha0001",
        finding_id="F-002",
        link_type=LinkType.CONTAINS,
        strength=0.4,
    )
    assert [item.id for item in index.links] == [1, 2]
    assert link_key(first.evidence_id, first.finding_id, first.link_type) == (
        "ev_alpha0001",
        "f-001",
        "supports",
    )
    assert link_weight(first) > link_weight(second)
    assert link_sort_key(first) < link_sort_key(second)
    assert group_by_type([first, second])["supports"][0]["id"] == first.id
    assert link_summary([first, second])["total"] == 2
    validate_link(first)
    assert update_link(first, note="Confirmed", strength=0.9).strength == 0.9
    with pytest.raises(ConflictError, match="already exists"):
        index.add(evidence_id="ev_alpha0001", finding_id="F-001", link_type=LinkType.SUPPORTS)


def test_link_validation_rejects_bad_ids_and_strength() -> None:
    def make_link(**changes: object) -> FindingLink:
        payload: dict[str, object] = {
            "id": 1,
            "evidence_id": "ev_alpha0001",
            "finding_id": "F-001",
            "finding_title": "Weak ACL",
            "link_type": LinkType.SUPPORTS,
            "strength": 0.5,
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": "alice",
            "note": "",
        }
        payload.update(changes)
        return cast(Any, FindingLink)(**payload)

    with pytest.raises(ValidationError, match="Invalid evidence id"):
        validate_link(make_link(evidence_id="!"))
    with pytest.raises(ValidationError, match="Finding id"):
        validate_link(make_link(finding_id=""))
    with pytest.raises(ValidationError, match="strength"):
        validate_link(make_link(strength=2.0))


def test_retention_policy_build_and_decisions() -> None:
    policy = build_policy(
        "ev_alpha0001",
        basis=RetentionBasis.SHORT_TERM,
        retain_days=10,
        reason="Rapid triage",
    )
    assert policy.retain_days == 10
    decision = evaluate_policy(policy, now="2026-01-01T00:00:00Z")
    assert decision.evidence_id == "ev_alpha0001"
    assert days_remaining(policy, now=policy.updated_at) == 10
    assert describe_policy(policy, now="2026-01-01T00:00:00Z")["decision"]
    extended = extend_policy(policy, days=5)
    assert extended.retain_days == 15
    held = set_legal_hold(policy, held=True, reason="Litigation")
    assert held.legal_hold
    assert evaluate_policy(held, now="2026-01-01T00:00:00Z").action is DispositionAction.KEEP
    assert retention_summary([policy, held])
    with pytest.raises(ValidationError, match="retain_days"):
        validate_retain_days(-1)


def test_retention_manager_flags_expired_items() -> None:
    manager = RetentionManager()
    policy = build_policy(
        "ev_alpha0001",
        basis=RetentionBasis.SHORT_TERM,
        retain_days=1,
        updated_at="2025-01-01T00:00:00Z",
    )
    manager.set(policy)
    assert manager.get("ev_alpha0001") == policy
    decision = manager.evaluate("ev_alpha0001", now="2026-01-01T00:00:00Z")
    assert decision is not None
    assert decision.action is DispositionAction.DESTROY
    assert manager.due_for_destroy(now="2026-01-01T00:00:00Z") == ("ev_alpha0001",)
    assert len(manager.plan(now="2026-01-01T00:00:00Z")) == 1
    assert len(manager.all()) == 1


def test_provenance_helpers_and_checklists() -> None:
    service = create_service(case_reference="CASE-7")
    record = service.ingest_bytes(
        b"provenance payload",
        filename="evidence.txt",
        operator="alice",
        witness="bob",
        image_number=2,
    )
    provenance = record.provenance
    assert provenance.method is AcquisitionMethod.MANUAL_UPLOAD
    assert provenance.case_reference == "CASE-7"
    summary = provenance_summary(provenance)
    assert summary["completeness"] > 0
    assert "tool_version" in summary["missing_fields"]
    assert missing_provenance_fields(provenance)
    assert any(item["filled"] for item in provenance_checklist(provenance))
    assert "manual_upload" in provenance_tags(provenance)
    timeline = acquisition_timeline([provenance])
    assert timeline[0]["method"] == AcquisitionMethod.MANUAL_UPLOAD.value
    assert validate_case_reference("CASE-8") == "CASE-8"
    override = update_provenance(provenance, tool="FTK", notes="Acquired")
    merged = merge_provenance(override, provenance)
    assert merged.tool == "FTK"
    assert set(compare_provenance(provenance, merged)["changed"]) == {"tool", "notes"}


def test_service_links_and_retention_views() -> None:
    service = create_service()
    record = service.ingest_bytes(b"links payload", filename="links.txt")
    link = service.add_link(
        record.id,
        "F-100",
        finding_title="Privilege escalation",
        link_type=LinkType.SUPPORTS,
        strength=0.9,
    )
    assert service.list_links(finding_id="f-100") == [link]
    view = service.links_view(record.id)
    assert view["summary"]["total"] == 1
    assert service.remove_link(link.id)
    assert not service.remove_link(link.id)
    service.set_retention(record.id, retain_days=2, reason="Short project")
    policy_view = service.get_retention(record.id)
    assert policy_view["policy"]["retain_days"] == 2
    held = service.set_hold(record.id, held=True, reason="Legal")
    assert held.legal_hold
    assert len(service.retention_plan()) == 1
    applied = service.apply_retention(now="2026-01-01T00:00:00Z")
    assert applied["disposed"] == []
    assert len(applied["decisions"]) == 1


def test_manifest_export_json_and_validation() -> None:
    service = create_service(case_reference="CASE-M")
    record = service.ingest_bytes(b"manifest payload", filename="manifest.txt")
    service.add_link(record.id, "F-1", link_type=LinkType.SUPPORTS)
    service.set_retention(record.id, retain_days=30)
    manifest = service.export_manifest()
    assert manifest.version == 1
    assert manifest.generator == "redscribe-evidence-vault"
    assert manifest.case_reference == "CASE-M"
    assert verify_manifest_checksum(manifest)
    assert validate_manifest(manifest)[0]
    assert manifest_stats(manifest)["records"] == 1
    payload = manifest.as_dict()
    assert parse_manifest(payload) == manifest
    assert "checksum" in manifest_to_json(manifest)
    assert len(manifest_to_jsonl(manifest).splitlines()) >= 1
    changed = manifest.as_dict()
    changed["records"][0]["title"] = "Tampered"
    with pytest.raises(ManifestError, match="checksum"):
        parse_manifest(changed)


def test_manifest_import_plan_and_reimport() -> None:
    source = create_service(case_reference="CASE-I")
    record = source.ingest_bytes(b"import payload", filename="import.txt")
    manifest = source.export_manifest()
    target = create_service()
    preview = target.preview_import(manifest.as_dict())
    assert preview["valid"]
    assert preview["plan"]["create"]
    result = target.import_manifest(manifest.as_dict())
    assert result["created"] == [record.id]
    assert target.get_record(record.id) == record
    second = target.import_manifest(manifest.as_dict(), strategy="skip")
    assert second["skipped"] == [record.id]
    with pytest.raises(ManifestError, match="checksum"):
        target.import_manifest({"format": "wrong"})
    with pytest.raises(ConflictError, match="explicit renaming"):
        target.import_manifest(manifest.as_dict(), strategy="rename")


def test_compare_manifests_detects_changes() -> None:
    first_service = create_service()
    first_record = first_service.ingest_bytes(b"v1", filename="v1.txt")
    first = first_service.export_manifest()
    second_service = create_service()
    second_service.ingest_bytes(b"v2", filename="v2.txt")
    second = second_service.export_manifest()
    comparison = compare_manifests(first, second)
    assert comparison["added"] or comparison["removed"]
    assert first_record.id not in comparison["added"]
