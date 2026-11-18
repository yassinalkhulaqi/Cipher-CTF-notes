"""Deterministic coalescing for block-editor autosave queues."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from redscribe.v2.blocks.constants import (
    DEFAULT_AUTOSAVE_INTERVAL_MS,
    DEFAULT_AUTOSAVE_MAX_WAIT_MS,
    MAX_AUTOSAVE_INTERVAL_MS,
    MAX_AUTOSAVE_MAX_WAIT_MS,
)
from redscribe.v2.blocks.diff import PatchEntry, merge_entries
from redscribe.v2.blocks.model import BlockDocument


@dataclass(frozen=True, slots=True)
class AutosaveBatch:
    """One coalesced save operation ready for persistence."""

    document_id: str
    base_revision: int
    entries: tuple[PatchEntry, ...]
    merged_from: int
    first_at_ms: float
    last_at_ms: float
    token: str = ""
    label: str = ""

    @property
    def size(self) -> int:
        return len(self.entries)

    @property
    def age_ms(self) -> float:
        return max(0.0, self.last_at_ms - self.first_at_ms)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "base_revision": self.base_revision,
            "entries": [entry.as_dict() for entry in self.entries],
            "merged_from": self.merged_from,
            "size": self.size,
            "age_ms": round(self.age_ms, 3),
            "token": self.token,
            "label": self.label,
        }


@dataclass(slots=True)
class _Bucket:
    document_id: str
    base_revision: int
    entries: list[PatchEntry] = field(default_factory=list)
    first_at_ms: float = 0.0
    last_at_ms: float = 0.0
    merged_from: int = 0
    token: str = ""
    label: str = ""

    def to_batch(self) -> AutosaveBatch:
        return AutosaveBatch(
            document_id=self.document_id,
            base_revision=self.base_revision,
            entries=merge_entries(self.entries),
            merged_from=self.merged_from,
            first_at_ms=self.first_at_ms,
            last_at_ms=self.last_at_ms,
            token=self.token,
            label=self.label,
        )


def now_ms() -> float:
    """Return a monotonic millisecond clock value."""
    return time.monotonic() * 1000.0


def coalesce_batches(batches: Iterable[AutosaveBatch]) -> list[AutosaveBatch]:
    """Merge batches that target the same document."""
    buckets: dict[str, _Bucket] = {}
    for batch in batches:
        bucket = buckets.get(batch.document_id)
        if bucket is None:
            buckets[batch.document_id] = _Bucket(
                document_id=batch.document_id,
                base_revision=batch.base_revision,
                entries=list(batch.entries),
                first_at_ms=batch.first_at_ms,
                last_at_ms=batch.last_at_ms,
                merged_from=batch.merged_from,
                token=batch.token,
                label=batch.label,
            )
            continue
        bucket.entries.extend(batch.entries)
        bucket.first_at_ms = min(bucket.first_at_ms, batch.first_at_ms)
        bucket.last_at_ms = max(bucket.last_at_ms, batch.last_at_ms)
        bucket.merged_from += batch.merged_from
        bucket.token = batch.token or bucket.token
        bucket.label = batch.label or bucket.label
    return [
        bucket.to_batch() for bucket in sorted(buckets.values(), key=lambda item: item.first_at_ms)
    ]


class AutosaveCoalescer:
    """Accumulate edits per document until a debounce window expires."""

    def __init__(
        self,
        *,
        interval_ms: int = DEFAULT_AUTOSAVE_INTERVAL_MS,
        max_wait_ms: int = DEFAULT_AUTOSAVE_MAX_WAIT_MS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if interval_ms < 0 or interval_ms > MAX_AUTOSAVE_INTERVAL_MS:
            raise ValueError("Invalid autosave interval")
        if max_wait_ms < 0 or max_wait_ms > MAX_AUTOSAVE_MAX_WAIT_MS:
            raise ValueError("Invalid autosave max wait")
        self.interval_ms = interval_ms
        self.max_wait_ms = max(max_wait_ms, interval_ms)
        self._clock = clock or now_ms
        self._buckets: dict[str, _Bucket] = {}

    def record(
        self,
        document: BlockDocument,
        entries: Sequence[PatchEntry],
        *,
        token: str = "",
        label: str = "",
    ) -> AutosaveBatch | None:
        """Queue operations and return a batch when the wait cap is reached."""
        if not entries:
            return None
        current = self._clock()
        bucket = self._buckets.get(document.id)
        if bucket is None:
            bucket = _Bucket(
                document_id=document.id,
                base_revision=document.revision,
                first_at_ms=current,
                last_at_ms=current,
                merged_from=1,
                token=token,
                label=label,
            )
            self._buckets[document.id] = bucket
        elif bucket.base_revision != document.revision:
            bucket.base_revision = document.revision
            bucket.entries.clear()
            bucket.first_at_ms = current
            bucket.merged_from = 1
        else:
            bucket.merged_from += 1
        bucket.entries.extend(entries)
        bucket.last_at_ms = current
        bucket.token = token or bucket.token
        bucket.label = label or bucket.label
        if current - bucket.first_at_ms >= self.max_wait_ms:
            return self.flush_document(document.id)
        return None

    @property
    def pending(self) -> tuple[AutosaveBatch, ...]:
        """Return queued batches without removing them."""
        return tuple(
            bucket.to_batch()
            for bucket in sorted(self._buckets.values(), key=lambda item: item.first_at_ms)
        )

    def has_pending(self, document_id: str | None = None) -> bool:
        """Return whether any matching edits are queued."""
        if document_id is None:
            return bool(self._buckets)
        return document_id in self._buckets

    def due(self, at_ms: float | None = None) -> tuple[AutosaveBatch, ...]:
        """Return batches whose debounce window has expired."""
        current = self._clock() if at_ms is None else at_ms
        result: list[AutosaveBatch] = []
        for bucket in sorted(self._buckets.values(), key=lambda item: item.first_at_ms):
            idle = current - bucket.last_at_ms >= self.interval_ms
            waited = current - bucket.first_at_ms >= self.max_wait_ms
            if idle or waited:
                result.append(bucket.to_batch())
        return tuple(result)

    def flush(self, at_ms: float | None = None) -> tuple[AutosaveBatch, ...]:
        """Remove and return all batches whose windows have expired."""
        due = self.due(at_ms)
        for batch in due:
            self._buckets.pop(batch.document_id, None)
        return due

    def flush_all(self) -> tuple[AutosaveBatch, ...]:
        """Remove and return every pending batch regardless of timing."""
        batches = self.pending
        self._buckets.clear()
        return batches

    def flush_document(self, document_id: str) -> AutosaveBatch | None:
        """Remove and return the batch for one document."""
        bucket = self._buckets.pop(document_id, None)
        return bucket.to_batch() if bucket is not None else None

    def acknowledge(self, document_id: str, revision: int) -> bool:
        """Drop a queued batch once its revision has been persisted."""
        bucket = self._buckets.get(document_id)
        if bucket is None:
            return False
        if bucket.base_revision > revision:
            return False
        self._buckets.pop(document_id, None)
        return True

    def cancel(self, document_id: str) -> bool:
        """Discard queued edits for one document."""
        return self._buckets.pop(document_id, None) is not None

    def clear(self) -> None:
        """Discard every queued edit."""
        self._buckets.clear()

    def state(self, at_ms: float | None = None) -> dict[str, Any]:
        """Return a telemetry-friendly summary of the queue."""
        current = self._clock() if at_ms is None else at_ms
        batches = self.pending
        next_in: float | None = None
        for batch in batches:
            remaining = self.interval_ms - (current - batch.last_at_ms)
            if remaining > 0:
                next_in = remaining if next_in is None else min(next_in, remaining)
        return {
            "pending": len(batches),
            "document_ids": [batch.document_id for batch in batches],
            "operations": sum(batch.size for batch in batches),
            "merged_edits": sum(batch.merged_from for batch in batches),
            "next_flush_ms": round(next_in or 0.0, 3),
            "interval_ms": self.interval_ms,
            "max_wait_ms": self.max_wait_ms,
        }


def next_flush_delay(state: dict[str, Any]) -> int:
    """Convert autosave state into a timer delay for the frontend."""
    value = state.get("next_flush_ms", 0)
    if not isinstance(value, (int, float)) or value < 0:
        return 0
    return max(0, min(60_000, int(value) + 1))


def batch_for_document(batches: Sequence[AutosaveBatch], document_id: str) -> AutosaveBatch | None:
    """Find one document's batch in a collection."""
    for batch in batches:
        if batch.document_id == document_id:
            return batch
    return None


def with_label(batch: AutosaveBatch, label: str) -> AutosaveBatch:
    """Return a labelled copy of a batch."""
    return replace(batch, label=label)
