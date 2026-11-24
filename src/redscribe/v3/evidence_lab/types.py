"""Immutable wire contracts for the evidence inspection lab.

Nothing in this module depends on the API, storage, or UI layer. Every record
exposes ``as_dict()`` so namespace handlers and the React client share one
vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.entities.types import EntityRef, LinkKind

DEFAULT_BYTES_PER_ROW = 16
DEFAULT_CHUNK_SIZE = 64 * 1024
DEFAULT_MIN_STRING_LENGTH = 4
DEFAULT_MAX_STRING_LENGTH = 4_096
DEFAULT_ENTROPY_SAMPLE = 256 * 1024
DEFAULT_MAX_WINDOW_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_PREVIEW_BYTES = 8 * 1024 * 1024

HEX_CHARS = frozenset("0123456789abcdefABCDEF")
ENTROPY_BUCKET_LABELS = (
    "empty",
    "very_low",
    "low",
    "medium",
    "high",
    "very_high",
    "random",
)


class StringEncoding(str, Enum):
    """Character encodings supported by the printable-string scanner."""

    ASCII = "ascii"
    UTF8 = "utf8"
    UTF16LE = "utf16le"
    UTF16BE = "utf16be"

    @classmethod
    def parse(cls, value: str) -> StringEncoding:
        """Parse an encoding name with a stable error message."""
        normalized = value.strip().casefold().replace("-", "").replace("_", "")
        for encoding in cls:
            if encoding.value == normalized:
                return encoding
        raise ValueError(f"Unsupported string encoding: {value}")

    @property
    def unit_size(self) -> int:
        """Return the byte width of one code unit."""
        return 2 if self in (StringEncoding.UTF16LE, StringEncoding.UTF16BE) else 1


class IntegrityState(str, Enum):
    """Integrity verdict rendered by the frontend badge."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class FileCategory(str, Enum):
    """Coarse grouping used by the magic classifier and thumbnails."""

    IMAGE = "image"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    EXECUTABLE = "executable"
    AUDIO = "audio"
    VIDEO = "video"
    DATABASE = "database"
    TEXT = "text"
    DATA = "data"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HexRow:
    """One rendered row of a hex dump."""

    offset: int
    cells: tuple[str, ...]
    ascii_text: str
    selected: bool = False

    @property
    def byte_count(self) -> int:
        """Return the number of bytes represented by this row."""
        return len(self.cells)

    @property
    def end_offset(self) -> int:
        """Return the exclusive offset of the end of the row."""
        return self.offset + self.byte_count

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "offset": self.offset,
            "offset_hex": f"{self.offset:08x}",
            "cells": list(self.cells),
            "ascii": self.ascii_text,
            "selected": self.selected,
        }


@dataclass(frozen=True, slots=True)
class HexWindow:
    """A bounded, seek-relative window of a hex dump."""

    start: int
    length: int
    bytes_per_row: int
    rows: tuple[HexRow, ...]
    total_bytes: int
    truncated: bool = False
    selection_start: int | None = None
    selection_end: int | None = None

    @property
    def end(self) -> int:
        """Return the exclusive end offset of the window."""
        return self.start + self.length

    @property
    def selected_rows(self) -> tuple[HexRow, ...]:
        """Return rows touched by the active selection."""
        return tuple(row for row in self.rows if row.selected)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "start": self.start,
            "length": self.length,
            "end": self.end,
            "bytes_per_row": self.bytes_per_row,
            "total_bytes": self.total_bytes,
            "truncated": self.truncated,
            "selection_start": self.selection_start,
            "selection_end": self.selection_end,
            "rows": [row.as_dict() for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class StringHit:
    """One contiguous run of printable characters."""

    offset: int
    text: str
    encoding: StringEncoding
    length: int
    printable_ratio: float
    kind: str = "plain"

    @property
    def end(self) -> int:
        """Return the exclusive byte offset of the run."""
        return self.offset + self.length

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "offset": self.offset,
            "end": self.end,
            "text": self.text,
            "encoding": self.encoding.value,
            "length": self.length,
            "printable_ratio": round(self.printable_ratio, 4),
            "kind": self.kind,
        }


