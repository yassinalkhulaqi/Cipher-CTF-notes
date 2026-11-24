"""Tests for dual hashing, integrity verification, and byte ranges."""

from __future__ import annotations

import hashlib
from io import BytesIO

import pytest

from redscribe.v3.evidence_lab.errors import InvalidInputError, InvalidRangeError
from redscribe.v3.evidence_lab.hashing import (
    compare_panels,
    compute_panel,
    digest_equal,
    hash_stream_panel,
    mask_hex,
    normalize_expected,
    panel_digests,
    panel_fingerprint,
    verify_panel,
)
from redscribe.v3.evidence_lab.ranges import (
    format_content_range,
    is_satisfiable,
    parse_range_header,
    parse_single_range,
    range_bounds,
    read_range,
    read_ranges,
    satisfy_ranges,
    total_requested,
)
from redscribe.v3.evidence_lab.types import IntegrityState, RangeSpec


def test_hash_panel_matches_stdlib() -> None:
    data = b"evidence pixels \x00\xff"
    panel = compute_panel(data, computed_at="2026-01-01T00:00:00Z")
    assert panel.sha256 == hashlib.sha256(data).hexdigest()
    assert panel.blake2b == hashlib.blake2b(data, digest_size=32).hexdigest()
    assert panel.size_bytes == len(data)
    assert panel.computed_at == "2026-01-01T00:00:00Z"
    assert panel.blake2b_size == 32
    assert panel.combined_id.startswith(panel.sha256)


def test_hash_panel_streaming_matches_memory() -> None:
    data = bytes(range(256)) * 20
    with BytesIO(data) as stream:
        streamed = hash_stream_panel(stream, chunk_size=4096)
    assert streamed == compute_panel(data)


def test_hash_panel_custom_digest_size() -> None:
    panel = compute_panel(b"abc", digest_size=16)
    assert len(panel.blake2b) == 32
    assert panel.blake2b_size == 16
    assert "..." in panel.as_dict()["blake2b_short"]


def test_panel_digests_and_fingerprint() -> None:
    panel = compute_panel(b"abc")
    digests = panel_digests(panel)
    assert [digest.algorithm for digest in digests] == ["sha256", "blake2b"]
    assert panel_fingerprint(panel).startswith("sha256:")
    assert mask_hex(panel.sha256, visible=6).startswith(panel.sha256[:6])


def test_verify_panel_states() -> None:
    panel = compute_panel(b"abc")
    assert verify_panel(panel).state is IntegrityState.UNVERIFIED
    good = verify_panel(
        panel,
        stored_sha256=panel.sha256,
        stored_blake2b=panel.blake2b,
        stored_size=3,
    )
    assert good.state is IntegrityState.VERIFIED
    assert good.ok is True
    bad = verify_panel(panel, stored_sha256="0" * 64, stored_size=99)
    assert bad.state is IntegrityState.MISMATCH
    assert "sha256 mismatch" in bad.reasons
    assert "size mismatch" in bad.reasons


def test_verify_panel_with_normalized_expectations() -> None:
    panel = compute_panel(b"abc")
    badge = verify_panel(panel, stored_sha256="  " + panel.sha256.upper() + "  ")
    assert badge.sha256_match is True
    assert badge.blake2b_match is False


def test_digest_helpers() -> None:
    panel = compute_panel(b"abc")
    assert digest_equal(panel.sha256, panel.sha256.upper()) is True
    assert digest_equal(panel.sha256, "") is False
    assert normalize_expected("zz" * 32, length=64) == ""
    assert normalize_expected("ab" * 32, length=64) == "ab" * 32
    compared = compare_panels(panel, compute_panel(b"abc"))
    assert compared == {"sha256": True, "blake2b": True, "size": True, "same_digest_size": True}


def test_hash_invalid_parameters() -> None:
    with BytesIO(b"abc") as stream:
        with pytest.raises(InvalidInputError):
            hash_stream_panel(stream, chunk_size=8)
        with pytest.raises(InvalidInputError):
            hash_stream_panel(stream, digest_size=4)


def test_parse_range_header_variants() -> None:
    specs = parse_range_header("bytes=0-9,20-, -5", size=100)
    assert specs[0] == RangeSpec(start=0, end=9)
    assert specs[1] == RangeSpec(start=20, end=None)
    assert specs[2] == RangeSpec(start=5, end=None, suffix=True)
    assert parse_single_range("3-7", size=10).length == 5
    assert parse_single_range("-4", size=10).suffix is True


def test_parse_range_header_rejects_invalid() -> None:
    with pytest.raises(InvalidRangeError):
        parse_range_header("items=0-9", size=100)
    with pytest.raises(InvalidRangeError):
        parse_range_header("bytes=9-3", size=100)
    with pytest.raises(InvalidRangeError):
        parse_range_header("bytes=-0", size=100)
    with pytest.raises(InvalidRangeError):
        parse_range_header("bytes=", size=100)


def test_range_bounds_and_merging() -> None:
    specs = (
        RangeSpec(start=0, end=9),
        RangeSpec(start=5, end=14),
        RangeSpec(start=90, end=None),
    )
    assert range_bounds(specs[0], 100) == (0, 10)
    assert range_bounds(RangeSpec(start=3, suffix=True), 100) == (97, 100)
    assert satisfy_ranges(specs, 100) == ((0, 15), (90, 100))
    assert total_requested(specs, 100) == 25
    assert is_satisfiable(specs, 100) is True
    assert is_satisfiable((RangeSpec(start=200, end=300),), 100) is False


def test_read_range_is_bounded() -> None:
    with BytesIO(bytes(range(100))) as stream:
        chunk = read_range(stream, 95, 20, total_size=100, max_bytes=64)
        assert chunk.length == 5
        assert chunk.start == 95
        assert chunk.end == 100
        assert chunk.content_range == "bytes 95-99/100"
        assert chunk.as_dict()["preview_hex"] == "5f60616263"
        with pytest.raises(InvalidRangeError):
            read_range(stream, 0, 100, max_bytes=10)


def test_read_ranges_multiple_and_budget() -> None:
    specs = parse_range_header("bytes=0-3,96-", size=100)
    with BytesIO(bytes(range(100))) as stream:
        chunks = read_ranges(stream, specs, size=100, max_bytes=64)
    assert [chunk.length for chunk in chunks] == [4, 4]
    assert chunks[1].data == bytes(range(96, 100))
    with BytesIO(bytes(range(100))) as stream, pytest.raises(InvalidRangeError):
        read_ranges(stream, parse_range_header("bytes=0-99", size=100), max_bytes=10)


def test_content_range_helper() -> None:
    assert format_content_range(0, 0, 100) == "bytes 0-0/100"
    assert format_content_range(10, 20, 100) == "bytes 10-19/100"
