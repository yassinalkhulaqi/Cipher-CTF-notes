"""Typed, validated value objects for the v4 evidence inspection lab.

Every object in this module is data-only: it validates its own invariants in
``__post_init__`` and round-trips through ``to_dict`` / ``from_dict``. Nothing
here executes shell commands, evaluates expressions, or performs network I/O.
The lab inspects *metadata* (bytes already supplied by a caller), never files.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v4.contracts import EntityKind, EntityRef, new_entity_id

_HEX_BYTE = re.compile(r"^[0-9a-fA-F]{2}$")
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,47}$")


class EvidenceLabError(Exception):
    """Base class for evidence-lab domain errors."""


class ValidationError(EvidenceLabError):
    """Raised when a value object violates its declared invariants."""


class ChainIntegrityError(EvidenceLabError):
    """Raised when a custody chain fails verification."""


class HashMismatchError(EvidenceLabError):
    """Raised when an expected digest does not match a computed digest."""


def require_text(value: object, label: str) -> str:
    """Return a stripped non-empty string or raise :class:`ValidationError`."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be a non-empty string")
    return value.strip()


def require_int(value: object, label: str, minimum: int = 0) -> int:
    """Return an integer at least ``minimum`` or raise :class:`ValidationError`."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{label} must be an integer")
    if value < minimum:
        raise ValidationError(f"{label} must be >= {minimum}")
    return value


def normalize_tags(values: Iterable[object]) -> tuple[str, ...]:
    """Lowercase, de-duplicate, and sort tag labels."""
    seen: set[str] = set()
    for item in values:
        tag = str(item).strip().casefold()
        if tag and not _TAG_PATTERN.match(tag):
            raise ValidationError(f"invalid tag: {tag}")
        if tag:
            seen.add(tag)
    return tuple(sorted(seen))


def is_hex_digest(value: str, length: int) -> bool:
    """Return whether ``value`` is a hex digest of exactly ``length`` chars."""
    return len(value) == length and all(character in _HEX_CHARS for character in value)


def printable_ascii(byte: int) -> str:
    """Map a byte to its printable ASCII glyph or a dot placeholder."""
    return chr(byte) if 32 <= byte <= 126 else "."


class HashAlgorithm(str, Enum):
    """Digest algorithms supported by the lab (data-only identifiers)."""

    SHA256 = "sha256"
    SHA1 = "sha1"
    MD5 = "md5"

    @classmethod
    def parse(cls, value: object) -> HashAlgorithm:
        raw = value.value if isinstance(value, Enum) else value
        normalized = str(raw).strip().casefold().replace("-", "").replace("_", "")
        aliases = {"sha2": cls.SHA256, "sha256": cls.SHA256, "sha1": cls.SHA1, "md5": cls.MD5}
        algorithm = aliases.get(normalized)
        if algorithm is None:
            raise ValidationError(f"unknown hash algorithm: {value}")
        return algorithm

    @property
    def digest_size(self) -> int:
        return {HashAlgorithm.SHA256: 64, HashAlgorithm.SHA1: 40, HashAlgorithm.MD5: 32}[self]

    @property
    def label(self) -> str:
        return {
            HashAlgorithm.SHA256: "SHA-256",
            HashAlgorithm.SHA1: "SHA-1",
            HashAlgorithm.MD5: "MD5",
        }[self]


class StringEncoding(str, Enum):
    """Encodings the printable-run scanner understands."""

    ASCII = "ascii"
    UTF8 = "utf-8"
    UTF16LE = "utf-16le"

    @classmethod
    def parse(cls, value: object) -> StringEncoding:
        raw = value.value if isinstance(value, Enum) else value
        normalized = str(raw).strip().casefold().replace("_", "-")
        aliases = {
            "ascii": cls.ASCII,
            "utf8": cls.UTF8,
            "utf-8": cls.UTF8,
            "utf16": cls.UTF16LE,
            "utf16le": cls.UTF16LE,
            "utf-16le": cls.UTF16LE,
        }
        encoding = aliases.get(normalized)
        if encoding is None:
            raise ValidationError(f"unknown string encoding: {value}")
        return encoding

    @property
    def unit(self) -> int:
        return 1 if self in (StringEncoding.ASCII, StringEncoding.UTF8) else 2


class CustodyAction(str, Enum):
    """Actions recorded in an evidence custody chain."""

    ACQUIRED = "acquired"
    TRANSFERRED = "transferred"
    ANALYZED = "analyzed"
    VERIFIED = "verified"
    EXPORTED = "exported"
    SEALED = "sealed"

    @classmethod
    def parse(cls, value: object) -> CustodyAction:
        raw = value.value if isinstance(value, Enum) else value
        normalized = str(raw).strip().casefold()
        for action in cls:
            if action.value == normalized:
                return action
        raise ValidationError(f"unknown custody action: {value}")

    @property
    def label(self) -> str:
        return self.value.title()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Metadata describing one piece of acquired evidence."""

    id: str
    name: str
    size: int
    sha256: str
    acquired_at: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "id"))
        object.__setattr__(self, "name", require_text(self.name, "name"))
        object.__setattr__(self, "size", require_int(self.size, "size"))
        digest = require_text(self.sha256, "sha256").casefold()
        if not is_hex_digest(digest, HashAlgorithm.SHA256.digest_size):
            raise ValidationError("sha256 must be 64 hexadecimal characters")
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "acquired_at", require_text(self.acquired_at, "acquired_at"))
        object.__setattr__(self, "tags", normalize_tags(self.tags))

    @property
    def extension(self) -> str:
        suffix = self.name.rsplit(".", 1)[-1] if "." in self.name else ""
        return suffix.casefold()

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]

    def has_tag(self, tag: str) -> bool:
        return tag.strip().casefold() in self.tags

    def with_hash(self, digest: str) -> EvidenceRecord:
        return EvidenceRecord(
            id=self.id,
            name=self.name,
            size=self.size,
            sha256=digest,
            acquired_at=self.acquired_at,
            tags=self.tags,
        )

    def to_ref(self) -> EntityRef:
        return EntityRef(kind=EntityKind.EVIDENCE, id=self.id, label=self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "sha256": self.sha256,
            "acquired_at": self.acquired_at,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceRecord:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            size=require_int(data.get("size", -1), "size"),
            sha256=str(data.get("sha256", "")),
            acquired_at=str(data.get("acquired_at", "")),
            tags=tuple(str(item) for item in data.get("tags", [])),
        )

    @classmethod
    def create(
        cls,
        name: str,
        size: int,
        sha256: str,
        acquired_at: str,
        tags: Iterable[str] = (),
        identifier: str | None = None,
    ) -> EvidenceRecord:
        return cls(
            id=identifier or new_entity_id(),
            name=name,
            size=size,
            sha256=sha256,
            acquired_at=acquired_at,
            tags=tuple(tags),
        )


