from __future__ import annotations

import hashlib
import io
import struct
from pathlib import Path

import pytest

from redscribe.v2.evidence.errors import ValidationError
from redscribe.v2.evidence.hashing import (
    canonical_digest,
    canonical_json,
    chain_hash,
    decode_base64_payload,
    digest_label,
    digest_matches,
    encode_base64_payload,
    hash_bytes,
    hash_file,
    hash_stream,
    hash_with,
    mask_digest,
    md5_hex,
    sha256_hex,
    verify_digest,
    verify_digest_set,
)
from redscribe.v2.evidence.mime import (
    detect_magic_mime,
    detect_mime,
    evidence_kind_for_mime,
    extension_for_mime,
    is_archive,
    is_image,
    is_probably_text,
    is_textual,
    mime_category,
    mime_conflict,
    mime_from_path,
    normalize_mime,
)
from redscribe.v2.evidence.models import EvidenceKind, MimeSource
from redscribe.v2.evidence.thumbnails import (
    gif_dimensions,
    image_dimensions,
    jpeg_dimensions,
    pdf_page_count,
    png_dimensions,
    preview_kind_for_mime,
    supports_preview,
    thumbnail_metadata,
    thumbnail_summary,
    unavailable_thumbnail,
    webp_dimensions,
)
from redscribe.v2.evidence.validation import (
    coerce_bool,
    normalize_metadata,
    normalize_tags,
    normalize_timestamp,
    sanitize_filename,
    validate_evidence_id,
    validate_hex_digest,
    validate_limit,
)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    + struct.pack(">I", 13)
    + b"IHDR"
    + struct.pack(">II", 640, 480)
    + b"\x08\x06\x00\x00\x00"
)
GIF_BYTES = b"GIF89a" + struct.pack("<HH", 32, 64) + b"\x00" * 20
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Page >>\nendobj\n2 0 obj\n<< /Type /Pages >>\nendobj\n"


def test_hash_bytes_returns_both_digests_and_size() -> None:
    payload = b"evidence payload"
    digests = hash_bytes(payload, computed_at="2026-01-01T00:00:00Z")
    assert digests.sha256 == hashlib.sha256(payload).hexdigest()
    assert digests.md5 == hashlib.md5(payload).hexdigest()
    assert digests.size_bytes == len(payload)
    assert digests.computed_at == "2026-01-01T00:00:00Z"


def test_hash_helpers_agree_across_bytes_stream_and_file(tmp_path: Path) -> None:
    payload = b"a" * 100_000
    path = tmp_path / "payload.bin"
    path.write_bytes(payload)
    expected = hash_bytes(payload)
    assert sha256_hex(payload) == expected.sha256
    assert md5_hex(payload) == expected.md5
    assert hash_with(payload, "SHA256") == expected.sha256
    assert hash_stream(io.BytesIO(payload)) == expected
    assert hash_file(path) == expected
    assert verify_digest(payload, expected.sha256)
    assert verify_digest_set(payload, expected) == (True, True)


def test_hash_helpers_reject_bad_inputs() -> None:
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        hash_with(b"x", "sha1")
    assert not verify_digest(b"x", "")
    assert not verify_digest(b"x", hashlib.sha256(b"y").hexdigest())
    assert digest_matches("ABC", "abc")
    assert not digest_matches(None, "abc")


