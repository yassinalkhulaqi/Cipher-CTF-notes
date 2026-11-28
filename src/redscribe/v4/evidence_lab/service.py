"""Pure, deterministic domain operations for the evidence inspection lab.

All operations work on byte sequences and typed metadata supplied by callers.
There is intentionally no file I/O, subprocess execution, evaluation, or network
access: the lab is a *metadata* workbench, so a hostile bundle cannot make the
service read arbitrary paths or run code.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar

from redscribe.v4.clock import SYSTEM_CLOCK, Clock

from .types import (
    ChainIntegrityError,
    CustodyAction,
    CustodyEntry,
    EvidenceRecord,
    HashAlgorithm,
    HashMismatchError,
    HashVerification,
    HexCell,
    HexRow,
    InspectionResult,
    StringEncoding,
    StringHit,
    ValidationError,
    printable_ascii,
    sorted_records,
)


class HexDumper:
    """Render raw bytes into offset/hex/ascii dump rows."""

    def __init__(self, bytes_per_row: int = 16, start_offset: int = 0) -> None:
        if not 1 <= bytes_per_row <= 64:
            raise ValidationError("bytes_per_row must be between 1 and 64")
        if start_offset < 0:
            raise ValidationError("start_offset must be >= 0")
        self.bytes_per_row = bytes_per_row
        self.start_offset = start_offset

    @staticmethod
    def as_bytes(data: bytes | bytearray | memoryview) -> bytes:
        return bytes(data)

    def cell_at(self, data: bytes, index: int, start_offset: int | None = None) -> HexCell:
        if index < 0 or index >= len(data):
            raise IndexError(f"byte index out of range: {index}")
        base = self.start_offset if start_offset is None else start_offset
        value = data[index]
        return HexCell(offset=base + index, hex=f"{value:02x}", ascii=printable_ascii(value))

    def slice(self, data: bytes, start: int = 0, length: int | None = None) -> tuple[bytes, int]:
        if start < 0:
            raise ValidationError("slice start must be >= 0")
        if start > len(data):
            raise ValidationError("slice start exceeds data length")
        end = len(data) if length is None else min(len(data), start + max(length, 0))
        return data[start:end], start

    def dump(
        self,
        data: bytes,
        start_offset: int | None = None,
        start: int = 0,
        length: int | None = None,
    ) -> tuple[HexCell, ...]:
        """Return one :class:`HexCell` per byte of the selected window."""
        window, offset = self.slice(data, start, length)
        base = self.start_offset if start_offset is None else start_offset
        return tuple(
            HexCell(offset=base + offset + index, hex=f"{value:02x}", ascii=printable_ascii(value))
            for index, value in enumerate(window)
        )

    def rows(
        self,
        data: bytes,
        start_offset: int | None = None,
        start: int = 0,
        length: int | None = None,
        max_rows: int | None = None,
    ) -> tuple[HexRow, ...]:
        """Group cells into fixed-width rows with a shared ascii column."""
        cells = self.dump(data, start_offset=start_offset, start=start, length=length)
        limit = len(cells) if max_rows is None else min(len(cells), max_rows * self.bytes_per_row)
        selected = cells[:limit]
        chunks = tuple(
            selected[index : index + self.bytes_per_row]
            for index in range(0, len(selected), self.bytes_per_row)
        )
        return tuple(HexRow(offset=chunk[0].offset, cells=chunk) for chunk in chunks if chunk)

    @staticmethod
    def ascii_column(cells: Sequence[HexCell]) -> str:
        return "".join(cell.ascii for cell in cells)

    def format_row(self, row: HexRow) -> str:
        hex_groups = []
        for index in range(0, self.bytes_per_row, 2):
            pair = row.cells[index : index + 2]
            if pair:
                hex_groups.append(" ".join(cell.hex for cell in pair))
        hex_column = "  ".join(hex_groups)
        return f"{row.offset:08x}  {hex_column:<{self.bytes_per_row * 3 + 7}}  |{row.ascii}|"

    def render(
        self,
        data: bytes,
        start_offset: int | None = None,
        max_rows: int | None = None,
    ) -> tuple[str, ...]:
        return tuple(
            self.format_row(row)
            for row in self.rows(data, start_offset=start_offset, max_rows=max_rows)
        )

    def index_at_offset(self, offset: int, start_offset: int | None = None) -> int | None:
        base = self.start_offset if start_offset is None else start_offset
        if offset < base:
            return None
        return offset - base

    def histogram(self, data: bytes) -> tuple[tuple[int, int], ...]:
        counts: dict[int, int] = {}
        for value in data:
            counts[value] = counts.get(value, 0) + 1
        return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


class StringExtractor:
    """Find printable ASCII and UTF-16LE runs inside a byte sequence."""

    def __init__(
        self,
        min_length: int = 4,
        dedupe: bool = True,
        encodings: tuple[StringEncoding, ...] = (
            StringEncoding.ASCII,
            StringEncoding.UTF16LE,
        ),
    ) -> None:
        if min_length < 1:
            raise ValidationError("min_length must be >= 1")
        if not encodings:
            raise ValidationError("at least one encoding is required")
        self.min_length = min_length
        self.dedupe = dedupe
        self.encodings = tuple(StringEncoding.parse(item) for item in encodings)

    @staticmethod
    def is_printable(byte: int) -> bool:
        return 32 <= byte <= 126

    def extract(
        self, data: bytes, encoding: StringEncoding | str = StringEncoding.ASCII
    ) -> tuple[StringHit, ...]:
        parsed = StringEncoding.parse(encoding)
        if parsed == StringEncoding.UTF16LE:
            return self.extract_utf16le(data)
        return self._extract_single_byte(data, parsed)

    def _extract_single_byte(self, data: bytes, encoding: StringEncoding) -> tuple[StringHit, ...]:
        hits: list[StringHit] = []
        run_start = -1
        for index, byte in enumerate(data):
            if self.is_printable(byte):
                if run_start < 0:
                    run_start = index
                continue
            if run_start >= 0:
                hit = self._make_hit(data, run_start, index, encoding)
                if hit is not None:
                    hits.append(hit)
                run_start = -1
        if run_start >= 0:
            hit = self._make_hit(data, run_start, len(data), encoding)
            if hit is not None:
                hits.append(hit)
        return tuple(hits)

    def extract_utf16le(self, data: bytes) -> tuple[StringHit, ...]:
        limit = len(data) - (len(data) % 2)
        hits: list[StringHit] = []
        run_start = -1
        chars: list[str] = []
        for index in range(0, limit, 2):
            code = data[index] | (data[index + 1] << 8)
            if self.is_printable(code):
                if run_start < 0:
                    run_start = index
                chars.append(chr(code))
                continue
            if run_start >= 0:
                hit = self._build_utf16_hit(run_start, chars)
                if hit is not None:
                    hits.append(hit)
                run_start = -1
                chars = []
        if run_start >= 0:
            hit = self._build_utf16_hit(run_start, chars)
            if hit is not None:
                hits.append(hit)
        return tuple(hits)

    def _build_utf16_hit(self, offset: int, chars: list[str]) -> StringHit | None:
        value = "".join(chars)
        if len(value) < self.min_length:
            return None
        return StringHit(offset=offset, value=value, encoding=StringEncoding.UTF16LE)

    def _make_hit(
        self, data: bytes, start: int, end: int, encoding: StringEncoding
    ) -> StringHit | None:
        value = data[start:end].decode("ascii", errors="replace")
        if len(value) < self.min_length:
            return None
        return StringHit(offset=start, value=value, encoding=encoding)

    def scan(self, data: bytes) -> tuple[StringHit, ...]:
        """Scan every configured encoding and optionally de-duplicate by value."""
        hits: list[StringHit] = []
        for encoding in self.encodings:
            hits.extend(self.extract(data, encoding))
        hits.sort(key=lambda hit: (hit.offset, hit.value, hit.encoding.value))
        if not self.dedupe:
            return tuple(hits)
        seen: set[str] = set()
        unique: list[StringHit] = []
        for hit in hits:
            if hit.value in seen:
                continue
            seen.add(hit.value)
            unique.append(hit)
        return tuple(unique)

    def filter(
        self,
        hits: Sequence[StringHit],
        prefix: str | None = None,
        min_length: int | None = None,
    ) -> tuple[StringHit, ...]:
        floor = self.min_length if min_length is None else min_length
        result: list[StringHit] = []
        for hit in hits:
            if hit.length < floor:
                continue
            if prefix is not None and not hit.value.casefold().startswith(prefix.casefold()):
                continue
            result.append(hit)
        return tuple(result)

    def top(self, hits: Sequence[StringHit], limit: int = 10) -> tuple[StringHit, ...]:
        if limit < 1:
            raise ValidationError("limit must be >= 1")
        ordered = sorted(hits, key=lambda hit: (-hit.length, hit.offset, hit.value))
        return tuple(ordered[:limit])


class HashVerifier:
    """Compute and compare digests using :mod:`hashlib` only."""

    _ALGORITHMS: ClassVar[dict[HashAlgorithm, str]] = {
        HashAlgorithm.SHA256: "sha256",
        HashAlgorithm.SHA1: "sha1",
        HashAlgorithm.MD5: "md5",
    }

    def compute(self, data: bytes, algorithm: HashAlgorithm | str) -> str:
        name = self._ALGORITHMS.get(HashAlgorithm.parse(algorithm))
        if name is None:
            raise ValidationError(f"unsupported algorithm: {algorithm}")
        return hashlib.new(name, data).hexdigest()

    def compute_all(self, data: bytes) -> dict[HashAlgorithm, str]:
        return {algorithm: self.compute(data, algorithm) for algorithm in self._ALGORITHMS}

    def verify(
        self, data: bytes, algorithm: HashAlgorithm | str, expected: str
    ) -> HashVerification:
        parsed = HashAlgorithm.parse(algorithm)
        actual = self.compute(data, parsed)
        expected = str(expected).strip().casefold()
        if not hmac.compare_digest(actual, expected):
            return HashVerification(
                algorithm=parsed, expected=expected, actual=actual, matches=False
            )
        return HashVerification.from_hashes(parsed, expected, actual)

    def verify_record(
        self,
        record: EvidenceRecord,
        data: bytes,
        algorithms: Sequence[HashAlgorithm | str] = (HashAlgorithm.SHA256,),
    ) -> tuple[HashVerification, ...]:
        verifications: list[HashVerification] = []
        for algorithm in algorithms:
            parsed = HashAlgorithm.parse(algorithm)
            expected = (
                record.sha256 if parsed == HashAlgorithm.SHA256 else self.compute(data, parsed)
            )
            verifications.append(self.verify(data, parsed, expected))
        return tuple(verifications)

    def verify_manifest(
        self, data: bytes, expected: Mapping[str, str]
    ) -> tuple[HashVerification, ...]:
        return tuple(
            self.verify(data, HashAlgorithm.parse(algorithm), digest)
            for algorithm, digest in sorted(expected.items())
        )

    @staticmethod
    def chain_digest(parts: Sequence[str]) -> str:
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def digest_of(self, data: bytes) -> str:
        return self.compute(data, HashAlgorithm.SHA256)


@dataclass(frozen=True, slots=True)
class DiffItem:
    """One field-level difference between two evidence records."""

    evidence_id: str
    field: str
    before: str
    after: str

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "field": self.field,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class BundleDiff:
    """Added, removed, changed, and unchanged evidence identifiers."""

    added: tuple[str, ...] = field(default_factory=tuple)
    removed: tuple[str, ...] = field(default_factory=tuple)
    changed: tuple[str, ...] = field(default_factory=tuple)
    unchanged: tuple[str, ...] = field(default_factory=tuple)
    changes: tuple[DiffItem, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self) -> dict[str, int | bool]:
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "field_changes": len(self.changes),
            "is_empty": self.is_empty,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
            "unchanged": list(self.unchanged),
            "changes": [item.to_dict() for item in self.changes],
            "summary": self.summary(),
        }


class BundleDiffer:
    """Compare two snapshots of evidence metadata deterministically."""

    COMPARED_FIELDS = ("name", "size", "sha256", "acquired_at", "tags")

    def compare(
        self,
        left: Mapping[str, EvidenceRecord] | Sequence[EvidenceRecord],
        right: Mapping[str, EvidenceRecord] | Sequence[EvidenceRecord],
    ) -> BundleDiff:
        before = self._index(left)
        after = self._index(right)
        added = tuple(sorted(set(after) - set(before)))
        removed = tuple(sorted(set(before) - set(after)))
        changed: list[str] = []
        unchanged: list[str] = []
        changes: list[DiffItem] = []
        for identifier in sorted(set(before) & set(after)):
            items = self.field_changes(before[identifier], after[identifier])
            if items:
                changed.append(identifier)
                changes.extend(items)
            else:
                unchanged.append(identifier)
        return BundleDiff(
            added=added,
            removed=removed,
            changed=tuple(changed),
            unchanged=tuple(unchanged),
            changes=tuple(changes),
        )

    @staticmethod
    def _index(
        records: Mapping[str, EvidenceRecord] | Sequence[EvidenceRecord],
    ) -> dict[str, EvidenceRecord]:
        if isinstance(records, Mapping):
            return dict(records)
        return {record.id: record for record in records}

    def field_changes(self, before: EvidenceRecord, after: EvidenceRecord) -> tuple[DiffItem, ...]:
        items: list[DiffItem] = []
        for name in self.COMPARED_FIELDS:
            old = getattr(before, name)
            new = getattr(after, name)
            if old != new:
                items.append(
                    DiffItem(
                        evidence_id=before.id,
                        field=name,
                        before=self._render(old),
                        after=self._render(new),
                    )
                )
        return tuple(items)

    @staticmethod
    def _render(value: object) -> str:
        if isinstance(value, (tuple, list)):
            return ",".join(str(item) for item in value)
        return str(value)


class CustodyGraph:
    """An append-only, hash-linked custody chain for one evidence item."""

    def __init__(self, evidence_id: str, clock: Clock | None = None) -> None:
        if not evidence_id.strip():
            raise ValidationError("evidence_id must not be empty")
        self.evidence_id = evidence_id.strip()
        self.clock = clock or SYSTEM_CLOCK
        self._entries: list[CustodyEntry] = []

    @classmethod
    def genesis_hash(cls, evidence_id: str) -> str:
        return hashlib.sha256(f"genesis|{evidence_id.strip()}".encode()).hexdigest()

    @property
    def entries(self) -> tuple[CustodyEntry, ...]:
        return tuple(self._entries)

    @property
    def last_hash(self) -> str:
        return self._entries[-1].to_hash if self._entries else self.genesis_hash(self.evidence_id)

    def __len__(self) -> int:
        return len(self._entries)

    def link_hash(
        self,
        from_hash: str,
        timestamp: str,
        actor: str,
        action: CustodyAction,
        index: int,
    ) -> str:
        return HashVerifier.chain_digest(
            (from_hash, timestamp, actor, action.value, str(index), self.evidence_id)
        )

    def append(
        self,
        actor: str,
        action: CustodyAction | str,
        occurred_at: str | None = None,
    ) -> CustodyEntry:
        parsed = CustodyAction.parse(action)
        timestamp = occurred_at or self.clock.iso()
        index = len(self._entries)
        from_hash = self.last_hash
        to_hash = self.link_hash(from_hash, timestamp, actor, parsed, index)
        entry = CustodyEntry(
            actor=actor,
            action=parsed,
            timestamp=timestamp,
            from_hash=from_hash,
            to_hash=to_hash,
        )
        self._entries.append(entry)
        return entry

    def timeline(self) -> tuple[CustodyEntry, ...]:
        ordered = sorted(
            enumerate(self._entries),
            key=lambda pair: (pair[1].timestamp, pair[0]),
        )
        return tuple(entry for _, entry in ordered)

    def verify(self) -> ChainIntegrityResult:
        return self.verify_chain(
            self.entries, self.genesis_hash(self.evidence_id), self.evidence_id
        )

    @staticmethod
    def verify_chain(
        entries: Sequence[CustodyEntry], genesis: str, evidence_id: str = ""
    ) -> ChainIntegrityResult:
        issues: list[str] = []
        broken_index = -1
        expected_from = genesis
        for index, entry in enumerate(entries):
            if not hmac.compare_digest(entry.from_hash, expected_from):
                issues.append(f"entry {index}: from_hash does not link to predecessor")
                if broken_index < 0:
                    broken_index = index
            expected = HashVerifier.chain_digest(
                (
                    entry.from_hash,
                    entry.timestamp,
                    entry.actor,
                    entry.action.value,
                    str(index),
                    evidence_id,
                )
            )
            if not hmac.compare_digest(entry.to_hash, expected):
                issues.append(f"entry {index}: to_hash does not match canonical payload")
                if broken_index < 0:
                    broken_index = index
            expected_from = entry.to_hash
        valid = not issues
        return ChainIntegrityResult(
            valid=valid,
            length=len(entries),
            broken_index=broken_index,
            issues=tuple(issues),
        )

    @classmethod
    def from_entries(cls, evidence_id: str, entries: Sequence[CustodyEntry]) -> CustodyGraph:
        graph = cls(evidence_id)
        graph._entries = list(entries)
        return graph

    @staticmethod
    def tampered_copy(
        entries: Sequence[CustodyEntry], index: int, actor: str
    ) -> tuple[CustodyEntry, ...]:
        """Return a copy with one actor replaced, for tamper-detection tests."""
        if not 0 <= index < len(entries):
            raise IndexError(f"entry index out of range: {index}")
        updated = list(entries)
        updated[index] = replace(updated[index], actor=actor)
        return tuple(updated)

    def require_intact(self) -> None:
        result = self.verify()
        if not result.valid:
            raise ChainIntegrityError(result.headline)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "entries": [entry.to_dict() for entry in self._entries],
            "verification": self.verify().to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ChainIntegrityResult:
    """Outcome of :meth:`CustodyGraph.verify_chain`."""

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


class InspectionPipeline:
    """Compose the four inspectors into one repeatable operation."""

    def __init__(
        self,
        dumper: HexDumper | None = None,
        extractor: StringExtractor | None = None,
        verifier: HashVerifier | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.dumper = dumper or HexDumper()
        self.extractor = extractor or StringExtractor()
        self.verifier = verifier or HashVerifier()
        self.clock = clock or SYSTEM_CLOCK

    def inspect(
        self,
        record: EvidenceRecord,
        data: bytes,
        custody: Sequence[CustodyEntry] = (),
        max_rows: int | None = None,
    ) -> InspectionResult:
        rows = self.dumper.rows(data, max_rows=max_rows)
        hits = self.extractor.scan(data)
        verifications = self.verifier.verify_record(record, data)
        notes: list[str] = []
        if len(data) != record.size:
            notes.append(f"declared size {record.size} differs from {len(data)} bytes inspected")
        if not all(item.matches for item in verifications):
            notes.append("stored digest does not match inspected bytes")
        return InspectionResult(
            evidence_id=record.id,
            hex_rows=rows,
            strings=hits,
            verifications=verifications,
            custody=tuple(custody),
            generated_at=self.clock.iso(),
            notes=tuple(notes),
        )

    def inspect_bundle(
        self,
        records: Sequence[EvidenceRecord],
        payloads: Mapping[str, bytes],
    ) -> tuple[InspectionResult, ...]:
        results: list[InspectionResult] = []
        for record in sorted_records(records):
            data = payloads.get(record.id, b"")
            results.append(self.inspect(record, data))
        return tuple(results)


def assert_verified(result: InspectionResult) -> None:
    """Raise :class:`HashMismatchError` unless every digest matched."""
    if not result.all_verified:
        raise HashMismatchError(f"evidence {result.evidence_id} failed digest verification")
