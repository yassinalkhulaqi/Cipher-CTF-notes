from __future__ import annotations

from typing import Any

import pytest

from redscribe.v2.evidence.custody import (
    CustodyChain,
    custody_action_label,
    custody_digest,
    custody_summary,
    custody_timeline,
    event_payload,
    latest_event,
    validate_custody_event,
)
from redscribe.v2.evidence.errors import ConflictError, ValidationError
from redscribe.v2.evidence.hashing import hash_bytes
from redscribe.v2.evidence.mime import mime_from_path
from redscribe.v2.evidence.models import (
    CustodyAction,
    CustodyEvent,
    EvidenceKind,
    EvidenceStatus,
)
from redscribe.v2.evidence.records import (
    apply_update,
    build_record,
    filter_records,
    generate_evidence_id,
    mime_kind,
    paginate_records,
    record_fingerprint,
    record_hash_index,
    record_matches,
    transition_status,
    validate_record,
)


def make_record(evidence_id: str = "ev_test0001", **overrides: Any) -> Any:
    digests = hash_bytes(b"payload")
    payload: dict[str, Any] = {
        "evidence_id": evidence_id,
        "title": "Capture evidence",
        "digests": digests,
        "mime": mime_from_path("capture.png"),
        "original_filename": "capture.png",
        "tags": ["web", "proof"],
    }
    payload.update(overrides)
    return build_record(**payload)


def test_generate_evidence_id_is_stable_and_avoids_collisions() -> None:
    first = generate_evidence_id("seed")
    assert first.startswith("ev_")
    assert len(first) == 13
    assert generate_evidence_id("seed") == first
    assert generate_evidence_id("seed", existing=[first]) != first


def test_build_record_and_validate_record() -> None:
    record = make_record(description="Captured from browser")
    assert record.id == "ev_test0001"
    assert record.title == "Capture evidence"
    assert record.kind is EvidenceKind.IMAGE
    assert record.status is EvidenceStatus.DISCOVERED
    assert record.tags == ("web", "proof")
    assert record.size_bytes == 7
    assert "capture" in record.search_text()
    validate_record(record)
    assert record.summary()["sha256"] == record.sha256
    assert record.detail()["search_text"]


def test_build_record_rejects_invalid_fields() -> None:
    with pytest.raises(ValidationError, match="Invalid evidence id"):
        build_record(
            evidence_id="!",
            title="Bad",
            digests=hash_bytes(b"x"),
            mime=mime_from_path("a.txt"),
        )


def test_apply_update_returns_new_record_and_validates_changes() -> None:
    record = make_record()
    updated = apply_update(record, title="Renamed", tags="new, tags", note_id=12)
    assert updated.title == "Renamed"
    assert updated.tags == ("new", "tags")
    assert updated.note_id == 12
    assert updated.updated_at >= record.updated_at
    assert record.title == "Capture evidence"
    assert apply_update(record) is record
    with pytest.raises(ValidationError, match="must not be empty"):
        apply_update(record, title="")
    with pytest.raises(ValidationError, match="positive integer"):
        apply_update(record, note_id=-1)


def test_status_transitions_follow_lifecycle_rules() -> None:
    record = make_record()
    acquired = transition_status(record, EvidenceStatus.ACQUIRED)
    assert acquired.status is EvidenceStatus.ACQUIRED
    analyzed = transition_status(acquired, EvidenceStatus.ANALYZED)
    verified = transition_status(analyzed, EvidenceStatus.VERIFIED)
    assert transition_status(verified, EvidenceStatus.VERIFIED) is verified
    with pytest.raises(ConflictError, match="Cannot transition"):
        transition_status(record, EvidenceStatus.VERIFIED)
    disposed = transition_status(record, EvidenceStatus.DISPOSED, force=True)
    with pytest.raises(ConflictError, match="disposed"):
        transition_status(disposed, EvidenceStatus.ACQUIRED, force=True)


