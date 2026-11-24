"""Magic-byte classification for evidence previews.

A compact, dependency-free signature table covers the formats most often seen
in CTF and pentest evidence. Classification reads only a short header prefix,
so it works on multi-gigabyte files without loading them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.types import FileCategory, FileClass, MagicMatch

DEFAULT_HEADER_BYTES = 512


@dataclass(frozen=True, slots=True)
class MagicSignature:
    """One magic-byte rule."""

    signature: bytes
    media_type: str
    description: str
    category: FileCategory
    extension: str
    confidence: float = 1.0
    offset: int = 0
    mask: bytes = b""

    def matches(self, header: bytes) -> bool:
        """Return whether this rule matches a header prefix."""
        start = self.offset
        end = start + len(self.signature)
        if end > len(header):
            return False
        window = header[start:end]
        if self.mask:
            if len(self.mask) != len(self.signature):
                return False
            return all(
                byte & mask_value == expected & mask_value
                for byte, mask_value, expected in zip(
                    window, self.mask, self.signature, strict=True
                )
            )
        return window == self.signature

    def to_match(self) -> MagicMatch:
        """Convert the rule into a reported match."""
        return MagicMatch(
            media_type=self.media_type,
            description=self.description,
            category=self.category,
            extension=self.extension,
            confidence=self.confidence,
            offset=self.offset,
            signature_hex=self.signature.hex(),
        )


SIGNATURES: tuple[MagicSignature, ...] = (
    MagicSignature(
        b"\x89PNG\r\n\x1a\n", "image/png", "Portable Network Graphics", FileCategory.IMAGE, "png"
    ),
    MagicSignature(b"\xff\xd8\xff", "image/jpeg", "JPEG image", FileCategory.IMAGE, "jpg", 0.99),
    MagicSignature(b"GIF87a", "image/gif", "GIF image (87a)", FileCategory.IMAGE, "gif"),
    MagicSignature(b"GIF89a", "image/gif", "GIF image (89a)", FileCategory.IMAGE, "gif"),
    MagicSignature(b"BM", "image/bmp", "Windows bitmap", FileCategory.IMAGE, "bmp", 0.8),
    MagicSignature(
        b"RIFF\x00\x00\x00\x00WEBP",
        "image/webp",
        "WebP image",
        FileCategory.IMAGE,
        "webp",
        0.95,
        0,
        b"\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff",
    ),
    MagicSignature(
        b"%PDF-", "application/pdf", "Portable Document Format", FileCategory.DOCUMENT, "pdf"
    ),
    MagicSignature(b"PK\x03\x04", "application/zip", "ZIP archive", FileCategory.ARCHIVE, "zip"),
    MagicSignature(
        b"PK\x05\x06", "application/zip", "Empty ZIP archive", FileCategory.ARCHIVE, "zip"
    ),
    MagicSignature(
        b"PK\x07\x08", "application/zip", "Spanned ZIP archive", FileCategory.ARCHIVE, "zip"
    ),
    MagicSignature(b"\x1f\x8b", "application/gzip", "Gzip stream", FileCategory.ARCHIVE, "gz"),
    MagicSignature(b"BZh", "application/x-bzip2", "Bzip2 stream", FileCategory.ARCHIVE, "bz2", 0.9),
    MagicSignature(b"\xfd7zXZ\x00", "application/x-xz", "XZ stream", FileCategory.ARCHIVE, "xz"),
    MagicSignature(
        b"7z\xbc\xaf'\x1c",
        "application/x-7z-compressed",
        "7-Zip archive",
        FileCategory.ARCHIVE,
        "7z",
    ),
    MagicSignature(
        b"Rar!\x1a\x07\x00",
        "application/x-rar-compressed",
        "RAR archive",
        FileCategory.ARCHIVE,
        "rar",
    ),
    MagicSignature(
        b"Rar!\x1a\x07\x01\x00",
        "application/x-rar-compressed",
        "RAR5 archive",
        FileCategory.ARCHIVE,
        "rar5",
    ),
    MagicSignature(
        b"\x7fELF", "application/x-executable", "ELF binary", FileCategory.EXECUTABLE, "elf"
    ),
    MagicSignature(
        b"MZ", "application/x-dosexec", "DOS/PE executable", FileCategory.EXECUTABLE, "exe", 0.7
    ),
    MagicSignature(
        b"\xca\xfe\xba\xbe",
        "application/java-vm",
        "Java class file",
        FileCategory.EXECUTABLE,
        "class",
    ),
    MagicSignature(
        b"\x00asm", "application/wasm", "WebAssembly module", FileCategory.EXECUTABLE, "wasm"
    ),
    MagicSignature(
        b"SQLite format 3\x00",
        "application/vnd.sqlite3",
        "SQLite database",
        FileCategory.DATABASE,
        "sqlite",
    ),
    MagicSignature(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        "application/x-ole-storage",
        "OLE compound file",
        FileCategory.DOCUMENT,
        "ole",
    ),
    MagicSignature(
        b"RIFF\x00\x00\x00\x00WAVE",
        "audio/wav",
        "Wave audio",
        FileCategory.AUDIO,
        "wav",
        0.95,
        0,
        b"\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff",
    ),
    MagicSignature(b"OggS", "application/ogg", "Ogg container", FileCategory.AUDIO, "ogg", 0.8),
    MagicSignature(b"fLaC", "audio/flac", "FLAC audio", FileCategory.AUDIO, "flac"),
    MagicSignature(b"ID3", "audio/mpeg", "MP3 with ID3 tag", FileCategory.AUDIO, "mp3", 0.9),
    MagicSignature(
        b"\xff\xfb", "audio/mpeg", "MP3 frame", FileCategory.AUDIO, "mp3", 0.75, 0, b"\xff\xe0"
    ),
    MagicSignature(
        b"\x00\x00\x00\x00ftyp",
        "video/mp4",
        "MP4 container",
        FileCategory.VIDEO,
        "mp4",
        0.9,
        0,
        b"\x00\x00\x00\x00\xff\xff\xff\xff",
    ),
    MagicSignature(
        b"ustar", "application/x-tar", "POSIX tar archive", FileCategory.ARCHIVE, "tar", 0.9, 257
    ),
    MagicSignature(b"\x04\x22M\x18", "application/x-lz4", "LZ4 frame", FileCategory.ARCHIVE, "lz4"),
    MagicSignature(
        b"\x28\xb5\x2f\xfd", "application/zstd", "Zstandard frame", FileCategory.ARCHIVE, "zst"
    ),
    MagicSignature(
        b"\xd4\xc3\xb2\xa1",
        "application/vnd.tcpdump.pcap",
        "PCAP capture",
        FileCategory.DATA,
        "pcap",
        0.9,
    ),
    MagicSignature(
        b"\xa1\xb2\xc3\xd4",
        "application/vnd.tcpdump.pcap",
        "PCAP capture (BE)",
        FileCategory.DATA,
        "pcap",
        0.9,
    ),
    MagicSignature(
        b"SSH-", "text/x-ssh-key", "OpenSSH key or banner", FileCategory.TEXT, "txt", 0.8
    ),
    MagicSignature(
        b"\xef\xbb\xbf", "text/plain", "UTF-8 text with BOM", FileCategory.TEXT, "txt", 0.6
    ),
)


def classify_header(header: bytes) -> FileClass:
    """Classify a byte prefix using the signature table."""
    matches: list[MagicMatch] = []
    for rule in SIGNATURES:
        if rule.matches(header):
            matches.append(rule.to_match())
    matches.sort(key=lambda match: (-match.confidence, match.offset, match.media_type))
    primary = matches[0] if matches else None
    hint = primary.extension if primary else ""
    return FileClass(
        matches=tuple(matches),
        primary=primary,
        extension_hint=hint,
        header_bytes=len(header),
    )


def classify_bytes(data: bytes, *, header_bytes: int = DEFAULT_HEADER_BYTES) -> FileClass:
    """Classify an in-memory byte string."""
    if header_bytes < 1:
        raise InvalidInputError("header_bytes must be positive")
    return classify_header(data[:header_bytes])


def classify_stream(stream: BinaryIO, *, header_bytes: int = DEFAULT_HEADER_BYTES) -> FileClass:
    """Classify a stream by reading only its header prefix."""
    if header_bytes < 1:
        raise InvalidInputError("header_bytes must be positive")
    current = stream.tell()
    stream.seek(0, 0)
    header = stream.read(header_bytes)
    stream.seek(current, 0)
    if not isinstance(header, bytes):
        raise InvalidInputError("Binary streams must return bytes")
    return classify_header(header)


def extension_for(media_type: str) -> str:
    """Return the preferred extension for a media type."""
    for rule in SIGNATURES:
        if rule.media_type == media_type:
            return rule.extension
    return "bin"


def category_for(media_type: str) -> FileCategory:
    """Return the coarse category for a media type."""
    for rule in SIGNATURES:
        if rule.media_type == media_type:
            return rule.category
    return FileCategory.UNKNOWN


def signature_table() -> tuple[dict[str, object], ...]:
    """Return the signature table as JSON-safe records for docs/UI."""
    return tuple(
        {
            "signature": rule.signature.hex(),
            "offset": rule.offset,
            "media_type": rule.media_type,
            "category": rule.category.value,
            "extension": rule.extension,
            "confidence": rule.confidence,
        }
        for rule in SIGNATURES
    )


def media_type_label(file_class: FileClass) -> str:
    """Return a short human label for a classification result."""
    return file_class.primary.description if file_class.primary else "Unknown binary"
