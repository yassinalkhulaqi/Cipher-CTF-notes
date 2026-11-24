"""Incremental in-memory search index with generation-based cache coherence.

The index never rescans the vault to answer a query. Mutations produce a small
delta, postings are updated in place, and cached query results are evicted only
when their tokens are actually touched. The harness uses this to demonstrate
that edits do not trigger a full-vault rebuild.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.performance.meter import Meter
from redscribe.v3.performance.models import (
    IndexDelta,
    IndexDocument,
    QueryPlan,
    QueryResult,
    QuerySpec,
)
from redscribe.v3.performance.queryplan import PlanRecorder
from redscribe.v3.performance.workers import (
    apply_delta_postings,
    build_postings,
    merge_postings,
    rank_refs,
    score_candidates,
)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    """A cached, bounded result window."""

    refs: tuple[EntityRef, ...]
    generation: int
    required_tokens: frozenset[str]
    candidates: int


class IncrementalIndex:
    """Maintain an inverted index across incremental mutations."""

    def __init__(self, *, meter: Meter | None = None) -> None:
        self._meter: Meter = meter or Meter()
        self._documents: dict[str, IndexDocument] = {}
        self._postings: dict[str, tuple[str, ...]] = {}
        self._generation = 0
        self._mutations = 0
        self._rebuilds = 0
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_hits = 0
        self._cache_evictions = 0
        self._last_plan: QueryPlan | None = None

    @property
    def generation(self) -> int:
        """Current index generation."""
        return self._generation

    @property
    def meter(self) -> Meter:
        """Meter attached to this index."""
        return self._meter

    @property
    def last_plan(self) -> QueryPlan | None:
        """Plan produced by the most recent query, if any."""
        return self._last_plan

    @property
    def size(self) -> int:
        """Number of indexed documents."""
        return len(self._documents)

    def add(self, document: IndexDocument) -> int:
        """Index one document and return the new generation."""
        return self.apply(IndexDelta(upserts=(document,)))

    def remove(self, key: str) -> int:
        """Remove one document and return the new generation."""
        return self.apply(IndexDelta(removals=(key,)))

    def apply(self, delta: IndexDelta) -> int:
        """Apply a mutation batch as a single generation."""
        if delta.is_empty():
            return self._generation
        touched: set[str] = set()
        for document in delta.upserts:
            previous = self._documents.get(document.key)
            if previous is not None:
                touched.update(previous.tokens)
            touched.update(document.tokens)
            self._documents[document.key] = document
        for key in delta.removals:
            previous = self._documents.pop(key, None)
            if previous is not None:
                touched.update(previous.tokens)
        self._postings = apply_delta_postings(self._postings, delta.upserts, delta.removals)
        self._evict_touched(touched)
        self._generation += 1
        self._mutations += delta.size
        self._meter.record("index_mutation", delta.size)
        return self._generation

    def _evict_touched(self, tokens: set[str]) -> None:
        """Drop only cache entries whose result could have changed."""
        if not tokens:
            return
        for fingerprint, entry in tuple(self._cache.items()):
            if entry.required_tokens & tokens:
                del self._cache[fingerprint]
                self._cache_evictions += 1

    def query(self, spec: QuerySpec) -> QueryResult:
        """Run a bounded query, using the cache when it is still coherent."""
        tokens = tuple(sorted(set(spec.tokens)))
        required = frozenset(tokens)
        recorder = PlanRecorder(self._meter, spec.fingerprint, self._generation)
        recorder.step(
            "cache_lookup",
            f"fingerprint={spec.fingerprint}",
            rows_in=1,
            rows_out=1,
            operation="fingerprint_step",
            count=1,
        )
        cached = self._cache.get(spec.fingerprint)
        if cached is not None:
            self._cache_hits += 1
            recorder.step(
                "cache_hit",
                f"generation={cached.generation}",
                rows_in=cached.candidates,
                rows_out=len(cached.refs),
                operation="row_materialize",
                count=len(cached.refs),
            )
            plan = recorder.finish(cache_hit=True)
            self._last_plan = plan
            return QueryResult(
                refs=cached.refs,
                generation=self._generation,
                cache_hit=True,
                candidates=cached.candidates,
                plan=plan,
            )

        lists = {token: self._postings.get(token, ()) for token in tokens}
        recorder.step(
            "posting_lookup",
            f"tokens={len(tokens)}",
            rows_in=len(tokens),
            rows_out=len(lists),
            operation="posting_lookup",
            count=len(tokens),
        )
        candidates = merge_postings(lists, tokens, require_all=spec.require_all)
        recorder.step(
            "posting_union",
            f"mode={'all' if spec.require_all else 'any'}",
            rows_in=sum(len(entries) for entries in lists.values()),
            rows_out=len(candidates),
            operation="posting_union",
            count=len(candidates),
        )
        scores = score_candidates(candidates, tokens, lists)
        recorder.step(
            "candidate_score",
            f"tokens={len(tokens)}",
            rows_in=len(candidates),
            rows_out=len(scores),
            operation="candidate_score",
            count=len(candidates) * max(1, len(tokens)),
        )
        refs = rank_refs(scores, self._documents, spec.limit)
        recorder.step(
            "rank_window",
            f"limit={spec.limit}",
            rows_in=len(scores),
            rows_out=len(refs),
            operation="row_materialize",
            count=len(refs),
        )
        plan = recorder.finish()
        self._last_plan = plan
        self._cache[spec.fingerprint] = _CacheEntry(
            refs=refs,
            generation=self._generation,
            required_tokens=required,
            candidates=len(candidates),
        )
        return QueryResult(
            refs=refs,
            generation=self._generation,
            cache_hit=False,
            candidates=len(candidates),
            plan=plan,
        )

    def postings_for(self, token: str) -> tuple[str, ...]:
        """Return document keys indexed under one token."""
        return self._postings.get(token, ())

    def documents(self) -> tuple[IndexDocument, ...]:
        """Return indexed documents in stable key order."""
        return tuple(self._documents[key] for key in sorted(self._documents))

    def rebuild(self) -> dict[str, tuple[str, ...]]:
        """Build a reference posting map by scanning every document."""
        self._rebuilds += 1
        self._meter.record("full_scan_document", len(self._documents))
        return build_postings(self.documents())

    def is_consistent(self) -> bool:
        """Return whether incremental postings equal a full rebuild."""
        return self._postings == self.rebuild()

    def fingerprint(self) -> str:
        """Return a stable digest of indexed document keys and versions."""
        raw = "|".join(
            f"{key}@{self._documents[key].version}" for key in sorted(self._documents)
        ).encode("utf-8")
        return hashlib.blake2b(raw, digest_size=10).hexdigest()

    def stats(self) -> dict[str, Any]:
        """Return a compact statistics snapshot for the HUD."""
        return {
            "documents": len(self._documents),
            "posting_tokens": len(self._postings),
            "generation": self._generation,
            "mutations": self._mutations,
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_evictions": self._cache_evictions,
            "rebuilds": self._rebuilds,
            "modeled_ms": self._meter.modeled_ms,
        }