@dataclass(frozen=True, slots=True)
class HexCell:
    """One byte rendered in a hex-dump grid."""

    offset: int
    hex: str
    ascii: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "offset", require_int(self.offset, "offset"))
        value = str(self.hex).strip().casefold()
        if not _HEX_BYTE.match(value):
            raise ValidationError(f"hex cell must be two hex digits: {self.hex!r}")
        object.__setattr__(self, "hex", value)
        glyph = str(self.ascii)
        if len(glyph) != 1:
            raise ValidationError("ascii cell must be a single character")
        object.__setattr__(self, "ascii", glyph)

    @property
    def byte(self) -> int:
        return int(self.hex, 16)

    @property
    def is_printable(self) -> bool:
        return 32 <= self.byte <= 126

    def to_dict(self) -> dict[str, Any]:
        return {"offset": self.offset, "hex": self.hex, "ascii": self.ascii}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HexCell:
        return cls(
            offset=require_int(data.get("offset", -1), "offset"),
            hex=str(data.get("hex", "")),
            ascii=str(data.get("ascii", ".")),
        )


@dataclass(frozen=True, slots=True)
class HexRow:
    """A single 16-byte row of a hex dump."""

    offset: int
    cells: tuple[HexCell, ...]
    ascii: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "offset", require_int(self.offset, "offset"))
        cells = tuple(self.cells)
        if not 1 <= len(cells) <= 16:
            raise ValidationError("a hex row holds between 1 and 16 cells")
        for index, cell in enumerate(cells):
            if cell.offset != self.offset + index:
                raise ValidationError("hex cell offsets must be consecutive")
        object.__setattr__(self, "cells", cells)
        if not self.ascii:
            object.__setattr__(self, "ascii", "".join(cell.ascii for cell in cells))

    @property
    def size(self) -> int:
        return len(self.cells)

    def cell_at(self, offset: int) -> HexCell | None:
        index = offset - self.offset
        return self.cells[index] if 0 <= index < len(self.cells) else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "cells": [cell.to_dict() for cell in self.cells],
            "ascii": self.ascii,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HexRow:
        return cls(
            offset=require_int(data.get("offset", -1), "offset"),
            cells=tuple(HexCell.from_dict(dict(item)) for item in data.get("cells", [])),
            ascii=str(data.get("ascii", "")),
        )


