"""Thumbnail and metadata records for lab previews.

Previews are metadata-only: no image decoding library is required. The module
derives a preview kind and nominal dimensions from the magic classification and
provides a bounded byte reader for callers that render their own preview.
"""

from __future__ import annotations

from typing import BinaryIO

from redscribe.v3.entities import EntityRef
from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.types import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_PREVIEW_BYTES,
    FileCategory,
    FileClass,
    HashPanel,
    IngestRecord,
    ThumbnailRecord,
)

PREVIEW_DIMENSIONS: dict[FileCategory, tuple[int, int]] = {
    FileCategory.IMAGE: (320, 240),
    FileCategory.VIDEO: (320, 180),
    FileCategory.DOCUMENT: (210, 297),
    FileCategory.ARCHIVE: (128, 128),
    FileCategory.EXECUTABLE: (128, 128),
    FileCategory.AUDIO: (320, 96),
    FileCategory.DATABASE: (128, 128),
    FileCategory.TEXT: (320, 320),
    FileCategory.DATA: (128, 128),
    FileCategory.UNKNOWN: (128, 128),
}

PREVIEW_KINDS: dict[FileCategory, str] = {
    FileCategory.IMAGE: "image",
    FileCategory.VIDEO: "video-frame",
    FileCategory.DOCUMENT: "page",
    FileCategory.ARCHIVE: "archive-tree",
    FileCategory.EXECUTABLE: "byte-map",
    FileCategory.AUDIO: "waveform",
    FileCategory.DATABASE: "schema",
    FileCategory.TEXT: "text-excerpt",
    FileCategory.DATA: "hex-map",
    FileCategory.UNKNOWN: "hex-map",
}


def preview_kind_for(file_class: FileClass) -> str:
    """Return the preview renderer key for a classification."""
    return PREVIEW_KINDS.get(file_class.category, "hex-map")


def dimensions_for(file_class: FileClass) -> tuple[int, int]:
    """Return nominal preview dimensions for a classification."""
    return PREVIEW_DIMENSIONS.get(file_class.category, (128, 128))


def make_thumbnail(
    ref: EntityRef,
    file_class: FileClass,
    panel: HashPanel,
    *,
    generated_at: str = "",
    note: str = "",
    available: bool = True,
) -> ThumbnailRecord:
    """Build a thumbnail record from a classification and hash panel."""
    width, height = dimensions_for(file_class)
    return ThumbnailRecord(
        ref=ref,
        preview_kind=preview_kind_for(file_class),
        category=file_class.category,
        width=width,
        height=height,
        mime_type=file_class.media_type,
        source_sha256=panel.sha256,
        generated_at=generated_at,
        available=available,
        note=note,
    )


def make_ingest_record(
    ref: EntityRef,
    filename: str,
    panel: HashPanel,
    file_class: FileClass,
    thumbnail: ThumbnailRecord,
    *,
    tags: tuple[str, ...] = (),
    ingested_at: str = "",
    source: str = "local",
) -> IngestRecord:
    """Assemble an ingest record for the lab registry."""
    if not filename.strip():
        raise InvalidInputError("Ingest filename cannot be blank")
    return IngestRecord(
        ref=ref,
        filename=filename,
        size_bytes=panel.size_bytes,
        panel=panel,
        file_class=file_class,
        thumbnail=thumbnail,
        tags=tags,
        ingested_at=ingested_at,
        source=source,
    )


def read_preview(
    stream: BinaryIO,
    *,
    start: int = 0,
    length: int = DEFAULT_MAX_PREVIEW_BYTES,
    max_bytes: int = DEFAULT_MAX_PREVIEW_BYTES,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> bytes:
    """Read a bounded preview slice from a stream."""
    if start < 0 or length < 0:
        raise InvalidInputError("Preview start and length must be non-negative")
    if chunk_size < 1:
        raise InvalidInputError("chunk_size must be positive")
    amount = min(length, max_bytes)
    stream.seek(start, 0)
    parts: list[bytes] = []
    remaining = amount
    while remaining > 0:
        chunk = stream.read(min(chunk_size, remaining))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def thumbnail_note(file_class: FileClass, panel: HashPanel) -> str:
    """Build a human-readable note for a thumbnail record."""
    media = file_class.primary.description if file_class.primary else "unrecognized binary"
    return f"{media}; {panel.size_bytes} bytes; SHA-256 {panel.sha256_short}"


def refresh_thumbnail(
    record: ThumbnailRecord,
    *,
    generated_at: str,
    note: str | None = None,
) -> ThumbnailRecord:
    """Return a thumbnail record with refreshed generation metadata."""
    return ThumbnailRecord(
        ref=record.ref,
        preview_kind=record.preview_kind,
        category=record.category,
        width=record.width,
        height=record.height,
        mime_type=record.mime_type,
        source_sha256=record.source_sha256,
        generated_at=generated_at,
        available=record.available,
        note=record.note if note is None else note,
    )
