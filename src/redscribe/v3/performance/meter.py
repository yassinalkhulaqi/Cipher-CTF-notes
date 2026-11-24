"""Deterministic cost model used by the performance harness.

Wall-clock time varies between machines, so CI budgets are asserted against a
modeled cost derived from operation counts. The model is calibrated in
microseconds per operation and is intentionally conservative: every operation
represents work the application really performs (tokenizing, posting lookups,
row materialization, event writes, and graph projection).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Final

OPERATION_COST_US: Final[dict[str, float]] = {
    "tokenize": 1.4,
    "posting_lookup": 0.9,
    "posting_union": 0.6,
    "candidate_score": 0.8,
    "row_materialize": 2.0,
    "full_scan_document": 9.0,
    "index_mutation": 1.1,
    "layout_node": 8.0,
    "event_append": 0.5,
    "event_flush": 0.7,
    "graph_node_project": 1.1,
    "fingerprint_step": 0.35,
}

_US_PER_MS: Final[float] = 1000.0


@dataclass(slots=True)
class Meter:
    """Accumulates operation counts and converts them to modeled milliseconds."""

    counts: Counter[str] = field(default_factory=Counter)
    costs: dict[str, float] = field(default_factory=lambda: dict(OPERATION_COST_US))

    def record(self, operation: str, count: int = 1) -> None:
        """Record a number of operations, ignoring non-positive counts."""
        if count <= 0:
            return
        if operation not in self.costs:
            raise KeyError(f"Unknown operation: {operation}")
        self.counts[operation] += count

    def record_many(self, values: dict[str, int]) -> None:
        """Record several operation families at once."""
        for operation, count in values.items():
            self.record(operation, count)

    def count(self, operation: str) -> int:
        """Return the recorded count for one operation."""
        return self.counts.get(operation, 0)

    def as_dict(self) -> dict[str, int]:
        """Return a stable operation snapshot."""
        return dict(sorted(self.counts.items()))

    @property
    def total_operations(self) -> int:
        """Return the number of recorded operations."""
        return sum(self.counts.values())

    @property
    def modeled_ms(self) -> float:
        """Return the modeled duration in milliseconds, rounded for stability."""
        total_us = sum(self.counts[operation] * self.costs[operation] for operation in self.counts)
        return round(total_us / _US_PER_MS, 4)

    def reset(self) -> None:
        """Drop all recorded operations."""
        self.counts.clear()