@dataclass(frozen=True, slots=True)
class StringHit:
    """A printable run located at a byte offset."""

    offset: int
    value: str
    encoding: StringEncoding = StringEncoding.ASCII

    def __post_init__(self) -> None:
        object.__setattr__(self, "offset", require_int(self.offset, "offset"))
        object.__setattr__(self, "value", require_text(self.value, "value"))
        object.__setattr__(self, "encoding", StringEncoding.parse(self.encoding))

    @property
    def length(self) -> int:
        return len(self.value)

    @property
    def end(self) -> int:
        return self.offset + self.length * self.encoding.unit

    @property
    def is_likely_url(self) -> bool:
        lowered = self.value.casefold()
        return lowered.startswith(("http://", "https://", "ftp://", "www."))

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "value": self.value,
            "encoding": self.encoding.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StringHit:
        return cls(
            offset=require_int(data.get("offset", -1), "offset"),
            value=str(data.get("value", "")),
            encoding=StringEncoding.parse(data.get("encoding", "ascii")),
        )


@dataclass(frozen=True, slots=True)
class HashVerification:
    """Comparison of an expected digest with a computed digest."""

    algorithm: HashAlgorithm
    expected: str
    actual: str
    matches: bool

    def __post_init__(self) -> None:
        algorithm = HashAlgorithm.parse(self.algorithm)
        object.__setattr__(self, "algorithm", algorithm)
        expected = require_text(self.expected, "expected").casefold()
        actual = require_text(self.actual, "actual").casefold()
        for label, digest in (("expected", expected), ("actual", actual)):
            if not is_hex_digest(digest, algorithm.digest_size):
                raise ValidationError(f"{label} is not a valid {algorithm.label} digest")
        object.__setattr__(self, "expected", expected)
        object.__setattr__(self, "actual", actual)
        consistent = expected == actual
        if bool(self.matches) != consistent:
            raise ValidationError("matches flag disagrees with the supplied digests")
        object.__setattr__(self, "matches", consistent)

    @classmethod
    def from_hashes(
        cls, algorithm: HashAlgorithm | str, expected: str, actual: str
    ) -> HashVerification:
        parsed = HashAlgorithm.parse(algorithm)
        return cls(
            algorithm=parsed,
            expected=expected,
            actual=actual,
            matches=str(expected).casefold() == str(actual).casefold(),
        )

    @property
    def verdict(self) -> str:
        return "verified" if self.matches else "mismatch"

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm.value,
            "expected": self.expected,
            "actual": self.actual,
            "matches": self.matches,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HashVerification:
        return cls(
            algorithm=HashAlgorithm.parse(data.get("algorithm", "sha256")),
            expected=str(data.get("expected", "")),
            actual=str(data.get("actual", "")),
            matches=bool(data.get("matches", False)),
        )


