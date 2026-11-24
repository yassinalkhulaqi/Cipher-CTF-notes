"""Tests for bundle diffing, fingerprints, and thumbnail metadata."""

from __future__ import annotations

from io import BytesIO

import pytest

from redscribe.v3.entities import EntityRef
from redscribe.v3.evidence_lab.bundle import (
    build_bundle,
    bundle_fingerprint,
    bundle_index,
    changed_keys,
    diff_bundles,
    diff_size_total,
    entries_from_records,
    summarize_bundle,
)
from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.hashing import compute_panel
from redscribe.v3.evidence_lab.magic import classify_bytes
from redscribe.v3.evidence_lab.thumbnails import (
    make_ingest_record,
    make_thumbnail,
    preview_kind_for,
    read_preview,
    refresh_thumbnail,
    thumbnail_note,
)
from redscribe.v3.evidence_lab.types import BundleDeltaKind, BundleEntry, FileCategory


def entry(key: str, digest: str, size: int = 100) -> BundleEntry:
    return BundleEntry(key=key, sha256=digest, blake2b=digest[::-1], size_bytes=size)


def test_bundle_index_and_fingerprint() -> None:
    entries = (entry("b", "2" * 64), entry("a", "1" * 64))
    index = bundle_index(entries)
    assert list(index) == ["b", "a"]
    assert bundle_fingerprint(entries) == bundle_fingerprint(tuple(reversed(entries)))
    with pytest.raises(InvalidInputError):
        bundle_index((entry("a", "1"), entry("a", "2")))
    with pytest.raises(InvalidInputError):
        bundle_index((entry("", "1"),))


def test_entries_from_records_and_bundle_manifest() -> None:
    records = ({"key": "x", "sha256": "a" * 64, "size_bytes": 12, "label": "X"},)
    entries = entries_from_records(records)
    assert entries[0].label == "X"
    manifest = build_bundle(entries, label="case-01")
    assert manifest["count"] == 1
    assert manifest["total_bytes"] == 12
    assert manifest["label"] == "case-01"
    assert manifest["entries"][0]["key"] == "x"


def test_diff_bundles_all_kinds() -> None:
    left = (entry("same", "1" * 64, 10), entry("gone", "2" * 64, 20), entry("mod", "3" * 64, 30))
    right = (
        entry("same", "1" * 64, 10),
        entry("mod", "9" * 64, 45),
        entry("new", "4" * 64, 40),
    )
    diff = diff_bundles(left, right, left_id="before", right_id="after")
    assert diff.left_id == "before"
    assert diff.identical is False
    assert diff.counts == {"added": 1, "removed": 1, "modified": 1, "unchanged": 1}
    assert changed_keys(diff) == ("gone", "mod", "new")
    assert diff_size_total(diff) == 40 + 15 - 20
    kinds = {delta.key: delta.kind for delta in diff.deltas}
    assert kinds["new"] is BundleDeltaKind.ADDED
    assert kinds["gone"] is BundleDeltaKind.REMOVED
    assert kinds["mod"] is BundleDeltaKind.MODIFIED
    assert kinds["same"] is BundleDeltaKind.UNCHANGED
    assert diff.as_dict()["deltas"][0]["kind"] in {"added", "removed", "modified", "unchanged"}


def test_diff_bundles_identical() -> None:
    entries = (entry("a", "a" * 64), entry("b", "b" * 64))
    diff = diff_bundles(entries, entries)
    assert diff.identical is True
    assert diff.changed() == ()
    assert summarize_bundle(entries)["count"] == 2


def test_bundle_identity_falls_back_to_blake2b() -> None:
    item = BundleEntry(key="x", sha256="", blake2b="f" * 64)
    assert item.identity() == "f" * 64


def test_thumbnail_derivation() -> None:
    ref = EntityRef.of("evidence", "png-1", "logo")
    panel = compute_panel(b"\x89PNG\r\n\x1a\n" + b"data")
    file_class = classify_bytes(b"\x89PNG\r\n\x1a\n" + b"data")
    thumb = make_thumbnail(ref, file_class, panel, generated_at="2026-01-01T00:00:00Z")
    assert thumb.preview_kind == "image"
    assert thumb.category is FileCategory.IMAGE
    assert (thumb.width, thumb.height) == (320, 240)
    assert thumb.source_sha256 == panel.sha256
    assert "SHA-256" in thumbnail_note(file_class, panel)
    refreshed = refresh_thumbnail(thumb, generated_at="later", note="updated")
    assert refreshed.generated_at == "later"
    assert refreshed.note == "updated"


def test_thumbnail_for_unknown_and_text() -> None:
    panel = compute_panel(b"hello")
    unknown = classify_bytes(b"\x01\x02\x03")
    text = classify_bytes(b"SSH-")
    assert preview_kind_for(unknown) == "hex-map"
    assert preview_kind_for(text) == "text-excerpt"
    assert make_thumbnail(EntityRef.of("evidence", "u"), unknown, panel).available is True


def test_ingest_record_assembly() -> None:
    ref = EntityRef.of("evidence", "file-1")
    panel = compute_panel(b"abc")
    file_class = classify_bytes(b"abc")
    thumb = make_thumbnail(ref, file_class, panel)
    record = make_ingest_record(
        ref, "capture.bin", panel, file_class, thumb, tags=("ctf",), ingested_at="now"
    )
    assert record.size_bytes == 3
    assert record.tags == ("ctf",)
    assert record.as_dict()["filename"] == "capture.bin"
    with pytest.raises(InvalidInputError):
        make_ingest_record(ref, " ", panel, file_class, thumb)


def test_read_preview_bounded() -> None:
    with BytesIO(bytes(range(256))) as stream:
        preview = read_preview(stream, start=250, length=32, max_bytes=16, chunk_size=4)
    assert preview == bytes(range(250, 256))
    with pytest.raises(InvalidInputError), BytesIO(b"abc") as stream:
        read_preview(stream, start=-1)
