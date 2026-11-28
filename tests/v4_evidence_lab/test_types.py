"""Value-object tests for the evidence inspection lab."""

from __future__ import annotations

import pytest

from redscribe.v4.contracts import EntityKind
from redscribe.v4.evidence_lab.types import (
    ChainIntegrityError,
    ChainVerification,
    CustodyAction,
    CustodyEntry,
    EvidenceLabError,
    EvidenceRecord,
    HashAlgorithm,
    HashVerification,
    HexCell,
    HexRow,
    InspectionResult,
    StringEncoding,
    StringHit,
    ValidationError,
    is_hex_digest,
    normalize_tags,
    printable_ascii,
    require_int,
    require_text,
    sorted_records,
)

FROZEN = "2024-05-01T12:00:00.000Z"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA1_A = "c" * 40
MD5_A = "d" * 32


def record(name: str = "disk.img", digest: str = SHA256_A) -> EvidenceRecord:
    return EvidenceRecord(
        id="ev-0001",
        name=name,
        size=4096,
        sha256=digest,
        acquired_at=FROZEN,
        tags=("Disk", "triage"),
    )


def cell(offset: int, value: int) -> HexCell:
    return HexCell(offset=offset, hex=f"{value:02x}", ascii=printable_ascii(value))


def test_hash_algorithm_parse_and_properties() -> None:
    assert HashAlgorithm.parse("SHA256") is HashAlgorithm.SHA256
    assert HashAlgorithm.parse(" sha-1 ") is HashAlgorithm.SHA1
    assert HashAlgorithm.parse("MD5") is HashAlgorithm.MD5
    assert HashAlgorithm.SHA256.digest_size == 64
    assert HashAlgorithm.SHA1.digest_size == 40
    assert HashAlgorithm.MD5.digest_size == 32
    assert HashAlgorithm.SHA256.label == "SHA-256"
    assert HashAlgorithm.MD5.label == "MD5"
    with pytest.raises(ValidationError, match="unknown hash algorithm"):
        HashAlgorithm.parse("sha999")


def test_string_encoding_parse_and_unit() -> None:
    assert StringEncoding.parse("ASCII") is StringEncoding.ASCII
    assert StringEncoding.parse("utf8") is StringEncoding.UTF8
    assert StringEncoding.parse("UTF-16LE") is StringEncoding.UTF16LE
    assert StringEncoding.ASCII.unit == 1
    assert StringEncoding.UTF16LE.unit == 2
    with pytest.raises(ValidationError, match="unknown string encoding"):
        StringEncoding.parse("latin1")


def test_custody_action_parse_and_label() -> None:
    assert CustodyAction.parse(" Acquired ") is CustodyAction.ACQUIRED
    assert CustodyAction.VERIFIED.label == "Verified"
    with pytest.raises(ValidationError, match="unknown custody action"):
        CustodyAction.parse("teleported")


def test_require_helpers_and_tag_normalization() -> None:
    assert require_text("  name ", "name") == "name"
    assert require_int(3, "size") == 3
    assert normalize_tags(["Disk", "disk", "", " triage "]) == ("disk", "triage")
    assert is_hex_digest(SHA256_A, 64)
    assert not is_hex_digest("zz" * 32, 64)
    assert not is_hex_digest("a" * 63, 64)
    assert printable_ascii(65) == "A"
    assert printable_ascii(0) == "."
    with pytest.raises(ValidationError, match="non-empty string"):
        require_text("   ", "actor")
    with pytest.raises(ValidationError, match="must be an integer"):
        require_int("4", "size")
    with pytest.raises(ValidationError, match=">= 2"):
        require_int(1, "size", minimum=2)
    with pytest.raises(ValidationError, match="invalid tag"):
        normalize_tags(["bad tag"])


def test_evidence_record_validates_and_roundtrips() -> None:
    item = record()
    assert item.name == "disk.img"
    assert item.tags == ("disk", "triage")
    assert item.extension == "img"
    assert item.short_hash == SHA256_A[:12]
    assert item.has_tag(" TRIAGE ")
    referenced = EvidenceRecord(
        "11111111-1111-1111-1111-111111111111", "disk.img", 2, SHA256_A, FROZEN
    )
    assert referenced.to_ref().kind is EntityKind.EVIDENCE
    restored = EvidenceRecord.from_dict(item.to_dict())
    assert restored == item
    assert item.with_hash(SHA256_B).sha256 == SHA256_B
    assert record().with_hash(SHA256_A) == item


def test_evidence_record_created_with_injected_id() -> None:
    item = EvidenceRecord.create(
        name="capture.pcap",
        size=128,
        sha256=SHA256_A,
        acquired_at=FROZEN,
        tags=["Network"],
        identifier="ev-fixed",
    )
    assert item.id == "ev-fixed"
    assert item.tags == ("network",)
    assert EvidenceRecord.create("x", 0, SHA256_A, FROZEN).id