@dataclass(frozen=True, slots=True)
class StringScan:
    """Result of a bounded printable-string scan."""

    hits: tuple[StringHit, ...]
    encoding: StringEncoding
    min_length: int
    bytes_scanned: int
    truncated: bool = False
    counts: dict[str, int] = field(default_factory=dict)

    def texts(self) -> tuple[str, ...]:
        """Return the extracted strings in offset order."""
        return tuple(hit.text for hit in self.hits)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "hits": [hit.as_dict() for hit in self.hits],
            "encoding": self.encoding.value,
            "min_length": self.min_length,
            "bytes_scanned": self.bytes_scanned,
            "truncated": self.truncated,
            "counts": dict(self.counts),
        }


@dataclass(frozen=True, slots=True)
class EntropyBucket:
    """Histogram bucket for the entropy mini-chart."""

    label: str
    low: float
    high: float
    count: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "label": self.label,
            "low": round(self.low, 4),
            "high": round(self.high, 4),
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class EntropyReport:
    """Shannon entropy estimate plus a byte histogram."""

    sample_bytes: int
    total_bytes: int
    entropy: float
    normalized: float
    histogram: tuple[int, ...]
    classification: str
    buckets: tuple[EntropyBucket, ...] = ()
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "sample_bytes": self.sample_bytes,
            "total_bytes": self.total_bytes,
            "entropy": round(self.entropy, 6),
            "normalized": round(self.normalized, 6),
            "classification": self.classification,
            "truncated": self.truncated,
            "histogram": list(self.histogram),
            "buckets": [bucket.as_dict() for bucket in self.buckets],
        }


@dataclass(frozen=True, slots=True)
class MagicMatch:
    """A single signature match from the magic-byte classifier."""

    media_type: str
    description: str
    category: FileCategory
    extension: str
    confidence: float
    offset: int
    signature_hex: str
    source: str = "magic"

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "media_type": self.media_type,
            "description": self.description,
            "category": self.category.value,
            "extension": self.extension,
            "confidence": round(self.confidence, 3),
            "offset": self.offset,
            "signature_hex": self.signature_hex,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class FileClass:
    """Classification result for a byte prefix."""

    matches: tuple[MagicMatch, ...]
    primary: MagicMatch | None
    extension_hint: str = ""
    header_bytes: int = 0

    @property
    def media_type(self) -> str:
        """Primary media type or a safe fallback."""
        return self.primary.media_type if self.primary else "application/octet-stream"

    @property
    def category(self) -> FileCategory:
        """Primary category or unknown."""
        return self.primary.category if self.primary else FileCategory.UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "matches": [match.as_dict() for match in self.matches],
            "primary": self.primary.as_dict() if self.primary else None,
            "media_type": self.media_type,
            "category": self.category.value,
            "extension_hint": self.extension_hint,
            "header_bytes": self.header_bytes,
        }


@dataclass(frozen=True, slots=True)
class HashDigest:
    """A named hex digest."""

    algorithm: str
    value: str
    size_bytes: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"algorithm": self.algorithm, "value": self.value, "size_bytes": self.size_bytes}


@dataclass(frozen=True, slots=True)
class HashPanel:
    """The authoritative multi-hash panel for one byte stream."""

    sha256: str
    blake2b: str
    size_bytes: int
    computed_at: str = ""
    blake2b_size: int = 32
    expected_sha256: str = ""
    expected_blake2b: str = ""

    @property
    def sha256_short(self) -> str:
        """Compact SHA-256 display form."""
        return compact_digest(self.sha256)

    @property
    def blake2b_short(self) -> str:
        """Compact BLAKE2b display form."""
        return compact_digest(self.blake2b)

    @property
    def combined_id(self) -> str:
        """Stable composite identifier for provenance links."""
        return f"{self.sha256}:{self.blake2b}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "sha256": self.sha256,
            "blake2b": self.blake2b,
            "sha256_short": self.sha256_short,
            "blake2b_short": self.blake2b_short,
            "size_bytes": self.size_bytes,
            "computed_at": self.computed_at,
            "blake2b_size": self.blake2b_size,
            "combined_id": self.combined_id,
        }