def test_canonical_json_and_chain_hash_are_deterministic() -> None:
    left = {"b": 2, "a": [1, 3]}
    right = {"a": [1, 3], "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_digest(left) == canonical_digest(right)
    assert chain_hash("0" * 64, left) != chain_hash("1" * 64, left)
    assert chain_hash("0" * 64, left) == chain_hash("0" * 64, right)


def test_base64_and_display_helpers() -> None:
    encoded = encode_base64_payload(b"payload")
    assert decode_base64_payload(encoded, max_bytes=100) == b"payload"
    with pytest.raises(ValueError, match="Invalid base64"):
        decode_base64_payload("not base64", max_bytes=100)
    with pytest.raises(ValueError, match="exceeds"):
        decode_base64_payload(encoded, max_bytes=2)
    assert mask_digest("a" * 64) == "aaaaaaaa…aaaaaaaa"
    assert digest_label("sha256") == "SHA-256"
    assert digest_label("md5") == "MD5 (compatibility)"


def test_mime_detection_prefers_magic_bytes() -> None:
    png = detect_mime(PNG_BYTES, filename="photo.jpg", declared="image/jpeg")
    assert png.mime_type == "image/png"
    assert png.source is MimeSource.MAGIC
    assert png.extension == ".jpg"
    assert detect_magic_mime(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert detect_magic_mime(b"SQLite format 3\x00") == "application/x-sqlite3"


def test_mime_detection_handles_text_json_and_extension_fallback() -> None:
    text = detect_mime(b"just plain text", filename="notes.txt")
    assert text.mime_type == "text/plain"
    assert text.source is MimeSource.TEXT_SNIFF
    json_payload = detect_mime(b'{"case": "demo"}', filename="notes.bin")
    assert json_payload.mime_type == "application/json"
    binary = detect_mime(b"\xff\x00\xfe\x02", filename="archive.zip")
    assert binary.mime_type == "application/zip"
    assert binary.source is MimeSource.EXTENSION
    assert (
        detect_mime(b"\xff\x00", filename="mystery.unknownext").mime_type
        == "application/octet-stream"
    )


def test_mime_classification_helpers() -> None:
    assert normalize_mime("Text/Plain; charset=utf-8") == "text/plain"
    assert normalize_mime("not-a-type") == "application/octet-stream"
    assert mime_category("image/png") == "image"
    assert mime_category("application/x-sqlite3") == "database"
    assert evidence_kind_for_mime("text/plain") is EvidenceKind.DOCUMENT
    assert evidence_kind_for_mime("image/png") is EvidenceKind.IMAGE
    assert is_textual("application/json")
    assert not is_textual("image/png")
    assert is_image("image/gif")
    assert is_archive("application/zip")
    assert extension_for_mime("image/png") == ".png"
    assert mime_from_path("/tmp/file.PNG").mime_type == "image/png"
    assert mime_conflict(detect_mime(PNG_BYTES, filename="x.png"), "application/pdf")


def test_text_sniffing_rejects_control_bytes() -> None:
    assert is_probably_text(b"hello")
    assert not is_probably_text(b"hello\x00\x01")


def test_thumbnail_dimensions_for_common_formats() -> None:
    assert png_dimensions(PNG_BYTES) == (640, 480)
    assert gif_dimensions(GIF_BYTES) == (32, 64)
    assert image_dimensions(PNG_BYTES) == (640, 480)
    assert webp_dimensions(b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 12) is None
    assert png_dimensions(b"not png") is None


def test_jpeg_dimension_parser_handles_marker_segments() -> None:
    jpeg = (
        b"\xff\xd8"
        + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xc0\x00\x11\x08\x01\x2c\x02\x58\x03\x01\x22\x00"
    )
    assert jpeg_dimensions(jpeg) == (600, 300)


def test_pdf_page_count_and_thumbnail_metadata() -> None:
    assert pdf_page_count(PDF_BYTES) == 1
    metadata = thumbnail_metadata(
        PDF_BYTES,
        mime_type="application/pdf",
        source_sha256="a" * 64,
        filename="report.pdf",
    )
    assert metadata.available
    assert metadata.preview_kind == "pdf"
    assert metadata.page_count == 1
    assert thumbnail_summary(metadata).startswith("pdf")
    assert preview_kind_for_mime("text/plain", filename="access.log") == "log"
    assert supports_preview("image/png")
    assert not supports_preview("application/octet-stream")


def test_unavailable_thumbnail_placeholder() -> None:
    thumbnail = unavailable_thumbnail(reason="No bytes")
    assert not thumbnail.available
    assert thumbnail.preview_kind == "icon"
    assert thumbnail.note == "No bytes"


def test_validation_helpers_enforce_field_rules() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..") == "evidence.bin"
    assert normalize_tags("web, web; exploit") == ("web", "exploit")
    assert normalize_metadata({"a": "x\x00y", "b": {"c": 1}}) == {"a": "xy", "b": {"c": 1}}
    assert normalize_timestamp("2026-01-02T03:04:05Z") == "2026-01-02T03:04:05Z"
    assert coerce_bool("YES")
    assert not coerce_bool("off")
    assert validate_limit(None) == 50
    assert validate_evidence_id("ev_abc123")
    assert validate_hex_digest("A" * 64, length=64) == "a" * 64
    with pytest.raises(ValidationError, match="Invalid evidence id"):
        validate_evidence_id("x")
    with pytest.raises(ValidationError, match="hexadecimal"):
        validate_hex_digest("zz", length=64)
    with pytest.raises(ValidationError, match="between"):
        validate_limit(1_000)