@pytest.mark.parametrize(
    ("name", "size", "digest"),
    [("", 1, SHA256_A), ("x", -1, SHA256_A), ("x", 1, "abc"), ("x", 1, "z" * 64)],
)
def test_evidence_record_rejects_bad_fields(name: str, size: int, digest: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord("ev-1", name, size, digest, FROZEN)


def test_hex_cell_and_row_roundtrip() -> None:
    first, second = cell(16, 0x41), cell(17, 0x0A)
    assert first.byte == 65
    assert first.is_printable
    assert not second.is_printable
    assert second.ascii == "."
    assert HexCell.from_dict(first.to_dict()) == first
    row = HexRow(offset=16, cells=(first, second))
    assert row.size == 2
    assert row.ascii == "A."
    assert row.cell_at(17) == second
    assert row.cell_at(99) is None
    assert HexRow.from_dict(row.to_dict()) == row


def test_hex_cell_and_row_validation() -> None:
    with pytest.raises(ValidationError, match="two hex digits"):
        HexCell(offset=0, hex="4", ascii="4")
    with pytest.raises(ValidationError, match="single character"):
        HexCell(offset=0, hex="41", ascii="AB")
    with pytest.raises(ValidationError, match="between 1 and 16"):
        HexRow(offset=0, cells=(cell(0, 65),) * 17)
    with pytest.raises(ValidationError, match="consecutive"):
        HexRow(offset=0, cells=(cell(0, 65), cell(5, 66)))


def test_string_hit_properties_and_roundtrip() -> None:
    hit = StringHit(offset=8, value="https://x.test", encoding="ascii")
    assert hit.length == 14
    assert hit.end == 22
    assert hit.is_likely_url
    assert not StringHit(0, "plain", StringEncoding.ASCII).is_likely_url
    assert StringHit.from_dict(hit.to_dict()) == hit
    wide = StringHit(offset=2, value="wide", encoding=StringEncoding.UTF16LE)
    assert wide.end == 10
    with pytest.raises(ValidationError, match="non-empty string"):
        StringHit(0, "  ")


def test_hash_verification_roundtrip_and_verdict() -> None:
    good = HashVerification.from_hashes(HashAlgorithm.SHA256, SHA256_A.upper(), SHA256_A)
    assert good.matches
    assert good.verdict == "verified"
    assert good.expected == SHA256_A
    assert HashVerification.from_dict(good.to_dict()) == good
    bad = HashVerification.from_hashes("md5", MD5_A, "0" * 32)
    assert not bad.matches
    assert bad.verdict == "mismatch"
    with pytest.raises(ValidationError, match="expected is not a valid SHA-256"):
        HashVerification(HashAlgorithm.SHA256, SHA1_A, SHA256_A, True)
    with pytest.raises(ValidationError, match="expected is not a valid SHA-1"):
        HashVerification(HashAlgorithm.SHA1, SHA256_A, SHA1_A, True)


def test_custody_entry_canonical_and_roundtrip() -> None:
    entry = CustodyEntry(
        actor="alice",
        action=CustodyAction.ACQUIRED,
        timestamp=FROZEN,
        from_hash=SHA256_A,
        to_hash=SHA256_B,
    )
    assert entry.canonical() == f"{FROZEN}|alice|acquired|{SHA256_A}|{SHA256_B}"
    assert CustodyEntry.from_dict(entry.to_dict()) == entry
    assert entry.action.label == "Acquired"
    with pytest.raises(ValidationError, match="actor must be a non-empty string"):
        CustodyEntry("", CustodyAction.ACQUIRED, FROZEN, SHA256_A, SHA256_B)
    with pytest.raises(ValidationError, match="from_hash must be a SHA-256"):
        CustodyEntry("alice", CustodyAction.ACQUIRED, FROZEN, "bad", SHA256_B)


def test_chain_verification_helpers() -> None:
    valid = ChainVerification(valid=True, length=3)
    assert valid.headline == "chain intact"
    assert valid.to_dict()["length"] == 3
    broken = ChainVerification(valid=False, length=3, broken_index=1, issues=("link",))
    assert broken.headline == "broken at entry 1"
    assert broken.to_dict()["issues"] == ["link"]
    assert issubclass(ChainIntegrityError, EvidenceLabError)
    assert issubclass(ValidationError, EvidenceLabError)


def test_inspection_result_summary_and_roundtrip() -> None:
    row = HexRow(offset=0, cells=(cell(0, 65), cell(1, 66)))
    result = InspectionResult(
        evidence_id="ev-0001",
        hex_rows=(row,),
        strings=(StringHit(0, "AB"),),
        verifications=(HashVerification.from_hashes("sha256", SHA256_A, SHA256_A),),
        generated_at=FROZEN,
        notes=("note",),
    )
    assert result.cell_count == 2
    assert result.all_verified
    assert result.cells() == row.cells
    assert result.summary()["rows"] == 1
    assert result.summary()["all_verified"] is True
    assert InspectionResult.from_dict(result.to_dict()) == result
    empty = InspectionResult(evidence_id="ev-2")
    assert not empty.all_verified
    assert empty.summary()["cells"] == 0


def test_sorted_records_is_deterministic() -> None:
    first = EvidenceRecord("z", "z.img", 1, SHA256_A, FROZEN)
    second = EvidenceRecord("a", "A.img", 2, SHA256_B, FROZEN)
    third = EvidenceRecord("m", "m.img", 3, SHA256_A, FROZEN)
    assert [item.id for item in sorted_records([first, third, second])] == ["a", "m", "z"]
