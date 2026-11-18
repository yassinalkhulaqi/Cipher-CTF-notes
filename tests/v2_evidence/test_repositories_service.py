from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.storage.db import Vault
from redscribe.v2.evidence.errors import ConflictError, IngestError, NotFoundError
from redscribe.v2.evidence.files import (
    DirectoryBlobStore,
    InMemoryBlobStore,
    validate_blob_size,
)
from redscribe.v2.evidence.integrity import IntegrityVerifier, sort_issues
from redscribe.v2.evidence.models import (
    AcquisitionMethod,
    CustodyAction,
    EvidenceKind,
    EvidenceStatus,
    IntegrityState,
)
from redscribe.v2.evidence.repositories import (
    InMemoryEvidenceRepository,
    SQLiteEvidenceRepository,
    build_repository,
    repository_counts,
)
from redscribe.v2.evidence.services import EvidenceVaultService, create_service


def test_blob_stores_roundtrip_and_validate_paths(tmp_path: Path) -> None:
    memory = InMemoryBlobStore()
    path = memory.put("ev_blob0001", "capture.png", b"abc")
    assert memory.get(path) == b"abc"
    assert memory.exists(path)
    assert memory.paths() == (path,)
    assert memory.total_bytes() == 3
    assert memory.delete(path)
    assert memory.get(path) is None

    directory = DirectoryBlobStore(tmp_path / "blobs")
    stored = directory.put("ev_blob0002", "../secret.png", b"payload")
    assert stored.startswith("evidence://")
    assert directory.get(stored) == b"payload"
    assert directory.exists(stored)
    assert directory.delete(stored)
    with pytest.raises(IngestError, match="Unknown evidence storage path"):
        directory.get("../../etc/passwd")
    with pytest.raises(IngestError, match="exceeds"):
        validate_blob_size(b"x" * 10, max_bytes=5)
    with pytest.raises(IngestError, match="must not be empty"):
        validate_blob_size(b"")


def test_repository_counts_and_in_memory_roundtrip() -> None:
    repository = InMemoryEvidenceRepository()
    service = EvidenceVaultService(repository)
    record = service.ingest_bytes(b"repo payload", filename="repo.txt")
    assert repository_counts(repository)["records"] == 1
    assert repository.get_record(record.id) == record
    assert len(repository.custody_events(record.id)) == 1
    assert repository.delete_record(record.id)
    assert repository.get_record(record.id) is None


def test_sqlite_repository_persists_all_sections(vault: Vault) -> None:
    repository = SQLiteEvidenceRepository(vault)
    service = EvidenceVaultService(repository)
    record = service.ingest_bytes(b"sqlite payload", filename="disk.img")
    service.add_link(record.id, "F-001", finding_title="Weak ACL", strength=0.8)
    service.set_retention(record.id, retain_days=90)
    service.export_manifest()
    reloaded = SQLiteEvidenceRepository(vault)
    assert reloaded.get_record(record.id) == record
    assert len(reloaded.custody_events(record.id)) == 1
    assert len(reloaded.all_links()) == 1
    assert len(reloaded.all_policies()) == 1
    assert len(reloaded.all_manifests()) == 1
    assert build_repository(vault).get_record(record.id) == record
    assert build_repository().all_records() == []


def test_ingest_dedupe_hashing_and_blob_storage(tmp_path: Path) -> None:
    service = create_service(storage_root=tmp_path / "blobs")
    first = service.ingest_bytes(
        b"dedupe payload",
        filename="capture.txt",
        title="Capture",
        tags=["web", "proof"],
        operator="alice",
        source_path="/evidence/capture.txt",
    )
    assert first.status is EvidenceStatus.ACQUIRED
    assert first.original_filename == "capture.txt"
    assert first.stored_path.startswith("evidence://")
    assert first.provenance.operator == "alice"
    assert first.provenance.method is AcquisitionMethod.MANUAL_UPLOAD
    duplicate = service.ingest_bytes(b"dedupe payload", filename="other.txt")
    assert duplicate.id == first.id
    assert service.stats().total == 1
    assert len(service.list_custody(first.id)) == 2
    assert service.get_record(first.id).title == "Capture"


