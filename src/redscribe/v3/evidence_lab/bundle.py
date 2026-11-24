"""Content-addressed evidence bundle comparison."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.types import (
    BundleDelta,
    BundleDeltaKind,
    BundleDiff,
    BundleEntry,
)


def bundle_index(entries: Iterable[BundleEntry]) -> dict[str, BundleEntry]:
    """Index bundle entries by key, rejecting duplicates."""
    index: dict[str, BundleEntry] = {}
    for entry in entries:
        if not entry.key.strip():
            raise InvalidInputError("Bundle entry key cannot be blank")
        if entry.key in index:
            raise InvalidInputError(f"Duplicate bundle key: {entry.key}")
        index[entry.key] = entry
    return index


def entries_from_records(records: Iterable[dict[str, Any]]) -> tuple[BundleEntry, ...]:
    """Convert JSON-like records into bundle entries."""
    return tuple(
        BundleEntry(
            key=str(record.get("key", "")),
            sha256=str(record.get("sha256", "")),
            blake2b=str(record.get("blake2b", "")),
            size_bytes=int(record.get("size_bytes", 0)),
            label=str(record.get("label", "")),
        )
        for record in records
    )


def canonical_bundle_json(entries: Sequence[BundleEntry]) -> str:
    """Serialize a bundle deterministically for fingerprinting."""
    payload = sorted((entry.as_dict() for entry in entries), key=lambda item: str(item["key"]))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def bundle_fingerprint(entries: Sequence[BundleEntry]) -> str:
    """Return a SHA-256 fingerprint of the complete bundle."""
    return hashlib.sha256(canonical_bundle_json(entries).encode("utf-8")).hexdigest()


def diff_bundles(
    left: Sequence[BundleEntry],
    right: Sequence[BundleEntry],
    *,
    left_id: str = "left",
    right_id: str = "right",
) -> BundleDiff:
    """Compare two bundles key by key."""
    left_index = bundle_index(left)
    right_index = bundle_index(right)
    keys = sorted(set(left_index) | set(right_index))
    deltas: list[BundleDelta] = []
    for key in keys:
        left_entry = left_index.get(key)
        right_entry = right_index.get(key)
        if left_entry is None and right_entry is not None:
            deltas.append(
                BundleDelta(
                    key, BundleDeltaKind.ADDED, right=right_entry, size_delta=right_entry.size_bytes
                )
            )
        elif right_entry is None and left_entry is not None:
            deltas.append(
                BundleDelta(
                    key, BundleDeltaKind.REMOVED, left=left_entry, size_delta=-left_entry.size_bytes
                )
            )
        elif left_entry is not None and right_entry is not None:
            if left_entry.identity() != right_entry.identity():
                deltas.append(
                    BundleDelta(
                        key,
                        BundleDeltaKind.MODIFIED,
                        left=left_entry,
                        right=right_entry,
                        size_delta=right_entry.size_bytes - left_entry.size_bytes,
                    )
                )
            else:
                deltas.append(
                    BundleDelta(key, BundleDeltaKind.UNCHANGED, left=left_entry, right=right_entry)
                )
    counts: dict[str, int] = {kind.value: 0 for kind in BundleDeltaKind}
    for delta in deltas:
        counts[delta.kind.value] += 1
    return BundleDiff(
        left_id=left_id,
        right_id=right_id,
        deltas=tuple(deltas),
        counts=counts,
        fingerprint_left=bundle_fingerprint(left),
        fingerprint_right=bundle_fingerprint(right),
    )


def build_bundle(entries: Sequence[BundleEntry], *, label: str = "") -> dict[str, Any]:
    """Return a manifest-like bundle dictionary."""
    index = bundle_index(entries)
    return {
        "format": "redscribe-evidence-bundle",
        "version": 1,
        "label": label,
        "count": len(index),
        "total_bytes": sum(entry.size_bytes for entry in index.values()),
        "fingerprint": bundle_fingerprint(entries),
        "entries": [index[key].as_dict() for key in sorted(index)],
    }


def summarize_bundle(entries: Sequence[BundleEntry]) -> dict[str, object]:
    """Return compact bundle statistics."""
    index = bundle_index(entries)
    return {
        "count": len(index),
        "total_bytes": sum(entry.size_bytes for entry in index.values()),
        "with_blake2b": sum(1 for entry in index.values() if entry.blake2b),
        "fingerprint": bundle_fingerprint(entries),
    }


def diff_size_total(diff: BundleDiff) -> int:
    """Return the net size change across all deltas."""
    return sum(delta.size_delta for delta in diff.deltas)


def changed_keys(diff: BundleDiff) -> tuple[str, ...]:
    """Return the keys that differ between the two bundles."""
    return tuple(delta.key for delta in diff.changed())
