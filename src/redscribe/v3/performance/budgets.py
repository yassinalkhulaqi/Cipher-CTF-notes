"""Performance budgets and reproducible budget assertions.

Budgets are expressed against the deterministic modeled cost of each scenario.
A wall-clock number is recorded in the report for humans, but CI never fails on
it: an I/O-slow runner would otherwise produce flaky results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from redscribe.v3.performance.models import Budget, BudgetResult, Measurement

STARTUP_MAX_ROWS = 50


@dataclass(frozen=True, slots=True)
class _BudgetRule:
    """Links a budget to the scenario and metric that satisfy it."""

    budget: Budget
    scenario: str
    operation: str = ""


_RULES: tuple[_BudgetRule, ...] = (
    _BudgetRule(
        Budget(
            "tree_interaction",
            100.0,
            "modeled_ms",
            "Expanding or scrolling a node in a 20k-note tree",
        ),
        "tree_interaction",
    ),
    _BudgetRule(
        Budget(
            "first_search",
            150.0,
            "modeled_ms",
            "First result window from a cold query on the incremental index",
        ),
        "first_search",
    ),
    _BudgetRule(
        Budget(
            "startup_load",
            250.0,
            "modeled_ms",
            "Building the initial bounded index window at startup",
        ),
        "startup",
    ),
    _BudgetRule(
        Budget(
            "startup_rows",
            float(STARTUP_MAX_ROWS),
            "rows",
            "Rows materialized on startup must not include the whole vault",
        ),
        "startup",
        "row_materialize",
    ),
    _BudgetRule(
        Budget(
            "incremental_edit",
            50.0,
            "modeled_ms",
            "Applying a 25-document mutation batch without a rebuild",
        ),
        "incremental_edit",
    ),
    _BudgetRule(
        Budget(
            "event_flush",
            200.0,
            "modeled_ms",
            "Flushing a full batch of generated domain events",
        ),
        "event_flush",
    ),
    _BudgetRule(
        Budget(
            "graph_deferred_frame",
            16.0,
            "modeled_ms",
            "One deferred graph projection chunk fits in a 60 fps frame",
        ),
        "graph_deferred",
    ),
)

BUDGETS: tuple[Budget, ...] = tuple(rule.budget for rule in _RULES)


class BudgetError(AssertionError):
    """Raised when one or more performance budgets fail."""


def _measured_value(rule: _BudgetRule, measurement: Measurement) -> float:
    """Extract the metric governed by a rule."""
    if not rule.operation:
        return measurement.modeled_ms
    return float(measurement.operations.get(rule.operation, 0))


def evaluate_budgets(measurements: Mapping[str, Measurement]) -> tuple[BudgetResult, ...]:
    """Compare every budget with its matching measurement."""
    results: list[BudgetResult] = []
    for rule in _RULES:
        measurement = measurements.get(rule.scenario)
        if measurement is None:
            raise ValueError(f"Missing benchmark measurement: {rule.scenario}")
        value = _measured_value(rule, measurement)
        results.append(
            BudgetResult(budget=rule.budget, measured=value, passed=value <= rule.budget.limit_ms)
        )
    return tuple(results)


def assert_budgets(results: Sequence[BudgetResult]) -> None:
    """Raise :class:`BudgetError` when any budget failed."""
    failures = [result for result in results if not result.passed]
    if not failures:
        return
    lines = [f"Performance budget failure: {len(failures)} of {len(results)} budgets failed"]
    for result in failures:
        lines.append(
            f"  {result.budget.name}: {result.measured} {result.budget.metric} "
            f"> {result.budget.limit_ms:g}"
        )
    raise BudgetError("\n".join(lines))


def format_budgets(results: Sequence[BudgetResult]) -> tuple[str, ...]:
    """Render budget results as stable text lines."""
    lines = [f"{'budget':<24} {'measured':>12} {'limit':>12}  status"]
    for result in results:
        lines.append(
            f"{result.budget.name:<24} "
            f"{result.measured:>12.4f} {result.budget.limit_ms:>12.4f}  "
            f"{'PASS' if result.passed else 'FAIL'}"
        )
    return tuple(lines)


def budget_by_name(name: str) -> Budget:
    """Look up a budget by its stable name."""
    for budget in BUDGETS:
        if budget.name == name:
            return budget
    raise ValueError(f"Unknown budget: {name}")
