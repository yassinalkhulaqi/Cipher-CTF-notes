"""Thumbnail and preview metadata extraction without external dependencies."""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping

from redscribe.v2.evidence.mime import is_image, is_textual, normalize_mime
from redscribe.v2.evidence.models import ThumbnailMetadata
from redscribe.v2.evidence.validation import now_iso

PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![s])")
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}
MAX_DIMENSION = 100_000


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read width and height from a PNG header."""
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if 0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION:
        return width, height
    return None


def gif_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read logical screen dimensions from a GIF header."""
    if len(data) < 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        return None
    width, height = struct.unpack("<HH", data[6:10])
    if 0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION:
        return width, height
    return None


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Find the first JPEG start-of-frame marker and read its dimensions."""
    if len(data) < 4 or not data.startswith(b"\xff\xd8\xff"):
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if marker not in JPEG_SOF_MARKERS:
            if offset + 4 > len(data):
                return None
            length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
            offset += 2 + length
            continue
        height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
        if 0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION:
            return width, height
        return None
    return None


def webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read dimensions from a lossy or lossless WebP header."""
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8 ":
        width, height = struct.unpack("<HH", data[26:30])
    elif chunk == b"VP8L":
        if len(data) < 25:
            return None
        packed = int.from_bytes(data[21:25], "little")
        width = (packed & 0x3FFF) + 1
        height = ((packed >> 14) & 0x3FFF) + 1
    elif chunk == b"VP8X":
        if len(data) < 30:
            return None
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
    else:
        return None
    if 0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION:
        return width, height
    return None


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return image dimensions for supported formats, if recognizable."""
    detectors = (png_dimensions, gif_dimensions, jpeg_dimensions, webp_dimensions)
    for detector in detectors:
        result = detector(data)
        if result is not None:
            return result
    return None


def pdf_page_count(data: bytes) -> int:
    """Estimate the PDF page count by counting page objects."""
    if not data.startswith(b"%PDF-"):
        return 0
    return len(PDF_PAGE_RE.findall(data[:8_388_608]))


def preview_kind_for_mime(mime_type: str, *, filename: str = "") -> str:
    """Return the UI preview strategy for a MIME type."""
    normalized = normalize_mime(mime_type)
    if is_image(normalized):
        return "image"
    if normalized == "application/pdf":
        return "pdf"
    if is_textual(normalized):
        if filename.casefold().endswith((".log", ".jsonl")):
            return "log"
        return "text"
    if normalized.startswith("audio/"):
        return "audio"
    if normalized.startswith("video/"):
        return "video"
    if normalized in {"application/zip", "application/x-tar", "application/gzip"}:
        return "archive"
    return "icon"


def supports_preview(mime_type: str) -> bool:
    """Return whether a MIME type has a meaningful preview mode."""
    return preview_kind_for_mime(mime_type) != "icon"


def thumbnail_metadata(
    data: bytes,
    *,
    mime_type: str,
    source_sha256: str,
    filename: str = "",
    generated_at: str = "",
) -> ThumbnailMetadata:
    """Build thumbnail metadata from file bytes and a detected MIME type."""
    kind = preview_kind_for_mime(mime_type, filename=filename)
    width = 0
    height = 0
    page_count = 0
    note = ""
    available = kind != "icon"
    normalized = normalize_mime(mime_type)
    if is_image(normalized):
        dimensions = image_dimensions(data)
        if dimensions is None:
            available = False
            note = "Image dimensions could not be read"
        else:
            width, height = dimensions
    elif normalized == "application/pdf":
        page_count = pdf_page_count(data)
        if page_count == 0:
            note = "PDF page tree could not be read"
    elif kind == "archive":
        note = "Archive contents are listed on the detail view"
    return ThumbnailMetadata(
        available=available,
        preview_kind=kind,
        width=width,
        height=height,
        page_count=page_count,
        source_sha256=source_sha256,
        generated_at=generated_at or now_iso(),
        note=note,
    )


def unavailable_thumbnail(*, reason: str = "No bytes available") -> ThumbnailMetadata:
    """Return placeholder metadata for records without file bytes."""
    return ThumbnailMetadata(
        available=False,
        preview_kind="icon",
        generated_at=now_iso(),
        note=reason,
    )


def thumbnail_summary(value: Mapping[str, object] | ThumbnailMetadata) -> str:
    """Render a short human-readable thumbnail description."""
    thumbnail = (
        value if isinstance(value, ThumbnailMetadata) else ThumbnailMetadata.from_dict(value)
    )
    if not thumbnail.available:
        return thumbnail.note or "No preview"
    if thumbnail.width and thumbnail.height:
        return f"{thumbnail.preview_kind} · {thumbnail.width}×{thumbnail.height}"
    if thumbnail.page_count:
        return f"{thumbnail.preview_kind} · {thumbnail.page_count} pages"
    return thumbnail.preview_kind


def aspect_ratio(thumbnail: ThumbnailMetadata) -> float:
    """Return width divided by height, or zero when unknown."""
    if thumbnail.width <= 0 or thumbnail.height <= 0:
        return 0.0
    return round(thumbnail.width / thumbnail.height, 4)


def is_portrait(thumbnail: ThumbnailMetadata) -> bool:
    """Return whether the preview's dimensions are portrait-oriented."""
    ratio = aspect_ratio(thumbnail)
    return 0 < ratio < 1


def is_landscape(thumbnail: ThumbnailMetadata) -> bool:
    """Return whether the preview's dimensions are landscape-oriented."""
    ratio = aspect_ratio(thumbnail)
    return ratio > 1