@dataclass(frozen=True, slots=True)
class IntegrityBadge:
    """Verdict produced by comparing a live panel with a stored record."""

    state: IntegrityState
    sha256_match: bool
    blake2b_match: bool
    size_match: bool
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether the badge reports a clean verification."""
        return self.state is IntegrityState.VERIFIED

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "state": self.state.value,
            "sha256_match": self.sha256_match,
            "blake2b_match": self.blake2b_match,
            "size_match": self.size_match,
            "ok": self.ok,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class RangeSpec:
    """A parsed HTTP-style byte range."""

    start: int
    end: int | None = None
    suffix: bool = False

    @property
    def length(self) -> int | None:
        """Return the requested length when it is explicitly bounded."""
        if self.suffix or self.end is None:
            return None
        return max(0, self.end - self.start + 1)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"start": self.start, "end": self.end, "suffix": self.suffix}


@dataclass(frozen=True, slots=True)
class RangeChunk:
    """A satisfied range read with bounded in-memory data."""

    start: int
    end: int
    total_size: int
    data: bytes
    truncated: bool = False

    @property
    def length(self) -> int:
        """Return the number of bytes actually read."""
        return len(self.data)

    @property
    def content_range(self) -> str:
        """Return an RFC-style content-range value."""
        return f"bytes {self.start}-{max(self.start, self.end - 1)}/{self.total_size}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without raw bytes."""
        return {
            "start": self.start,
            "end": self.end,
            "length": self.length,
            "total_size": self.total_size,
            "truncated": self.truncated,
            "content_range": self.content_range,
            "preview_hex": self.data[:32].hex(),
        }


@dataclass(frozen=True, slots=True)
class CustodyNode:
    """A vertex in the chain-of-custody graph."""

    ref: EntityRef
    label: str
    action: str = ""
    timestamp: str = ""
    depth: int = 0
    terminal: bool = False

    @property
    def key(self) -> str:
        """Stable graph key."""
        return str(self.ref)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            **self.ref.as_dict(),
            "label": self.label or self.ref.label,
            "action": self.action,
            "timestamp": self.timestamp,
            "depth": self.depth,
            "terminal": self.terminal,
        }


@dataclass(frozen=True, slots=True)
class CustodyEdge:
    """A typed directed custody edge."""

    source: str
    target: str
    kind: LinkKind
    label: str = ""
    timestamp: str = ""
    sequence: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "label": self.label,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class CustodyGraph:
    """A verifiable custody chain rendered as a graph and a timeline."""

    root: str
    nodes: tuple[CustodyNode, ...]
    edges: tuple[CustodyEdge, ...]
    timeline: tuple[dict[str, Any], ...] = ()
    problems: tuple[str, ...] = ()
    cycle_free: bool = True

    @property
    def node_keys(self) -> tuple[str, ...]:
        """Return node keys in stable order."""
        return tuple(node.key for node in self.nodes)

    @property
    def verified(self) -> bool:
        """Whether the graph has no validation problems."""
        return self.cycle_free and not self.problems

    @property
    def depth(self) -> int:
        """Return the longest root-to-leaf path length."""
        return max((node.depth for node in self.nodes), default=0)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "root": self.root,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "timeline": [dict(item) for item in self.timeline],
            "problems": list(self.problems),
            "cycle_free": self.cycle_free,
            "verified": self.verified,
            "depth": self.depth,
        }


@dataclass(frozen=True, slots=True)
class BundleEntry:
    """One content-addressed item in an evidence bundle."""

    key: str
    sha256: str
    blake2b: str = ""
    size_bytes: int = 0
    label: str = ""

    def identity(self) -> str:
        """Return the hash identity used for comparison."""
        return self.sha256 or self.blake2b

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "sha256": self.sha256,
            "blake2b": self.blake2b,
            "size_bytes": self.size_bytes,
            "label": self.label,
        }


