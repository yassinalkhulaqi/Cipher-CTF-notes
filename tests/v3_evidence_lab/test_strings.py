"""Tests for printable-string extraction."""

from __future__ import annotations

from io import BytesIO

import pytest

from redscribe.v3.evidence_lab.errors import InvalidInputError, UnsupportedEncodingError
from redscribe.v3.evidence_lab.strings import (
    classify_hit,
    encoding_from_name,
    is_printable_byte,
    is_printable_unit,
    merge_hits,
    scan_bytes,
    scan_stream,
    string_summary,
)
from redscribe.v3.evidence_lab.types import StringEncoding


def test_encoding_parsing() -> None:
    assert encoding_from_name("ascii") is StringEncoding.ASCII
    assert encoding_from_name("UTF-16LE") is StringEncoding.UTF16LE
    assert encoding_from_name("utf-16-be") is StringEncoding.UTF16BE
    with pytest.raises(UnsupportedEncodingError):
        encoding_from_name("ebcdic")


def test_printable_predicates() -> None:
    assert is_printable_byte(ord("a")) is True
    assert is_printable_byte(0x00) is False
    assert is_printable_byte(0x09) is True
    assert is_printable_byte(0x09, allow_whitespace=False) is False
    assert is_printable_unit(0x41) is True
    assert is_printable_unit(0x0100) is False


def test_classify_hit_variants() -> None:
    assert classify_hit("https://example.com/a") == "url"
    assert classify_hit("user@example.com") == "email"
    assert classify_hit("192.168.1.10") == "ipv4"
    assert classify_hit("/etc/passwd") == "path"
    assert classify_hit("C:\\Windows\\System32") == "path"
    assert classify_hit("deadbeefdeadbeef") == "hex"
    assert classify_hit("QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=") == "base64"
    assert classify_hit("hello world") == "plain"


def test_scan_bytes_basic_runs() -> None:
    data = b"\x00\x01HELLO\x00world!\xff"
    scan = scan_bytes(data, min_length=3)
    assert [hit.text for hit in scan.hits] == ["HELLO", "world!"]
    assert scan.hits[0].offset == 2
    assert scan.hits[1].offset == 8
    assert scan.bytes_scanned == len(data)
    assert scan.counts == {"plain": 2}


def test_scan_bytes_respects_min_length() -> None:
    scan = scan_bytes(b"a\x00bb\x00ccc\x00dddd", min_length=4)
    assert scan.texts() == ("dddd",)


def test_scan_bytes_offset_base() -> None:
    scan = scan_bytes(b"abcdef\x00", min_length=3, offset_base=0x1000)
    assert scan.hits[0].offset == 0x1000
    assert scan.hits[0].end == 0x1006


def test_scan_bytes_max_hits_truncates() -> None:
    data = b"alpha\x00beta\x00gamma\x00delta\x00"
    scan = scan_bytes(data, min_length=3, max_hits=2)
    assert len(scan.hits) == 2
    assert scan.truncated is True


def test_scan_bytes_max_string_length() -> None:
    scan = scan_bytes(b"x" * 100, min_length=4, max_string_length=10)
    assert scan.hits[0].text == "x" * 10
    assert scan.hits[0].length == 100


def test_scan_bytes_whitespace_only_is_rejected() -> None:
    scan = scan_bytes(b"\t\t\t\t\t\n\n\n\n", min_length=3)
    assert scan.hits == ()


def test_scan_bytes_utf16_le() -> None:
    data = "HELLO".encode("utf-16-le") + b"\x00\x00" + "WORLD".encode("utf-16-le")
    scan = scan_bytes(data, min_length=3, encoding=StringEncoding.UTF16LE)
    assert "HELLO" in scan.texts()
    assert "WORLD" in scan.texts()
    assert all(hit.encoding is StringEncoding.UTF16LE for hit in scan.hits)


def test_scan_bytes_utf16_be() -> None:
    data = "ABCD".encode("utf-16-be")
    scan = scan_bytes(data, min_length=3, encoding="utf16be")
    assert scan.texts() == ("ABCD",)


def test_scan_stream_matches_in_memory_scan() -> None:
    prefix = b"\x00\x01" + b"hello stream world!!" + b"\x00" + b"second run here"
    expected = scan_bytes(prefix, min_length=5)
    with BytesIO(prefix) as stream:
        streamed = scan_stream(stream, min_length=5, chunk_size=7)
    assert streamed.texts() == expected.texts()
    assert [hit.offset for hit in streamed.hits] == [hit.offset for hit in expected.hits]


def test_scan_stream_utf16_across_chunks() -> None:
    data = "REAMCONSTANT".encode("utf-16-le")
    with BytesIO(data) as stream:
        scan = scan_stream(stream, min_length=6, encoding=StringEncoding.UTF16LE, chunk_size=3)
    assert any("REAMCONSTANT" in text for text in scan.texts())


def test_scan_stream_limits_bytes() -> None:
    data = b"aaaaaaaaaa\x00bbbbbbbbbb"
    with BytesIO(data) as stream:
        scan = scan_stream(stream, min_length=3, max_bytes=8, chunk_size=4)
    assert scan.bytes_scanned == 8
    assert scan.truncated is True
    assert [hit.text for hit in scan.hits] == ["aaaaaaaa"]


def test_merge_hits_joins_adjacent_runs() -> None:
    data = b"foo bar"
    scan = scan_bytes(data, min_length=2)
    merged = merge_hits(scan.hits, max_gap=1)
    assert len(merged) == 1
    assert merged[0].text == "foo bar"
    assert merged[0].length == 7


def test_merge_hits_keeps_distant_runs() -> None:
    data = b"foo\x00\x00bar"
    scan = scan_bytes(data, min_length=2)
    merged = merge_hits(scan.hits, max_gap=1)
    assert len(merged) == 2


def test_string_summary() -> None:
    scan = scan_bytes(b"abcde\x00abcdef\x00https://x.test", min_length=3)
    summary = string_summary(scan)
    assert summary["count"] == 3
    assert summary["counts"]["url"] == 1
    assert summary["longest"] == 14


def test_scan_rejects_invalid_parameters() -> None:
    with pytest.raises(InvalidInputError):
        scan_bytes(b"abc", min_length=0)
    with pytest.raises(InvalidInputError):
        scan_bytes(b"abc", max_hits=0)
    with BytesIO(b"abc") as stream, pytest.raises(InvalidInputError):
        scan_stream(stream, max_bytes=0)
