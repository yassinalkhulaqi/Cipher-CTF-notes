"""Tests for magic-byte classification."""

from __future__ import annotations

from io import BytesIO

import pytest

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.magic import (
    SIGNATURES,
    MagicSignature,
    category_for,
    classify_bytes,
    classify_stream,
    extension_for,
    media_type_label,
    signature_table,
)


def test_signature_table_is_usable() -> None:
    assert len(SIGNATURES) >= 20
    assert any(rule.media_type == "image/png" for rule in SIGNATURES)
    assert any(rule.mask for rule in SIGNATURES)
    table = signature_table()
    assert len(table) == len(SIGNATURES)
    assert all(set(item) >= {"signature", "media_type", "category"} for item in table)


def test_classify_png_and_jpeg() -> None:
    png = classify_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert png.media_type == "image/png"
    assert png.category.value == "image"
    assert png.extension_hint == "png"
    assert png.primary is not None
    assert png.primary.confidence == 1.0
    jpeg = classify_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    assert jpeg.media_type == "image/jpeg"


def test_classify_masked_signature() -> None:
    webp = b"RIFF\x20\x00\x00\x00WEBPVP8 "
    result = classify_bytes(webp)
    assert result.media_type == "image/webp"
    mp4 = b"\x00\x00\x00\x28ftypisom"
    assert classify_bytes(mp4).media_type == "video/mp4"


def test_classify_archives_and_binaries() -> None:
    assert classify_bytes(b"PK\x03\x04more").media_type == "application/zip"
    assert classify_bytes(b"\x1f\x8b\x08\x00").media_type == "application/gzip"
    assert classify_bytes(b"\x7fELF\x02\x01\x01").category.value == "executable"
    assert classify_bytes(b"SQLite format 3\x00data").category.value == "database"


def test_classify_unknown() -> None:
    result = classify_bytes(b"\x01\x02\x03\x04unknown payload")
    assert result.primary is None
    assert result.media_type == "application/octet-stream"
    assert result.category.value == "unknown"
    assert result.extension_hint == ""


def test_classify_stream_reads_only_prefix() -> None:
    payload = b"%PDF-1.7\n" + b"x" * 4096
    with BytesIO(payload) as stream:
        stream.seek(5)
        result = classify_stream(stream, header_bytes=16)
        assert stream.tell() == 5
    assert result.media_type == "application/pdf"
    assert result.header_bytes == 16


def test_classify_stream_rejects_bad_header_size() -> None:
    with BytesIO(b"data") as stream, pytest.raises(InvalidInputError):
        classify_stream(stream, header_bytes=0)


def test_magic_signature_direct_matching() -> None:
    rule = MagicSignature(b"\x7fELF", "application/x-executable", "ELF", "executable", "elf")
    assert rule.matches(b"\x7fELF\x02\x01")
    assert not rule.matches(b"MZ\x90\x00")
    assert rule.to_match().signature_hex == "7f454c46"


def test_mask_length_mismatch_does_not_match() -> None:
    rule = MagicSignature(b"ABCD", "x/test", "test", "data", "bin", mask=b"\xff\xff")
    assert not rule.matches(b"ABCD")


def test_lookup_helpers() -> None:
    assert extension_for("image/png") == "png"
    assert extension_for("application/unknown") == "bin"
    assert category_for("application/pdf").value == "document"
    assert category_for("application/unknown").value == "unknown"
    result = classify_bytes(b"\x89PNG\r\n\x1a\n")
    assert media_type_label(result) == "Portable Network Graphics"
    assert media_type_label(classify_bytes(b"\x01\x02")) == "Unknown binary"
