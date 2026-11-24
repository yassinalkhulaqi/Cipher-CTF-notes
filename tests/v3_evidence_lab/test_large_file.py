"""Memory-bound guarantees for 100 MB evidence streams."""

from __future__ import annotations

import hashlib
from typing import Any

from redscribe.v3.entities import EntityRef
from redscribe.v3.evidence_lab.entropy import estimate_stream_entropy
from redscribe.v3.evidence_lab.hashing import hash_stream_panel
from redscribe.v3.evidence_lab.hexdump import build_hex_window, stream_size
from redscribe.v3.evidence_lab.ranges import parse_range_header, read_ranges
from redscribe.v3.evidence_lab.service import EvidenceLabService
from redscribe.v3.evidence_lab.strings import scan_stream

HUNDRED_MB = 100 * 1024 * 1024


class SparseStream:
    """A virtual 100 MB stream that records its largest read request."""

    def __init__(self, size: int, *, fill: bytes = b"\x00") -> None:
        self.size = size
        self.fill = fill
        self.position = 0
        self.max_read = 0
        self.bytes_read = 0
        self.read_count = 0

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.position = offset
        elif whence == 1:
            self.position += offset
        elif whence == 2:
            self.position = self.size + offset
        return self.position

    def read(self, size: int = -1) -> bytes:
        amount = self.size - self.position if size < 0 else min(size, self.size - self.position)
        amount = max(0, amount)
        self.max_read = max(self.max_read, amount)
        self.bytes_read += amount
        self.read_count += 1
        self.position += amount
        return (self.fill * ((amount // len(self.fill)) + 1))[:amount]

    def as_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "max_read": self.max_read,
            "bytes_read": self.bytes_read,
            "reads": self.read_count,
        }


def test_stream_size_does_not_read() -> None:
    stream = SparseStream(HUNDRED_MB)
    assert stream_size(stream) == HUNDRED_MB
    assert stream.bytes_read == 0


def test_hash_100mb_in_bounded_chunks() -> None:
    stream = SparseStream(HUNDRED_MB)
    panel = hash_stream_panel(stream, chunk_size=64 * 1024)
    expected = hashlib.sha256()
    expected_blake = hashlib.blake2b(digest_size=32)
    block = b"\x00" * 64 * 1024
    for _ in range(HUNDRED_MB // (64 * 1024)):
        expected.update(block)
        expected_blake.update(block)
    assert panel.sha256 == expected.hexdigest()
    assert panel.blake2b == expected_blake.hexdigest()
    assert panel.size_bytes == HUNDRED_MB
    assert stream.max_read <= 64 * 1024
    assert stream.bytes_read == HUNDRED_MB


def test_hex_window_of_100mb_does_not_read_whole_file() -> None:
    stream = SparseStream(HUNDRED_MB, fill=b"ABCDEFGH")
    window = build_hex_window(
        stream,
        start=HUNDRED_MB - 64,
        length=64,
        bytes_per_row=16,
        chunk_size=1024,
    )
    assert window.total_bytes == HUNDRED_MB
    assert window.length == 64
    assert len(window.rows) == 4
    assert stream.max_read <= 1024
    assert stream.bytes_read <= 1024


def test_entropy_and_strings_sample_only_prefix() -> None:
    stream = SparseStream(HUNDRED_MB, fill=b"visible-text\x00")
    report = estimate_stream_entropy(stream, max_bytes=2048, chunk_size=512, total_bytes=HUNDRED_MB)
    assert report.sample_bytes == 2048
    assert report.total_bytes == HUNDRED_MB
    assert stream.max_read <= 512
    assert stream.bytes_read == 2048
    stream = SparseStream(HUNDRED_MB, fill=b"visible-text\x00")
    scan = scan_stream(stream, min_length=4, max_bytes=2048, chunk_size=512)
    assert scan.bytes_scanned == 2048
    assert stream.bytes_read == 2048


def test_range_read_near_end_of_100mb() -> None:
    stream = SparseStream(HUNDRED_MB)
    specs = parse_range_header(f"bytes={HUNDRED_MB - 32}-", size=HUNDRED_MB)
    chunks = read_ranges(stream, specs, size=HUNDRED_MB, max_bytes=4096)
    assert len(chunks) == 1
    assert chunks[0].length == 32
    assert chunks[0].start == HUNDRED_MB - 32
    assert stream.max_read <= 4096


def test_service_inspects_100mb_with_bounded_budget() -> None:
    stream = SparseStream(HUNDRED_MB)
    service = EvidenceLabService(
        max_window_bytes=512,
        max_scan_bytes=1024,
        entropy_sample_bytes=1024,
        chunk_size=64 * 1024,
    )
    report = service.inspect_stream(
        stream,
        ref=EntityRef.of("evidence", "huge"),
        hex_length=4096,
        min_string_length=4,
    )
    assert report.size_bytes == HUNDRED_MB
    assert report.hex_window is not None
    assert report.hex_window.length <= 512
    assert report.strings is not None
    assert report.strings.bytes_scanned <= 1024
    assert report.entropy is not None
    assert report.entropy.sample_bytes <= 1024
    assert stream.max_read <= 64 * 1024
