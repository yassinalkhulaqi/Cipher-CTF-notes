"""MIME detection and media classification for ingested evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from redscribe.v2.evidence.models import EvidenceKind, MimeInfo, MimeSource
from redscribe.v2.evidence.validation import file_extension

DEFAULT_MIME = "application/octet-stream"
TEXT_MIME = "text/plain"

EXTENSION_MIME: dict[str, str] = {
    ".txt": "text/plain",
    ".text": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".svg": "image/svg+xml",
    ".ico": "image/vnd.microsoft.icon",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".zip": "application/zip",
    ".gz": "application/gzip",
    ".tar": "application/x-tar",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".exe": "application/x-msdownload",
    ".dll": "application/x-msdownload",
    ".sh": "application/x-sh",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".db": "application/x-sqlite3",
    ".sqlite": "application/x-sqlite3",
    ".sqlite3": "application/x-sqlite3",
    ".pcap": "application/vnd.tcpdump.pcap",
    ".pcapng": "application/vnd.tcpdump.pcap",
    ".dmp": "application/x-memory-dump",
    ".raw": "application/octet-stream",
    ".img": "application/octet-stream",
    ".bin": DEFAULT_MIME,
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
}

MIME_CATEGORIES: dict[str, str] = {
    "text": "document",
    "application/json": "document",
    "application/xml": "document",
    "application/pdf": "document",
    "image": "image",
    "audio": "audio",
    "video": "video",
    "application/zip": "archive",
    "application/gzip": "archive",
    "application/x-tar": "archive",
    "application/x-7z-compressed": "archive",
    "application/vnd.rar": "archive",
    "application/x-msdownload": "executable",
    "application/x-sh": "executable",
    "application/x-sqlite3": "database",
    "application/vnd.tcpdump.pcap": "network",
    "application/x-memory-dump": "memory",
    "message": "communication",
}

CATEGORY_KINDS: dict[str, EvidenceKind] = {
    "document": EvidenceKind.DOCUMENT,
    "image": EvidenceKind.IMAGE,
    "audio": EvidenceKind.AUDIO,
    "video": EvidenceKind.VIDEO,
    "archive": EvidenceKind.ARCHIVE,
    "executable": EvidenceKind.EXECUTABLE,
    "database": EvidenceKind.DOCUMENT,
    "network": EvidenceKind.NETWORK_CAPTURE,
    "memory": EvidenceKind.MEMORY_IMAGE,
    "communication": EvidenceKind.DOCUMENT,
    "log": EvidenceKind.LOG,
    "other": EvidenceKind.OTHER,
}

CONTROL_RE = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
JSON_PREFIX_RE = re.compile(rb"^[\s]*[{[]")


@dataclass(frozen=True, slots=True)
class MagicSignature:
    """A byte signature used for content-based MIME detection."""

    mime_type: str
    prefix: bytes
    offset: int = 0
    mask: bytes | None = None

    def matches(self, data: bytes) -> bool:
        """Return whether this signature matches the supplied bytes."""
        start = self.offset
        end = start + len(self.prefix)
        if end > len(data):
            return False
        window = data[start:end]
        if self.mask is None:
            return window == self.prefix
        if len(self.mask) != len(self.prefix):
            return False
        return all(
            (byte & mask_value) == (expected & mask_value)
            for byte, mask_value, expected in zip(window, self.mask, self.prefix, strict=True)
        )


MAGIC_SIGNATURES: tuple[MagicSignature, ...] = (
    MagicSignature("image/png", b"\x89PNG\r\n\x1a\n"),
    MagicSignature("image/jpeg", b"\xff\xd8\xff"),
    MagicSignature("image/gif", b"GIF87a"),
    MagicSignature("image/gif", b"GIF89a"),
    MagicSignature("image/webp", b"RIFF", 8, b"WEBP"),
    MagicSignature("image/bmp", b"BM"),
    MagicSignature("image/tiff", b"II*\x00"),
    MagicSignature("image/tiff", b"MM\x00*"),
    MagicSignature("application/pdf", b"%PDF-"),
    MagicSignature("application/zip", b"PK\x03\x04"),
    MagicSignature("application/x-7z-compressed", b"7z\xbc\xaf\x27\x1c"),
    MagicSignature("application/vnd.rar", b"Rar!\x1a\x07"),
    MagicSignature("application/gzip", b"\x1f\x8b\x08"),
    MagicSignature("application/x-tar", b"ustar", 257),
    MagicSignature("application/x-sqlite3", b"SQLite format 3\x00"),
    MagicSignature("application/vnd.tcpdump.pcap", b"\xd4\xc3\xb2\xa1"),
    MagicSignature("application/vnd.tcpdump.pcap", b"\xa1\xb2\xc3\xd4"),
    MagicSignature("application/vnd.tcpdump.pcap", b"\x0a\x0d\x0d\x0a", 0, b"\xff\xff\xff\xff"),
    MagicSignature("audio/mpeg", b"ID3"),
    MagicSignature("audio/flac", b"fLaC"),
    MagicSignature("audio/ogg", b"OggS"),
    MagicSignature("audio/wav", b"RIFF", 8, b"WAVE"),
    MagicSignature("video/mp4", b"ftyp", 4),
    MagicSignature("video/webm", b"\x1a\x45\xdf\xa3"),
    MagicSignature("application/x-msdownload", b"MZ"),
    MagicSignature("application/x-elf", b"\x7fELF"),
)


def normalize_mime(value: object, *, default: str = DEFAULT_MIME) -> str:
    """Normalize a declared MIME type, dropping parameters and whitespace."""
    if not isinstance(value, str) or not value.strip():
        return default
    candidate = value.strip().casefold().split(";", 1)[0].strip()
    if "/" not in candidate or len(candidate) > 120:
        return default
    return candidate


def detect_magic_mime(data: bytes) -> str:
    """Return the MIME type indicated by the strongest magic signature."""
    for signature in MAGIC_SIGNATURES:
        if signature.matches(data):
            return signature.mime_type
    return ""


def is_probably_text(data: bytes) -> bool:
    """Return whether bytes look like UTF-8 text without binary control bytes."""
    if not data:
        return True
    sample = data[:8_192]
    if CONTROL_RE.search(sample):
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def sniff_text_mime(data: bytes) -> str:
    """Distinguish common textual formats after a text check succeeds."""
    if JSON_PREFIX_RE.match(data):
        try:
            data[:1_048_576].decode("utf-8")
            return "application/json"
        except UnicodeDecodeError:
            return TEXT_MIME
    stripped = data[:1_024].lstrip().lower()
    if stripped.startswith((b"<!doctype html", b"<html", b"<head")):
        return "text/html"
    if stripped.startswith(b"<?xml"):
        return "application/xml"
    return TEXT_MIME


def mime_category(mime_type: str) -> str:
    """Map a MIME type to a broad category string."""
    normalized = normalize_mime(mime_type)
    if normalized in MIME_CATEGORIES:
        return MIME_CATEGORIES[normalized]
    family = normalized.split("/", 1)[0]
    return MIME_CATEGORIES.get(family, "other")


def evidence_kind_for_mime(mime_type: str) -> EvidenceKind:
    """Map a MIME type to the evidence kind used by the UI."""
    normalized = normalize_mime(mime_type)
    category = mime_category(normalized)
    if normalized in {"text/csv", "application/json", "application/yaml"}:
        return EvidenceKind.DOCUMENT
    return CATEGORY_KINDS.get(category, EvidenceKind.OTHER)


def confidence_for_source(source: MimeSource) -> float:
    """Return the confidence weight associated with a detection source."""
    return {
        MimeSource.MAGIC: 0.98,
        MimeSource.EXTENSION: 0.62,
        MimeSource.DECLARED: 0.7,
        MimeSource.TEXT_SNIFF: 0.8,
        MimeSource.DEFAULT: 0.1,
    }[source]


def detect_mime(data: bytes, *, filename: str = "", declared: str = "") -> MimeInfo:
    """Detect a MIME type using magic bytes, text sniffing, and extensions."""
    extension = file_extension(filename)
    declared_mime = normalize_mime(declared)
    magic = detect_magic_mime(data)
    if magic:
        return MimeInfo(
            mime_type=magic,
            source=MimeSource.MAGIC,
            confidence=confidence_for_source(MimeSource.MAGIC),
            extension=extension,
            category=mime_category(magic),
        )
    if is_probably_text(data):
        sniffed = sniff_text_mime(data)
        return MimeInfo(
            mime_type=sniffed,
            source=MimeSource.TEXT_SNIFF,
            confidence=confidence_for_source(MimeSource.TEXT_SNIFF),
            extension=extension,
            category=mime_category(sniffed),
        )
    if declared_mime and extension and EXTENSION_MIME.get(extension) == declared_mime:
        return MimeInfo(
            mime_type=declared_mime,
            source=MimeSource.DECLARED,
            confidence=confidence_for_source(MimeSource.DECLARED),
            extension=extension,
            category=mime_category(declared_mime),
        )
    if extension and extension in EXTENSION_MIME:
        inferred = EXTENSION_MIME[extension]
        return MimeInfo(
            mime_type=inferred,
            source=MimeSource.EXTENSION,
            confidence=confidence_for_source(MimeSource.EXTENSION),
            extension=extension,
            category=mime_category(inferred),
        )
    if declared_mime:
        return MimeInfo(
            mime_type=declared_mime,
            source=MimeSource.DECLARED,
            confidence=confidence_for_source(MimeSource.DECLARED) * 0.75,
            extension=extension,
            category=mime_category(declared_mime),
        )
    return MimeInfo(
        mime_type=DEFAULT_MIME,
        source=MimeSource.DEFAULT,
        confidence=confidence_for_source(MimeSource.DEFAULT),
        extension=extension,
        category="other",
    )


def is_textual(mime: MimeInfo | str) -> bool:
    """Return whether a MIME type is safe to render as text."""
    normalized = normalize_mime(mime.mime_type if isinstance(mime, MimeInfo) else mime)
    return normalized.startswith("text/") or normalized in {
        "application/json",
        "application/xml",
        "application/yaml",
        "application/x-ndjson",
        "application/x-sh",
    }


def is_image(mime: MimeInfo | str) -> bool:
    """Return whether a MIME type represents an image."""
    value = mime.mime_type if isinstance(mime, MimeInfo) else mime
    return normalize_mime(value).startswith("image/")


def is_archive(mime: MimeInfo | str) -> bool:
    """Return whether a MIME type represents an archive container."""
    value = mime.mime_type if isinstance(mime, MimeInfo) else mime
    return mime_category(value) == "archive"


def extension_for_mime(mime_type: str) -> str:
    """Return the canonical extension for a MIME type, if known."""
    normalized = normalize_mime(mime_type)
    for extension, candidate in EXTENSION_MIME.items():
        if candidate == normalized:
            return extension
    return ""


def mime_from_path(path: str) -> MimeInfo:
    """Classify a path by extension without reading file bytes."""
    name = PurePosixPath(path.replace("\\", "/")).name
    extension = file_extension(name)
    inferred = EXTENSION_MIME.get(extension, DEFAULT_MIME)
    source = MimeSource.EXTENSION if extension in EXTENSION_MIME else MimeSource.DEFAULT
    return MimeInfo(
        mime_type=inferred,
        source=source,
        confidence=confidence_for_source(source),
        extension=extension,
        category=mime_category(inferred),
    )


def mime_conflict(mime: MimeInfo, declared: str) -> bool:
    """Return whether a declared type conflicts with content detection."""
    candidate = normalize_mime(declared)
    if not candidate or mime.source is not MimeSource.MAGIC:
        return False
    return candidate != mime.mime_type
