"""Pure, worker-friendly functions used by the index and the harness.

None of these functions touch the filesystem, the clock, module globals, or
their arguments. They can be moved into a web worker or a thread pool without
changing behavior, which is what makes the benchmark reproducible.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TypeVar

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.events.types import EventRecord
from redscribe.v3.performance.models import IndexDocument

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
T = TypeVar("T")


def tokenize(text: str, *, min_length: int = 2) -> tuple[str, ...]:
    """Split text into a stable, de-duplicated token tuple."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_PATTERN.findall(text.casefold()):
        if len(match) < min_length or match in seen:
            continue
        seen.add(match)
        found.append(match)
    return tuple(found)


def build_postings(
    documents: Iterable[IndexDocument],
) -> dict[str, tuple[str, ...]]:
    """Build an inverted index from a document collection."""
    gathered: dict[str, set[str]] = {}
    for document in documents:
        for token in document.tokens:
            gathered.setdefault(token, set()).add(document.key)
    return {token: tuple(sorted(keys)) for token, keys in sorted(gathered.items())}


def merge_postings(
    postings: Mapping[str, Sequence[str]],
    tokens: Sequence[str],
    *,
    require_all: bool = False,
) -> tuple[str, ...]:
    """Union or intersect posting lists for a set of query tokens."""
    lists = [set(postings.get(token, ())) for token in tokens]
    if not lists:
        return ()
    if require_all:
        merged: set[str] = set(lists[0])
        for entries in lists[1:]:
            merged &= entries
    else:
        merged = set()
        for entries in lists:
            merged.update(entries)
    return tuple(sorted(merged))


def score_candidates(
    candidates: Sequence[str],
    tokens: Sequence[str],
    postings: Mapping[str, Sequence[str]],
) -> dict[str, int]:
    """Score candidates by query-token overlap."""
    wanted = tuple(sorted(set(tokens)))
    scores: dict[str, int] = {}
    for key in candidates:
        score = 0
        for token in wanted:
            if key in postings.get(token, ()):
                score += 1
        scores[key] = score
    return scores


def rank_refs(
    scores: Mapping[str, int],
    documents: Mapping[str, IndexDocument],
    limit: int,
) -> tuple[EntityRef, ...]:
    """Rank scored documents and return a bounded reference list."""
    if limit < 1:
        raise ValueError("Limit must be positive")
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    refs: list[EntityRef] = []
    for key in ordered[:limit]:
        document = documents.get(key)
        if document is not None:
            refs.append(document.ref)
    return tuple(refs)


def apply_delta_postings(
    postings: Mapping[str, Sequence[str]],
    upserts: Sequence[IndexDocument],
    removals: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    """Return a new posting map after applying a mutation batch."""
    removed = set(removals)
    mutable: dict[str, set[str]] = {token: set(keys) for token, keys in postings.items()}
    for keys in mutable.values():
        keys.difference_update(removed)
    for document in upserts:
        for token in document.tokens:
            mutable.setdefault(token, set()).add(document.key)
    return {token: tuple(sorted(keys)) for token, keys in sorted(mutable.items()) if keys}


def chunk(items: Sequence[T], size: int) -> tuple[tuple[T, ...], ...]:
    """Split a sequence into fixed-size chunks."""
    if size < 1:
        raise ValueError("Chunk size must be positive")
    return tuple(tuple(items[index : index + size]) for index in range(0, len(items), size))


def visible_range(
    count: int,
    scroll_top: float,
    viewport_height: float,
    row_height: float,
    overscan: int = 4,
) -> tuple[int, int]:
    """Return the half-open window of rows that should be rendered."""
    if count <= 0 or row_height <= 0 or viewport_height <= 0:
        return (0, 0)
    first = max(0, int(scroll_top / row_height) - max(0, overscan))
    visible = int(viewport_height / row_height) + 1
    last = min(count, first + visible + 2 * max(0, overscan))
    return (first, last)


def paginate_refs(
    refs: Sequence[EntityRef], offset: int, size: int
) -> tuple[tuple[EntityRef, ...], bool]:
    """Return a bounded slice and whether more rows remain."""
    if offset < 0 or size < 1:
        raise ValueError("Offset and size must be valid")
    window = tuple(refs[offset : offset + size])
    return window, offset + size < len(refs)


def event_fingerprint(records: Sequence[EventRecord]) -> str:
    """Derive a stable digest of an event batch without serializing payloads."""
    parts = [f"{record.sequence}:{record.kind}:{record.subject_ref}" for record in records]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()


def estimate_event_bytes(records: Sequence[EventRecord]) -> int:
    """Estimate the serialized size of an event batch."""
    total = 0
    for record in records:
        total += len(record.kind) + len(record.subject_ref) + len(record.event.actor)
        total += len(record.event.correlation_id) + 96
        for key, value in record.event.payload.items():
            total += len(key) + (len(value) if isinstance(value, str) else 16)
    return total
