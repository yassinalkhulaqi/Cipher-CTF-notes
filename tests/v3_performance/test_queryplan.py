"""Query-plan instrumentation and explanation helpers."""

from __future__ import annotations

import pytest

from redscribe.v3.performance.meter import Meter
from redscribe.v3.performance.models import PlanNode, QueryPlan
from redscribe.v3.performance.queryplan import (
    PlanRecorder,
    compare_plans,
    explain_plans,
    plan_cost,
    plan_rows_scanned,
    plan_step_names,
    summarize_operations,
)


def test_recorder_charges_operations_to_meter() -> None:
    meter = Meter()
    recorder = PlanRecorder(meter, "alpha|5|False", generation=2)
    recorder.step(
        "posting_lookup",
        "tokens=1",
        rows_in=1,
        rows_out=1,
        operation="posting_lookup",
        count=3,
    )
    plan = recorder.finish()
    assert meter.count("posting_lookup") == 3
    assert plan.generation == 2
    assert plan.nodes[0].rows_out == 1
    assert plan.nodes[0].cost_ms > 0
    assert plan.total_cost_ms == plan_cost(plan)


def test_recorder_step_without_operation_has_zero_cost() -> None:
    meter = Meter()
    recorder = PlanRecorder(meter, "x", 0)
    recorder.step("cache_lookup", "fingerprint=x", rows_in=1, rows_out=1)
    plan = recorder.finish(cache_hit=True)
    assert plan.nodes[0].cost_ms == 0
    assert plan.cache_hit is True


def test_unknown_operation_raises() -> None:
    recorder = PlanRecorder(Meter(), "x", 0)
    with pytest.raises(KeyError, match="Unknown operation"):
        recorder.step("bad", "bad", rows_in=0, rows_out=0, operation="not_real", count=1)


def test_plan_helpers() -> None:
    plan = QueryPlan(
        fingerprint="x",
        generation=1,
        nodes=(
            PlanNode("a", "detail", rows_in=10, rows_out=5, cost_ms=0.1),
            PlanNode("b", "detail", rows_in=5, rows_out=2, cost_ms=0.2),
        ),
    )
    assert plan_step_names(plan) == ("a", "b")
    assert plan_rows_scanned(plan) == 10
    assert plan_cost(plan) == 0.3


def test_empty_plan_helpers() -> None:
    plan = QueryPlan(fingerprint="empty", generation=0)
    assert plan_rows_scanned(plan) == 0
    assert plan_cost(plan) == 0
    assert plan_step_names(plan) == ()


def test_compare_plans_detects_cache_win() -> None:
    first = QueryPlan(
        "x",
        1,
        (PlanNode("scan", "all", rows_in=100, cost_ms=1.0),),
    )
    second = QueryPlan(
        "x",
        1,
        (PlanNode("cache_hit", "hit", rows_in=1, cost_ms=0.01),),
        cache_hit=True,
    )
    comparison = compare_plans(first, second)
    assert comparison["second_cache_hit"] is True
    assert comparison["cheaper"] is True
    assert comparison["steps_match"] is False


def test_explain_plans_and_summary() -> None:
    first = QueryPlan("a", 1, (PlanNode("scan", "all", rows_in=9),))
    second = QueryPlan("b", 2, (PlanNode("scan", "all", rows_in=3),))
    lines = explain_plans({"second": second, "first": first})
    assert lines[0] == "[first]"
    assert "[second]" in lines
    assert summarize_operations((first, second)) == {"scan": 2}
