"""Value types shared by the V3 performance and scale tooling.

Everything in this package is deliberately in-memory and deterministic. The
models here are the wire shape used by the performance namespace, the benchmark
harness, and the frontend HUD, so no branch needs to invent its own metrics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.entities.types import EntityId, EntityRecord, EntityRef
from redscribe.v3.events.types import EventRecord


@dataclass(frozen=True, slots=True)
class IndexDocument:
    """One searchable document in the incremental index."""

    ref: EntityRef
    text: str
    tokens: tuple[str, ...]
    version: int = 1

    @property
    def key(self) -> str:
        """Stable index key."""
        return str(self.ref.entity_id)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "label": self.ref.label,
            "tokens": list(self.tokens),
            "version": self.version,
            "characters": len(self.text),
        }


@dataclass(frozen=True, slots=True)
class IndexDelta:
    """A batch of index mutations applied as one generation."""

    upserts: tuple[IndexDocument, ...] = ()
    removals: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        """Number of mutations in the batch."""
        return len(self.upserts) + len(self.removals)

    def is_empty(self) -> bool:
        """Return whether the batch has no mutations."""
        return self.size == 0


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """A bounded search request against the incremental index."""

    tokens: tuple[str, ...]
    limit: int = 50
    require_all: bool = False

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 500:
            raise ValueError("Query limit must be between 1 and 500")
        if not self.tokens:
            raise ValueError("Query must contain at least one token")

    @property
    def fingerprint(self) -> str:
        """Stable cache key for the query."""
        return "|".join((*sorted(set(self.tokens)), str(self.limit), str(self.require_all)))


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Bounded result window returned by the index."""

    refs: tuple[EntityRef, ...]
    generation: int
    cache_hit: bool
    candidates: int
    plan: QueryPlan | None = None


@dataclass(frozen=True, slots=True)
class PlanNode:
    """One instrumented step of a query plan."""

    step: str
    detail: str
    rows_in: int = 0
    rows_out: int = 0
    cost_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "step": self.step,
            "detail": self.detail,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "cost_ms": round(self.cost_ms, 4),
        }


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """An explainable, deterministic query execution trace."""

    fingerprint: str
    generation: int
    nodes: tuple[PlanNode, ...] = ()
    cache_hit: bool = False

    @property
    def total_cost_ms(self) -> float:
        """Modeled cost of every plan node."""
        return sum(node.cost_ms for node in self.nodes)

    def explain(self) -> tuple[str, ...]:
        """Return human-readable plan lines."""
        lines = [
            f"query {self.fingerprint} generation={self.generation} "
            f"cache={'hit' if self.cache_hit else 'miss'}"
        ]
        for node in self.nodes:
            lines.append(
                f"  {node.step}: {node.detail} "
                f"rows={node.rows_in}->{node.rows_out} cost={node.cost_ms:.4f}ms"
            )
        lines.append(f"total modeled cost: {self.total_cost_ms:.4f}ms")
        return tuple(lines)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "fingerprint": self.fingerprint,
            "generation": self.generation,
            "cache_hit": self.cache_hit,
            "nodes": [node.as_dict() for node in self.nodes],
            "total_cost_ms": round(self.total_cost_ms, 4),
        }


@dataclass(frozen=True, slots=True)
class Measurement:
    """One reproducible benchmark measurement."""

    scenario: str
    modeled_ms: float
    operations: dict[str, int] = field(default_factory=dict)
    wall_ms: float = 0.0
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "scenario": self.scenario,
            "modeled_ms": round(self.modeled_ms, 4),
            "wall_ms": round(self.wall_ms, 4),
            "operations": dict(sorted(self.operations.items())),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Budget:
    """A measured limit for one user-visible interaction."""

    name: str
    limit_ms: float
    metric: str
    description: str

    def __post_init__(self) -> None:
        if self.limit_ms <= 0:
            raise ValueError("Budget limit must be positive")