def test_ingest_path_and_external_records(tmp_path: Path) -> None:
    evidence_file = tmp_path / "sample.log"
    evidence_file.write_bytes(b"error: denied\n")
    service = create_service()
    record = service.ingest_path(evidence_file, title="Auth log")
    assert record.title == "Auth log"
    assert record.kind is EvidenceKind.LOG
    assert record.provenance.source_path == str(evidence_file)
    external = service.record_external(
        title="External disk",
        source_path="/mnt/evidence/disk.img",
        operator="bob",
    )
    assert external.status is EvidenceStatus.DISCOVERED
    assert not external.thumbnail.available
    assert external.kind is EvidenceKind.DISK_IMAGE
    with pytest.raises(IngestError, match="does not exist"):
        service.ingest_path(tmp_path / "missing.bin")


def test_list_filters_status_and_delete_cascade() -> None:
    service = create_service()
    first = service.ingest_bytes(b"one", filename="a.txt", tags=["web"])
    second = service.ingest_bytes(b"two", filename="b.txt", tags=["recon"])
    service.set_status(first.id, EvidenceStatus.VERIFIED)
    assert [item.id for item in service.list_records(tag="web")] == [first.id]
    assert [item.id for item in service.list_records(status=EvidenceStatus.VERIFIED)] == [first.id]
    rows, page = service.list_page(limit=1)
    assert len(rows) == 1
    assert page["total"] == 2
    assert page["has_more"] is True
    assert service.find_by_sha256(first.sha256) == service.get_record(first.id)
    with pytest.raises(NotFoundError, match="does not exist"):
        service.get_record("ev_missing001")
    assert service.delete_record(second.id)
    assert not service.delete_record(second.id)
    assert service.stats().total == 1


def test_update_status_and_provenance() -> None:
    service = create_service()
    record = service.ingest_bytes(b"update payload", filename="update.txt")
    updated = service.update_record(record.id, title="Renamed", description="Now named")
    assert updated.title == "Renamed"
    with pytest.raises(ConflictError, match="Cannot transition"):
        service.set_status(record.id, EvidenceStatus.DISCOVERED)
    service.set_status(record.id, EvidenceStatus.ANALYZED)
    verified = service.set_status(record.id, EvidenceStatus.VERIFIED, actor="alice")
    assert verified.status is EvidenceStatus.VERIFIED
    provenance = service.set_provenance(
        record.id,
        operator="carol",
        case_reference="CASE-1",
        tool_version="2.1",
        image_number=3,
    )
    assert provenance["summary"]["operator"] == "carol"
    assert "witness" in provenance["missing_fields"]
    assert service.get_provenance(record.id)["summary"]["completeness"] > 0


def test_verify_record_detects_missing_and_matching_payloads() -> None:
    service = create_service()
    record = service.ingest_bytes(b"verify payload", filename="verify.txt")
    report = service.verify_record(record.id)
    assert report.state is IntegrityState.VERIFIED
    assert report.digest_match
    assert report.issues == ()
    assert service.blobs.delete(record.stored_path)
    missing = service.verify_record(record.id)
    assert missing.state is IntegrityState.MISSING
    assert any(issue.code == "blob_missing" for issue in missing.issues)
    summary = service.verify_all()
    assert summary["summary"]["states"]["missing"] == 1
    assert service.list_view()["items"][0]["integrity"]["state"] == "missing"


def test_integrity_verifier_checks_custody_and_manifest() -> None:
    service = create_service()
    record = service.ingest_bytes(b"integrity", filename="integrity.txt")
    verifier = IntegrityVerifier(require_custody=True, require_md5=True)
    report = verifier.verify_record(
        record,
        data=b"integrity",
        custody=service.list_custody(record.id),
    )
    assert report.state is IntegrityState.VERIFIED
    assert report.custody_valid
    unverified = verifier.verify_record(record)
    assert unverified.state is IntegrityState.UNVERIFIED
    assert any(issue.code == "blob_unavailable" for issue in unverified.issues)
    assert sort_issues(unverified.issues)


def test_custody_append_and_verification() -> None:
    service = create_service()
    record = service.ingest_bytes(b"custody", filename="custody.txt")
    event = service.add_custody(
        record.id,
        CustodyAction.TRANSFERRED,
        actor="alice",
        description="Handed to lab",
        location="Lab A",
        metadata={"badge": "A1"},
    )
    assert event.previous_hash
    view = service.custody_view(record.id)
    assert view["valid"]
    assert view["summary"]["count"] == 2
    assert len(view["timeline"]) >= 1
    assert service.verify_custody(record.id)[0]


def test_ingest_rejects_missing_or_oversized_payloads() -> None:
    service = create_service(max_bytes=10)
    with pytest.raises(IngestError, match="exceeds"):
        service.ingest_bytes(b"x" * 20, filename="big.bin")
    with pytest.raises(IngestError, match="must not be empty"):
        service.ingest_bytes(b"", filename="empty.bin")