def test_filter_sort_and_paginate_records() -> None:
    records = [
        make_record("ev_alpha01", title="Alpha", status=EvidenceStatus.ACQUIRED, tags=["web"]),
        make_record("ev_bravo01", title="Bravo", status=EvidenceStatus.VERIFIED, tags=["recon"]),
        make_record("ev_charlie1", title="Charlie", status=EvidenceStatus.ACQUIRED, tags=["web"]),
    ]
    assert [item.title for item in filter_records(records, sort="title", direction="asc")] == [
        "Alpha",
        "Bravo",
        "Charlie",
    ]
    assert [item.id for item in filter_records(records, status=EvidenceStatus.ACQUIRED)] == [
        "ev_alpha01",
        "ev_charlie1",
    ]
    assert len(filter_records(records, tag="web")) == 2
    assert record_matches(records[0], query="alpha")
    page, meta = paginate_records(records, offset=1, limit=1)
    assert [item.id for item in page] == ["ev_bravo01"]
    assert meta["has_more"] is True
    assert meta["next_offset"] == 2
    with pytest.raises(ValidationError, match="Unsupported sort"):
        filter_records(records, sort="unknown")
    assert record_hash_index(records)[records[2].sha256] == "ev_charlie1"
    assert record_fingerprint(records[0]).startswith("ev_alpha01:")


def test_mime_kind_special_cases() -> None:
    log_mime = mime_from_path("access.log")
    assert mime_kind(log_mime, "access.log") is EvidenceKind.LOG
    image_mime = mime_from_path("disk.dd")
    assert mime_kind(image_mime, "disk.dd") is EvidenceKind.DISK_IMAGE


def test_custody_chain_appends_hash_linked_events() -> None:
    chain = CustodyChain()
    first = chain.append(
        "ev_test0001",
        CustodyAction.CREATED,
        actor="alice",
        description="Created",
    )
    second = chain.append(
        "ev_test0001",
        CustodyAction.ACQUIRED,
        actor="bob",
        description="Acquired",
        metadata={"tool": "dd"},
    )
    assert first.id == 1
    assert second.id == 2
    assert first.previous_hash == "0" * 64
    assert second.previous_hash == first.event_hash
    assert chain.last_hash("ev_test0001") == second.event_hash
    valid, problems = chain.verify("ev_test0001")
    assert valid
    assert problems == []
    validate_custody_event(second)
    assert custody_action_label(CustodyAction.ACQUIRED) == "Acquired"


def test_custody_chain_detects_tampering() -> None:
    chain = CustodyChain()
    event = chain.append("ev_test0001", CustodyAction.CREATED, actor="alice")
    tampered = CustodyEvent(
        id=event.id,
        evidence_id=event.evidence_id,
        action=event.action,
        actor="mallory",
        timestamp=event.timestamp,
        description=event.description,
        location=event.location,
        reference=event.reference,
        previous_hash=event.previous_hash,
        event_hash=event.event_hash,
        metadata=event.metadata,
    )
    restored = CustodyChain([tampered])
    valid, problems = restored.verify("ev_test0001")
    assert not valid
    assert any("hash does not match" in item for item in problems)
    with pytest.raises(ValidationError, match="actor"):
        validate_custody_event(
            CustodyEvent(
                id=1,
                evidence_id="ev_test0001",
                action=CustodyAction.CREATED,
                actor="",
                timestamp="2026-01-01T00:00:00+00:00",
                description="",
                location="",
                reference="",
                previous_hash="0" * 64,
                event_hash="a" * 64,
                metadata={},
            )
        )


def test_custody_projection_helpers() -> None:
    chain = CustodyChain()
    chain.append(
        "ev_test0001",
        CustodyAction.CREATED,
        actor="alice",
        timestamp="2026-01-01T10:00:00+00:00",
    )
    chain.append(
        "ev_test0001",
        CustodyAction.VERIFIED,
        actor="bob",
        timestamp="2026-01-02T11:00:00+00:00",
    )
    events = chain.events
    timeline = custody_timeline(events)
    assert len(timeline) == 2
    assert timeline[0]["date"] == "2026-01-01"
    assert custody_summary(events)["count"] == 2
    assert custody_summary(events)["actors"] == ["alice", "bob"]
    assert latest_event(events) == events[-1]
    assert len(custody_digest(events)) == 64
    assert (
        event_payload(
            evidence_id="ev_test0001",
            action=CustodyAction.CREATED,
            actor="alice",
            timestamp="2026-01-01T10:00:00+00:00",
            description="",
            location="",
            reference="",
            metadata={},
        )["evidence_id"]
        == "ev_test0001"
    )
