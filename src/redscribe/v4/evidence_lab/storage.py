"""Indexed in-memory persistence for evidence metadata and inspection results.

The store is deliberately adapter-shaped: every read goes through the hash and
tag indexes, and every mutation keeps those indexes consistent. A future SQL
adapter can implement the same surface without changing callers. No bytes are
read from disk and no external commands are invoked.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v4.clock import SYSTEM_CLOCK, Clock
from redscribe.v4.pagination import weak_etag

from .service import BundleDiffer, CustodyGraph
from .types import (
    CustodyAction,
    CustodyEntry,
    EvidenceLabError,
    EvidenceRecord,
    InspectionResult,
    ValidationError,
    sorted_records,
)

MANIFEST_SCHEMA = "redscribe.evidence-lab/v4"


class StoreError(EvidenceLabError):
    """Raised when a store operation cannot be satisfied."""


@dataclass(frozen=True, slots=True)
class StoreStats:
    """A point-in-time summary of store contents."""

    records: int
    tags: int
    digests: int
    cached_inspections: int
    custody_entries: int
    etag: str

    def to_dict(self) -> dict[str, int | str]:
        return {
            "records": self.records,
            "tags": self.tags,
            "digests": self.digests,
            "cached_inspections": self.cached_inspections,
            "custody_entries": self.custody_entries,
            "etag": self.etag,
        }


@dataclass(slots=True)
class EvidenceStore:
    """CRUD + indexes + inspection cache for evidence records."""

    clock: Clock = field(default_factory=lambda: SYSTEM_CLOCK)
    _records: dict[str, EvidenceRecord] = field(default_factory=dict, repr=False)
    _by_hash: dict[str, set[str]] = field(default_factory=dict, repr=False)
    _by_tag: dict[str, set[str]] = field(default_factory=dict, repr=False)
    _inspections: dict[str, InspectionResult] = field(default_factory=dict, repr=False)
    _custody: dict[str, list[CustodyEntry]] = field(default_factory=dict, repr=False)

    @classmethod
    def from_records(
        cls, records: Iterable[EvidenceRecord], clock: Clock | None = None
    ) -> EvidenceStore:
        store = cls(clock=clock or SYSTEM_CLOCK)
        for record in records:
            store.add(record)
        return store

    def add(self, record: EvidenceRecord) -> EvidenceRecord:
        if record.id in self._records:
            raise StoreError(f"duplicate evidence id: {record.id}")
        self._records[record.id] = record
        self._index(record)
        return record

    def put(self, record: EvidenceRecord) -> EvidenceRecord:
        """Insert or replace a record, refreshing every index."""
        previous = self._records.get(record.id)
        if previous is not None:
            self._unindex(previous)
        self._records[record.id] = record
        self._index(record)
        return record

    def get(self, identifier: str) -> EvidenceRecord:
        record = self._records.get(identifier)
        if record is None:
            raise StoreError(f"evidence not found: {identifier}")
        return record

    def find(self, identifier: str) -> EvidenceRecord | None:
        return self._records.get(identifier)

    def remove(self, identifier: str) -> EvidenceRecord:
        record = self.get(identifier)
        self._unindex(record)
        del self._records[identifier]
        self._inspections.pop(identifier, None)
        self._custody.pop(identifier, None)
        return record

    def all(self) -> tuple[EvidenceRecord, ...]:
        return sorted_records(self._records.values())

    def page(self, offset: int = 0, size: int = 50) -> tuple[EvidenceRecord, ...]:
        if offset < 0 or size < 1:
            raise ValidationError("invalid pagination window")
        return self.all()[offset : offset + size]

    def __len__(self) -> int:
        return len(self._records)

    def contains(self, identifier: str) -> bool:
        return identifier in self._records

    def _index(self, record: EvidenceRecord) -> None:
        self._by_hash.setdefault(record.sha256, set()).add(record.id)
        for tag in record.tags:
            self._by_tag.setdefault(tag, set()).add(record.id)

    def _unindex(self, record: EvidenceRecord) -> None:
        holders = self._by_hash.get(record.sha256)
        if holders is not None:
            holders.discard(record.id)
            if not holders:
                del self._by_hash[record.sha256]
        for tag in record.tags:
            tagged = self._by_tag.get(tag)
            if tagged is not None:
                tagged.discard(record.id)
                if not tagged:
                    del self._by_tag[tag]

    def by_hash(self, digest: str) -> tuple[EvidenceRecord, ...]:
        identifiers = self._by_hash.get(str(digest).strip().casefold(), set())
        return tuple(
            sorted_records(self._records[item] for item in identifiers if item in self._records)
        )

    def hash_count(self, digest: str) -> int:
        return len(self._by_hash.get(str(digest).strip().casefold(), set()))

    def by_tag(self, tag: str) -> tuple[EvidenceRecord, ...]:
        identifiers = self._by_tag.get(str(tag).strip().casefold(), set())
        return tuple(
            sorted_records(self._records[item] for item in identifiers if item in self._records)
        )

    def all_tags(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_tag))

    def find_by_name(self, name: str) -> tuple[EvidenceRecord, ...]:
        needle = str(name).strip().casefold()
        return tuple(record for record in self.all() if needle in record.name.casefold())

    def reindex(self) -> int:
        """Rebuild all indexes from canonical records; return record count."""
        self._by_hash.clear()
        self._by_tag.clear()
        for record in self._records.values():
            self._index(record)
        return len(self._records)

    def index_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        expected_hash: dict[str, set[str]] = {}
        expected_tag: dict[str, set[str]] = {}
        for record in self._records.values():
            expected_hash.setdefault(record.sha256, set()).add(record.id)
            for tag in record.tags:
                expected_tag.setdefault(tag, set()).add(record.id)
        if expected_hash != self._by_hash:
            issues.append("hash index is stale")
        if expected_tag != self._by_tag:
            issues.append("tag index is stale")
        return tuple(issues)

    def cache_inspection(self, result: InspectionResult) -> InspectionResult:
        if not self.contains(result.evidence_id):
            raise StoreError(f"cannot cache inspection for unknown id: {result.evidence_id}")
        self._inspections[result.evidence_id] = result
        return result

    def inspection(self, identifier: str) -> InspectionResult | None:
        return self._inspections.get(identifier)

    def inspection_or_raise(self, identifier: str) -> InspectionResult:
        result = self.inspection(identifier)
        if result is None:
            raise StoreError(f"no cached inspection for: {identifier}")
        return result

    def invalidate(self, identifier: str) -> bool:
        return self._inspections.pop(identifier, None) is not None

    def clear_cache(self) -> int:
        count = len(self._inspections)
        self._inspections.clear()
        return count

    def cached_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._inspections))

    def record_custody(
        self,
        identifier: str,
        actor: str,
        action: CustodyAction | str,
        occurred_at: str | None = None,
    ) -> CustodyEntry:
        record = self.get(identifier)
        graph = CustodyGraph.from_entries(record.id, self._custody.get(record.id, ()))
        entry = graph.append(actor, action, occurred_at)
        self._custody[record.id] = list(graph.entries)
        return entry

    def custody_for(self, identifier: str) -> tuple[CustodyEntry, ...]:
        return tuple(self._custody.get(identifier, ()))

    def verify_custody(self, identifier: str) -> bool:
        record = self.get(identifier)
        graph = CustodyGraph.from_entries(record.id, self.custody_for(record.id))
        return graph.verify().valid

    def stats(self) -> StoreStats:
        entries = sum(len(items) for items in self._custody.values())
        fingerprint = "|".join(
            f"{record.id}:{record.sha256}:{record.size}" for record in self.all()
        )
        return StoreStats(
            records=len(self._records),
            tags=len(self._by_tag),
            digests=len(self._by_hash),
            cached_inspections=len(self._inspections),
            custody_entries=entries,
            etag=weak_etag(fingerprint),
        )

    def export_manifest(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "generated_at": self.clock.iso(),
            "stats": self.stats().to_dict(),
            "records": [record.to_dict() for record in self.all()],
            "tag_index": {tag: sorted(ids) for tag, ids in sorted(self._by_tag.items())},
            "hash_index": {digest: sorted(ids) for digest, ids in sorted(self._by_hash.items())},
            "cached_inspections": list(self.cached_ids()),
        }

    def import_manifest(self, manifest: Mapping[str, Any]) -> tuple[EvidenceRecord, ...]:
        if manifest.get("schema") != MANIFEST_SCHEMA:
            raise StoreError("unsupported manifest schema")
        raw_records = manifest.get("records", [])
        if not isinstance(raw_records, list):
            raise StoreError("manifest records must be a list")
        imported: list[EvidenceRecord] = []
        differ = BundleDiffer()
        snapshot: dict[str, EvidenceRecord] = {}
        for item in raw_records:
            if not isinstance(item, Mapping):
                raise StoreError("manifest records must be objects")
            record = EvidenceRecord.from_dict(item)
            snapshot[record.id] = record
        for record in sorted_records(snapshot.values()):
            existing = self.find(record.id)
            if existing is None:
                self.add(record)
            elif differ.field_changes(existing, record):
                self.put(record)
            imported.append(record)
        return tuple(imported)

    def diff(self, other: EvidenceStore) -> dict[str, Any]:
        differ = BundleDiffer()
        return differ.compare(self._records, other._records).to_dict()

    def clear(self) -> None:
        self._records.clear()
        self._by_hash.clear()
        self._by_tag.clear()
        self._inspections.clear()
        self._custody.clear()

    def snapshot(self) -> dict[str, EvidenceRecord]:
        return dict(self._records)

    def sequence(self, records: Sequence[EvidenceRecord]) -> tuple[EvidenceRecord, ...]:
        """Return records that exist in this store, in caller-supplied order."""
        return tuple(record for record in records if self.contains(record.id))