class BundleDeltaKind(str, Enum):
    """Change classification for a bundle comparison."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class BundleDelta:
    """A single key-level difference between two bundles."""

    key: str
    kind: BundleDeltaKind
    left: BundleEntry | None = None
    right: BundleEntry | None = None
    size_delta: int = 0

    @property
    def hash_changed(self) -> bool:
        """Whether the content hash changed."""
        if self.left is None or self.right is None:
            return self.kind is not BundleDeltaKind.UNCHANGED
        return self.left.identity() != self.right.identity()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "kind": self.kind.value,
            "left": self.left.as_dict() if self.left else None,
            "right": self.right.as_dict() if self.right else None,
            "size_delta": self.size_delta,
            "hash_changed": self.hash_changed,
        }


@dataclass(frozen=True, slots=True)
class BundleDiff:
    """Diff summary for two evidence bundles."""

    left_id: str
    right_id: str
    deltas: tuple[BundleDelta, ...]
    counts: dict[str, int] = field(default_factory=dict)
    fingerprint_left: str = ""
    fingerprint_right: str = ""

    @property
    def identical(self) -> bool:
        """Whether both bundles contain the same content."""
        return (
            all(delta.kind is BundleDeltaKind.UNCHANGED for delta in self.deltas)
            and self.fingerprint_left == self.fingerprint_right
        )

    def changed(self) -> tuple[BundleDelta, ...]:
        """Return every non-identical delta."""
        return tuple(delta for delta in self.deltas if delta.kind is not BundleDeltaKind.UNCHANGED)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "deltas": [delta.as_dict() for delta in self.deltas],
            "counts": dict(self.counts),
            "fingerprint_left": self.fingerprint_left,
            "fingerprint_right": self.fingerprint_right,
            "identical": self.identical,
        }


@dataclass(frozen=True, slots=True)
class ThumbnailRecord:
    """Metadata describing a generated or derived preview."""

    ref: EntityRef
    preview_kind: str
    category: FileCategory
    width: int
    height: int
    mime_type: str
    source_sha256: str
    generated_at: str
    available: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": str(self.ref),
            "preview_kind": self.preview_kind,
            "category": self.category.value,
            "width": self.width,
            "height": self.height,
            "mime_type": self.mime_type,
            "source_sha256": self.source_sha256,
            "generated_at": self.generated_at,
            "available": self.available,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class IngestRecord:
    """A registered evidence item with its provenance panel."""

    ref: EntityRef
    filename: str
    size_bytes: int
    panel: HashPanel
    file_class: FileClass
    thumbnail: ThumbnailRecord
    tags: tuple[str, ...] = ()
    ingested_at: str = ""
    source: str = "local"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": str(self.ref),
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "panel": self.panel.as_dict(),
            "file_class": self.file_class.as_dict(),
            "thumbnail": self.thumbnail.as_dict(),
            "tags": list(self.tags),
            "ingested_at": self.ingested_at,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """Complete inspection result returned to the lab UI."""

    ref: EntityRef
    size_bytes: int
    panel: HashPanel
    badge: IntegrityBadge
    file_class: FileClass
    hex_window: HexWindow | None = None
    strings: StringScan | None = None
    entropy: EntropyReport | None = None
    thumbnail: ThumbnailRecord | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ref": str(self.ref),
            "size_bytes": self.size_bytes,
            "panel": self.panel.as_dict(),
            "badge": self.badge.as_dict(),
            "file_class": self.file_class.as_dict(),
            "hex_window": self.hex_window.as_dict() if self.hex_window else None,
            "strings": self.strings.as_dict() if self.strings else None,
            "entropy": self.entropy.as_dict() if self.entropy else None,
            "thumbnail": self.thumbnail.as_dict() if self.thumbnail else None,
            "warnings": list(self.warnings),
        }


def compact_digest(value: str, *, visible: int = 10) -> str:
    """Shorten a digest for compact display without losing identity."""
    if not value:
        return ""
    count = max(4, min(24, visible))
    if len(value) <= count * 2 + 1:
        return value
    return f"{value[:count]}...{value[-count:]}"


def normalize_hex_digest(value: str, *, length: int) -> str:
    """Return a lowercase hex digest or an empty string when malformed."""
    text = value.strip().casefold()
    if len(text) != length or any(char not in HEX_CHARS for char in text):
        return ""
    return text


def is_hex_string(value: str) -> bool:
    """Return whether a string contains only hexadecimal characters."""
    return bool(value) and all(char in HEX_CHARS for char in value)
