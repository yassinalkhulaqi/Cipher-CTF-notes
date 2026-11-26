"""Domain-service tests for hex dumps, strings, hashing, custody, and diffs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from redscribe.v4.clock import Clock
from redscribe.v4.evidence_lab.service import (
    BundleDiffer,
    ChainIntegrityResult,
    CustodyGraph,
    DiffItem,
    HashVerifier,
    HexDumper,
    InspectionPipeline,
    StringExtractor,
    assert_verified,
)
from redscribe.v4.evidence_lab.types import (
    ChainIntegrityError,
    CustodyAction,
    CustodyEntry,
    EvidenceRecord,
    HashAlgorithm,
    HashMismatchError,
    StringEncoding,
    StringHit,
    ValidationError,
)

FROZEN = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
SHA256_A = "a" * 64
SHA256_B = "b" * 64


def frozen_clock() -> Clock:
    return Clock(frozen_at=FROZEN)


def sample_record(
    name: str = "sample.bin", digest: str = SHA256_A, size: int = 40
) -> EvidenceRecord:
    return EvidenceRecord("ev-1", name, size, digest, "2024-05-01T12:00:00.000Z", ("disk",))


def test_hex_dumper_offsets_and_ascii_columns() -> None:
    dumper = HexDumper()
    data = bytes(range(0x41, 0x55))
    cells = dumper.dump(data, start_offset=0x1000)
    assert len(cells) == 20
    assert cells[0].offset == 0x1000
    assert cells[0].hex == "41"
    assert cells[0].ascii == "A"
    assert cells[-1].offset == 0x1013
    assert cells[19].ascii == "T"
    assert dumper.ascii_column(cells[:4]) == "ABCD"


def test_hex_dumper_rows_group_sixteen_bytes() -> None:
    dumper = HexDumper(bytes_per_row=16)
    rows = dumper.rows(bytes(range(40)))
    assert [row.offset for row in rows] == [0, 16, 32]
    assert [row.size for row in rows] == [16, 16, 8]
    assert rows[0].cells[15].offset == 15
    assert rows[2].ascii.startswith(' !"#')
    assert dumper.rows(bytes(range(40)), max_rows=1)[0].size == 16


def test_hex_dumper_render_and_format_alignment() -> None:
    dumper = HexDumper(bytes_per_row=8)
    data = b"ABCDEFGHIJKLMNOP"
    rendered = dumper.render(data)
    assert len(rendered) == 2
    assert "41 42" in rendered[0]
    assert "47 48" in rendered[0]
    assert rendered[0].startswith("00000000")
    assert rendered[0].endswith("|ABCDEFGH|")
    assert "00000008" in rendered[1]


def test_hex_dumper_slice_and_offset_lookup() -> None:
    dumper = HexDumper(start_offset=0x200)
    window, start = dumper.slice(b"abcdef", start=2, length=3)
    assert window == b"cde"
    assert start == 2
    assert [cell.offset for cell in dumper.dump(b"abcdef", start=2, length=3)] == [
        0x202,
        0x203,
        0x204,
    ]
    assert dumper.index_at_offset(0x204) == 4
    assert dumper.index_at_offset(1) is None
    assert dumper.cell_at(b"abc", 1).hex == "62"


def test_hex_dumper_validation_and_edge_cases() -> None:
    with pytest.raises(ValidationError, match="bytes_per_row"):
        HexDumper(bytes_per_row=0)
    with pytest.raises(ValidationError, match="start_offset"):
        HexDumper(start_offset=-1)
    with pytest.raises(ValidationError, match="slice start"):
        HexDumper().slice(b"abc", start=9)
    with pytest.raises(IndexError, match="out of range"):
        HexDumper().cell_at(b"abc", 4)
    assert HexDumper().rows(b"") == ()
    assert HexDumper().dump(b"abc", length=0) == ()
    assert HexDumper(start_offset=8).dump(b"abc", start_offset=0)[0].offset == 0


def test_hex_dumper_histogram() -> None:
    top = HexDumper().histogram(b"aabbbc")
    assert top[0] == (ord("b"), 3)
    assert top[-1][1] == 1


def test_string_extractor_ascii_runs_and_min_length() -> None:
    data = b"abc\x00hello world\x00xy"
    extractor = StringExtractor(min_length=3)
    hits = extractor.extract(data)
    assert [hit.value for hit in hits] == ["abc", "hello world"]
    strict = StringExtractor(min_length=5)
    assert [hit.value for hit in strict.extract(data)] == ["hello world"]
    assert StringExtractor().extract(b"\x00\x01\xff") == ()


def test_string_extractor_dedupe_and_scan_order() -> None:
    data = b"hello\x00hello\x00second"
    deduped = StringExtractor(min_length=3).scan(data)
    assert [hit.value for hit in deduped] == ["hello", "second"]
    kept = StringExtractor(min_length=3, dedupe=False).scan(data)
    assert len(kept) == 3
    assert [hit.offset for hit in kept] == sorted(hit.offset for hit in kept)


def test_string_extractor_utf16le() -> None:
    data = "wide text".encode("utf-16le")
    hits = StringExtractor(min_length=4).extract(data, StringEncoding.UTF16LE)
    assert len(hits) == 1
    assert hits[0].value == "wide text"
    assert hits[0].encoding is StringEncoding.UTF16LE
    assert hits[0].end == len(data)
    assert StringExtractor(min_length=4).extract(b"ab\x00\x00", "utf16le") == ()


def test_string_extractor_filter_and_top() -> None:
    hits = (
        StringHit(0, "https://a.test", StringEncoding.ASCII),
        StringHit(9, "plain", StringEncoding.ASCII),
        StringHit(20, "ABCDEFGHIJ", StringEncoding.ASCII),
    )
    extractor = StringExtractor(min_length=4)
    assert [hit.value for hit in extractor.filter(hits, prefix="http")] == ["https://a.test"]
    assert extractor.filter(hits, min_length=10) == (hits[0], hits[2])
    assert extractor.top(hits, limit=1)[0].value == "https://a.test"
    assert hits[0].is_likely_url
    with pytest.raises(ValidationError, match="limit must be >= 1"):
        extractor.top(hits, limit=0)


def test_string_extractor_validation() -> None:
    with pytest.raises(ValidationError, match="min_length"):
        StringExtractor(min_length=0)
    with pytest.raises(ValidationError, match="at least one encoding"):
        StringExtractor(encodings=())
    with pytest.raises(ValidationError, match="unknown string encoding"):
        StringExtractor(encodings=("latin1",))


def test_hash_verifier_known_vectors() -> None:
    verifier = HashVerifier()
    data = b"abc"
    assert verifier.compute(data, "sha256") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert verifier.compute(data, HashAlgorithm.SHA1).startswith("a9993e36")
    assert verifier.compute(data, HashAlgorithm.MD5) == "900150983cd24fb0d6963f7d28e17f72"
    assert len(verifier.compute_all(data)) == 3
    assert verifier.digest_of(data) == verifier.compute(data, HashAlgorithm.SHA256)


def test_hash_verifier_pass_and_fail() -> None:
    verifier = HashVerifier()
    digest = verifier.compute(b"payload", HashAlgorithm.SHA256)
    assert verifier.verify(b"payload", "sha256", digest.upper()).matches
    failed = verifier.verify(b"payload", "sha256", SHA256_B)
    assert not failed.matches
    assert failed.algorithm is HashAlgorithm.SHA256
    assert failed.verdict == "mismatch"
    with pytest.raises(ValidationError, match="unknown hash algorithm"):
        verifier.compute(b"x", "sha999")


def test_hash_verifier_record_and_manifest() -> None:
    verifier = HashVerifier()
    data = b"capture"
    digest = verifier.compute(data, HashAlgorithm.SHA256)
    record = sample_record(digest=digest, size=len(data))
    results = verifier.verify_record(record, data)
    assert len(results) == 1
    assert results[0].matches
    multiple = verifier.verify_record(
        record, data, (HashAlgorithm.SHA256, HashAlgorithm.MD5, HashAlgorithm.SHA1)
    )
    assert len(multiple) == 3
    assert all(item.matches for item in multiple)
    manifest = verifier.verify_manifest(
        data, {"md5": verifier.compute(data, "md5"), "sha256": digest}
    )
    assert all(item.matches for item in manifest)
    assert [item.algorithm.value for item in manifest] == ["md5", "sha256"]


def test_hash_verifier_chain_digest_is_stable() -> None:
    first = HashVerifier.chain_digest(("a", "b", "c"))
    assert first == HashVerifier.chain_digest(("a", "b", "c"))
    assert first != HashVerifier.chain_digest(("c", "b", "a"))
    assert len(first) == 64


def test_custody_graph_builds_valid_chain() -> None:
    graph = CustodyGraph("ev-1", clock=frozen_clock())
    assert len(graph) == 0
    assert graph.last_hash == CustodyGraph.genesis_hash("ev-1")
    first = graph.append("alice", CustodyAction.ACQUIRED)
    assert first.from_hash == graph.genesis_hash("ev-1")
    second = graph.append("bob", "transferred")
    assert second.from_hash == first.to_hash
    assert graph.verify().valid
    assert graph.verify().length == 2
    assert graph.require_intact() is None
    assert graph.entries == (first, second)


def test_custody_graph_detects_tamper_and_broken_link() -> None:
    graph = CustodyGraph("ev-1", clock=frozen_clock())
    graph.append("alice", "acquired")
    graph.append("bob", "transferred")
    graph.append("carol", "analyzed")
    tampered = CustodyGraph.tampered_copy(graph.entries, 1, "mallory")
    result = CustodyGraph.verify_chain(tampered, graph.genesis_hash("ev-1"), "ev-1")
    assert not result.valid
    assert result.broken_index == 1
    assert result.issues
    mutated = (
        graph.entries[0],
        CustodyEntry.from_dict({**graph.entries[1].to_dict(), "from_hash": SHA256_A}),
    )
    broken = CustodyGraph.verify_chain(mutated, graph.genesis_hash("ev-1"), "ev-1")
    assert not broken.valid
    restored = CustodyGraph.from_entries("ev-1", graph.entries)
    assert restored.verify().valid


def test_custody_graph_require_intact_raises() -> None:
    graph = CustodyGraph("ev-9", clock=frozen_clock())
    graph.append("alice", "acquired")
    bad = CustodyGraph.from_entries("ev-9", CustodyGraph.tampered_copy(graph.entries, 0, "mallory"))
    assert not bad.verify().valid
    with pytest.raises(ChainIntegrityError, match="broken at entry 0"):
        bad.require_intact()


def test_custody_graph_timeline_and_serialization() -> None:
    clock = frozen_clock()
    graph = CustodyGraph("ev-1", clock=clock)
    graph.append("alice", "acquired", "2024-05-01T14:00:00.000Z")
    graph.append("bob", "transferred", "2024-05-01T12:30:00.000Z")
    assert [entry.actor for entry in graph.timeline()] == ["bob", "alice"]
    clock.advance(timedelta(minutes=1))
    assert clock.iso().endswith("Z")
    payload = graph.to_dict()
    assert payload["evidence_id"] == "ev-1"
    assert payload["verification"]["valid"] is True
    assert len(payload["entries"]) == 2
    with pytest.raises(ValidationError, match="evidence_id"):
        CustodyGraph("  ")


def test_bundle_differ_added_removed_changed() -> None:
    left = {
        "ev-1": sample_record(),
        "ev-2": sample_record("old.bin", SHA256_B),
        "ev-3": sample_record("gone.bin", SHA256_A),
    }
    right = {
        "ev-1": sample_record(),
        "ev-2": sample_record("new.bin", SHA256_B),
        "ev-4": sample_record("fresh.bin", SHA256_A),
    }
    differ = BundleDiffer()
    diff = differ.compare(left, right)
    assert diff.added == ("ev-4",)
    assert diff.removed == ("ev-3",)
    assert diff.changed == ("ev-2",)
    assert diff.unchanged == ("ev-1",)
    assert not diff.is_empty
    assert diff.summary()["field_changes"] == 1
    assert diff.to_dict()["changes"][0]["field"] == "name"


def test_bundle_differ_sequence_input_and_field_changes() -> None:
    before = sample_record(name="a.bin", digest=SHA256_A, size=5)
    after = sample_record(name="a.bin", digest=SHA256_B, size=6)
    diff = BundleDiffer().compare([before], [after])
    assert diff.changed == ("ev-1",)
    changes = BundleDiffer().field_changes(before, after)
    assert [item.field for item in changes] == ["size", "sha256"]
    assert changes[0].before == "5"
    assert changes[0].after == "6"
    assert DiffItem("ev", "tags", "a,b", "a").to_dict()["after"] == "a"
    empty = BundleDiffer().compare([before], [before])
    assert empty.is_empty
    assert empty.summary()["unchanged"] == 1


def test_inspection_pipeline_inspects_and_notes() -> None:
    data = b"hello world\x00tail"
    digest = HashVerifier().compute(data, HashAlgorithm.SHA256)
    record = sample_record(digest=digest, size=len(data))
    pipeline = InspectionPipeline(clock=frozen_clock())
    result = pipeline.inspect(record, data, max_rows=1)
    assert len(result.hex_rows) == 1
    assert result.cell_count == 16
    assert [hit.value for hit in result.strings] == ["hello world", "tail"]
    assert result.all_verified
    assert result.notes == ()
    assert result.generated_at.endswith("Z")
    assert_verified(result)


def test_inspection_pipeline_reports_size_and_hash_mismatch() -> None:
    record = sample_record(digest=SHA256_A, size=999)
    result = InspectionPipeline(clock=frozen_clock()).inspect(record, b"abc")
    assert not result.all_verified
    assert any("declared size" in note for note in result.notes)
    assert any("digest" in note for note in result.notes)
    with pytest.raises(HashMismatchError, match="failed digest verification"):
        assert_verified(result)


def test_inspection_pipeline_bundle_is_sorted() -> None:
    first = EvidenceRecord("ev-b", "b.bin", 3, SHA256_A, "t")
    second = EvidenceRecord("ev-a", "a.bin", 3, SHA256_B, "t")
    results = InspectionPipeline(clock=frozen_clock()).inspect_bundle(
        [first, second], {"ev-a": b"abc", "ev-b": b"xyz"}
    )
    assert [result.evidence_id for result in results] == ["ev-a", "ev-b"]


def test_chain_integrity_result_helpers() -> None:
    result = ChainIntegrityResult(valid=True, length=1)
    assert result.headline == "chain intact"
    assert result.to_dict()["broken_index"] == -1
    assert StringExtractor(min_length=1).is_printable(ord("z"))