@dataclass(frozen=True, slots=True)
class CustodyEntry:
    """One append-only entry in an evidence custody chain."""

    actor: str
    action: CustodyAction
    timestamp: str
    from_hash: str
    to_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor", require_text(self.actor, "actor"))
        object.__setattr__(self, "action", CustodyAction.parse(self.action))
        object.__setattr__(self, "timestamp", require_text(self.timestamp, "timestamp"))
        for label, digest in (("from_hash", self.from_hash), ("to_hash", self.to_hash)):
            value = require_text(digest, label).casefold()
            if not is_hex_digest(value, HashAlgorithm.SHA256.digest_size):
                raise ValidationError(f"{label} must be a SHA-256 digest")
            object.__setattr__(self, label, value)

    def canonical(self) -> str:
        """Return the canonical string whose digest links this entry."""
        return "|".join(
            (self.timestamp, self.actor, self.action.value, self.from_hash, self.to_hash)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "action": self.action.value,
            "timestamp": self.timestamp,
            "from_hash": self.from_hash,
            "to_hash": self.to_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CustodyEntry:
        return cls(
            actor=str(data.get("actor", "")),
            action=CustodyAction.parse(data.get("action", "acquired")),
            timestamp=str(data.get("timestamp", "")),
            from_hash=str(data.get("from_hash", "")),
            to_hash=str(data.get("to_hash", "")),
        )


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """Result of verifying an append-only custody chain."""

    valid: bool
    length: int
    broken_index: int = -1
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def headline(self) -> str:
        return "chain intact" if self.valid else f"broken at entry {self.broken_index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "length": self.length,
            "broken_index": self.broken_index,
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class InspectionResult:
    """Aggregated, serializable output of one evidence inspection."""

    evidence_id: str
    hex_rows: tuple[HexRow, ...] = field(default_factory=tuple)
    strings: tuple[StringHit, ...] = field(default_factory=tuple)
    verifications: tuple[HashVerification, ...] = field(default_factory=tuple)
    custody: tuple[CustodyEntry, ...] = field(default_factory=tuple)
    generated_at: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", require_text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "hex_rows", tuple(self.hex_rows))
        object.__setattr__(self, "strings", tuple(self.strings))
        object.__setattr__(self, "verifications", tuple(self.verifications))
        object.__setattr__(self, "custody", tuple(self.custody))
        object.__setattr__(self, "generated_at", str(self.generated_at))
        object.__setattr__(self, "notes", tuple(str(item) for item in self.notes))

    @property
    def all_verified(self) -> bool:
        return bool(self.verifications) and all(item.matches for item in self.verifications)

    @property
    def cell_count(self) -> int:
        return sum(row.size for row in self.hex_rows)

    def summary(self) -> dict[str, int | bool]:
        return {
            "rows": len(self.hex_rows),
            "cells": self.cell_count,
            "strings": len(self.strings),
            "verifications": len(self.verifications),
            "custody_entries": len(self.custody),
            "all_verified": self.all_verified,
        }

    def cells(self) -> tuple[HexCell, ...]:
        return tuple(cell for row in self.hex_rows for cell in row.cells)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "hex_rows": [row.to_dict() for row in self.hex_rows],
            "strings": [hit.to_dict() for hit in self.strings],
            "verifications": [item.to_dict() for item in self.verifications],
            "custody": [entry.to_dict() for entry in self.custody],
            "generated_at": self.generated_at,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InspectionResult:
        return cls(
            evidence_id=str(data.get("evidence_id", "")),
            hex_rows=tuple(HexRow.from_dict(dict(item)) for item in data.get("hex_rows", [])),
            strings=tuple(StringHit.from_dict(dict(item)) for item in data.get("strings", [])),
            verifications=tuple(
                HashVerification.from_dict(dict(item)) for item in data.get("verifications", [])
            ),
            custody=tuple(CustodyEntry.from_dict(dict(item)) for item in data.get("custody", [])),
            generated_at=str(data.get("generated_at", "")),
            notes=tuple(str(item) for item in data.get("notes", [])),
        )


def sorted_records(records: Iterable[EvidenceRecord]) -> tuple[EvidenceRecord, ...]:
    """Return records sorted deterministically by name and identifier."""
    return tuple(sorted(records, key=lambda record: (record.name.casefold(), record.id)))
