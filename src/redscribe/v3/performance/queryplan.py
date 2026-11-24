"""Query-plan instrumentation for indexed reads.

A plan is recorded as a tuple of :class:`PlanNode` values with modeled costs,
so the same query on the same index always produces the same explanation. No
wall-clock timestamps are stored in the plan itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from redscribe.v3.performance.meter import Meter
from redscribe.v3.performance.models import PlanNode, QueryPlan


class PlanRecorder:
    """Collects plan nodes while charging operations to a meter."""

    def __init__(self, meter: Meter, fingerprint: str, generation: int) -> None:
        self._meter = meter
        self._fingerprint = fingerprint
        self._generation = generation
        self._nodes: list[PlanNode] = []

    def step(
        self,
        name: str,
        detail: str,
        *,
        rows_in: int,
        rows_out: int,
        operation: str | None = None,
        count: int = 0,
    ) -> None:
        """Append one instrumented step."""
        before = self._meter.modeled_ms
        if operation is not None:
            self._meter.record(operation, count)
        after = self._meter.modeled_ms
        self._nodes.append(
            PlanNode(
                step=name,
                detail=detail,
                rows_in=rows_in,
                rows_out=rows_out,
                cost_ms=round(after - before, 4),
            )
        )

    def finish(self, *, cache_hit: bool = False) -> QueryPlan:
        """Build the immutable plan."""
        return QueryPlan(
            fingerprint=self._fingerprint,
            generation=self._generation,
            nodes=tuple(self._nodes),
            cache_hit=cache_hit,
        )


def plan_step_names(plan: QueryPlan) -> tuple[str, ...]:
    """Return the ordered step names of a plan."""
    return tuple(node.step for node in plan.nodes)


def plan_rows_scanned(plan: QueryPlan) -> int:
    """Return the largest row count seen by any plan step."""
    return max((node.rows_in for node in plan.nodes), default=0)


def plan_cost(plan: QueryPlan) -> float:
    """Return the modeled cost of a plan."""
    return round(plan.total_cost_ms, 4)


def explain_plans(plans: Mapping[str, QueryPlan]) -> tuple[str, ...]:
    """Explain several plans with a blank line between them."""
    lines: list[str] = []
    for name in sorted(plans):
        if lines:
            lines.append("")
        lines.append(f"[{name}]")
        lines.extend(plans[name].explain())
    return tuple(lines)


def compare_plans(first: QueryPlan, second: QueryPlan) -> dict[str, object]:
    """Compare two plans for cache and cost regressions."""
    return {
        "first_cost_ms": plan_cost(first),
        "second_cost_ms": plan_cost(second),
        "second_cache_hit": second.cache_hit,
        "steps_match": plan_step_names(first) == plan_step_names(second),
        "cheaper": plan_cost(second) <= plan_cost(first),
    }


def summarize_operations(plans: Sequence[QueryPlan]) -> dict[str, int]:
    """Count how often each plan step appears across a sequence of plans."""
    counts: dict[str, int] = {}
    for plan in plans:
        for node in plan.nodes:
            counts[node.step] = counts.get(node.step, 0) + 1
    return dict(sorted(counts.items()))