@dataclass(frozen=True, slots=True)
class BudgetResult:
    """Outcome of comparing one measurement with its budget."""

    budget: Budget
    measured: float
    passed: bool

    @property
    def margin_ms(self) -> float:
        """Remaining headroom against the limit."""
        return round(self.budget.limit_ms - self.measured, 4)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.budget.name,
            "metric": self.budget.metric,
            "measured": round(self.measured, 4),
            "limit": self.budget.limit_ms,
            "margin": self.margin_ms,
            "passed": self.passed,
            "description": self.budget.description,
        }


@dataclass(frozen=True, slots=True)
class FlushReport:
    """Summary of one batched event flush."""

    received: int
    flushed: int
    batches: int
    checkpoint: int
    dropped: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "received": self.received,
            "flushed": self.flushed,
            "batches": self.batches,
            "checkpoint": self.checkpoint,
            "dropped": self.dropped,
        }


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    """Size and seed of an in-memory benchmark vault."""

    notes: int = 20_000
    findings: int = 10_000
    evidence: int = 5_000
    seed: int = 11
    tokens_per_note: int = 6
    event_sample_every: int = 8

    def __post_init__(self) -> None:
        for name in ("notes", "findings", "evidence"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.seed < 0:
            raise ValueError("seed cannot be negative")
        if self.tokens_per_note < 1 or self.tokens_per_note > 32:
            raise ValueError("tokens_per_note must be between 1 and 32")
        if self.event_sample_every < 1:
            raise ValueError("event_sample_every must be positive")

    @property
    def total_entities(self) -> int:
        """Total number of generated entities."""
        return self.notes + self.findings + self.evidence

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "notes": self.notes,
            "findings": self.findings,
            "evidence": self.evidence,
            "seed": self.seed,
            "tokens_per_note": self.tokens_per_note,
            "event_sample_every": self.event_sample_every,
            "total_entities": self.total_entities,
        }


@dataclass(frozen=True, slots=True)
class VaultFixture:
    """A generated vault that lives only in memory."""

    spec: FixtureSpec
    notes: tuple[EntityRecord, ...]
    findings: tuple[EntityRecord, ...]
    evidence: tuple[EntityRecord, ...]
    linked: tuple[tuple[EntityId, EntityId], ...]
    events: tuple[EventRecord, ...]
    fingerprint: str

    def all_records(self) -> tuple[EntityRecord, ...]:
        """Return every generated record in stable order."""
        return (*self.notes, *self.findings, *self.evidence)

    def as_dict(self) -> dict[str, Any]:
        """Return a compact, JSON-safe summary."""
        return {
            "spec": self.spec.as_dict(),
            "notes": len(self.notes),
            "findings": len(self.findings),
            "evidence": len(self.evidence),
            "links": len(self.linked),
            "events": len(self.events),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """The reproducible output of a full benchmark run."""

    fixture: VaultFixture
    measurements: dict[str, Measurement] = field(default_factory=dict)
    budgets: tuple[BudgetResult, ...] = ()
    plans: dict[str, QueryPlan] = field(default_factory=dict)
    wall_ms: float = 0.0

    @property
    def passed(self) -> bool:
        """Whether every budget passed."""
        return all(result.passed for result in self.budgets)

    @property
    def digest(self) -> str:
        """Stable digest of the deterministic portion of the report."""
        parts = [self.fixture.fingerprint]
        for name in sorted(self.measurements):
            measurement = self.measurements[name]
            operations = ",".join(
                f"{key}:{value}" for key, value in sorted(measurement.operations.items())
            )
            parts.append(f"{name}:{measurement.modeled_ms:.4f}:{operations}")
        raw = "|".join(parts)
        return hashlib.blake2b(raw.encode("utf-8"), digest_size=12).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without the large fixture."""
        return {
            "fixture": self.fixture.as_dict(),
            "digest": self.digest,
            "passed": self.passed,
            "wall_ms": round(self.wall_ms, 4),
            "measurements": {
                name: measurement.as_dict()
                for name, measurement in sorted(self.measurements.items())
            },
            "budgets": [result.as_dict() for result in self.budgets],
            "plans": {name: plan.as_dict() for name, plan in sorted(self.plans.items())},
        }
