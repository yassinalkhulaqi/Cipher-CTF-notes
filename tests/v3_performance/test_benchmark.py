"""Benchmark harness, reproducibility, and budget enforcement."""

from __future__ import annotations

import pytest

from redscribe.v3.performance.batching import FlushPolicy
from redscribe.v3.performance.benchmark import (
    SCENARIO_NAMES,
    render_report,
    report_lines_as_text,
    report_operations,
    report_summary,
    run_benchmark,
)
from redscribe.v3.performance.budgets import (
    BUDGETS,
    STARTUP_MAX_ROWS,
    BudgetError,
    assert_budgets,
    budget_by_name,
    evaluate_budgets,
    format_budgets,
)
from redscribe.v3.performance.fixtures import fixture_documents, generate_fixture
from redscribe.v3.performance.meter import OPERATION_COST_US
from redscribe.v3.performance.models import FixtureSpec, Measurement

SMALL = FixtureSpec(notes=60, findings=30, evidence=15, seed=5)


def test_fixture_is_deterministic_and_in_memory() -> None:
    first = generate_fixture(SMALL)
    second = generate_fixture(SMALL)
    assert first.fingerprint == second.fingerprint
    assert len(first.notes) == 60
    assert len(first.findings) == 30
    assert len(first.evidence) == 15
    assert len(first.linked) == 45
    assert first.events[0].sequence == 1
    assert first.notes[0].title == second.notes[0].title
    assert first.as_dict()["spec"]["seed"] == 5


def test_fixture_seed_changes_fingerprint() -> None:
    first = generate_fixture(SMALL)
    second = generate_fixture(FixtureSpec(notes=60, findings=30, evidence=15, seed=6))
    assert first.fingerprint != second.fingerprint


def test_fixture_tokens_match_generated_notes() -> None:
    fixture = generate_fixture(SMALL)
    tokens = fixture_documents(fixture)
    assert len(tokens) == len(fixture.notes)
    assert tokens[0][0] == str(fixture.notes[0].entity_id)
    assert tokens[0][1][0] in fixture.notes[0].title


def test_run_benchmark_runs_every_scenario() -> None:
    report = run_benchmark(SMALL)
    assert set(report.measurements) == set(SCENARIO_NAMES)
    assert report.passed is True
    assert len(report.budgets) == len(BUDGETS)
    assert all(result.passed for result in report.budgets)
    assert report.measurements["startup"].operations.get("row_materialize", 0) <= STARTUP_MAX_ROWS
    assert "first_search" in report.plans


def test_benchmark_is_reproducible() -> None:
    first = run_benchmark(SMALL, enforce=False)
    second = run_benchmark(SMALL, enforce=False)
    assert first.digest == second.digest
    assert first.fixture.fingerprint == second.fixture.fingerprint
    for name in SCENARIO_NAMES:
        assert first.measurements[name].modeled_ms == second.measurements[name].modeled_ms
        assert first.measurements[name].operations == second.measurements[name].operations
    assert first.plans["first_search"].as_dict() == second.plans["first_search"].as_dict()


def test_report_rendering_and_summary() -> None:
    report = run_benchmark(SMALL, enforce=False)
    lines = render_report(report)
    text = report_lines_as_text(lines)
    assert "RedScribe V3 performance benchmark" in text
    assert "status: PASS" in text
    assert "first_search" in text
    summary = report_summary(report)
    assert summary["digest"] == report.digest
    assert summary["passed"] is True
    assert set(summary["measurements"]) == set(SCENARIO_NAMES)
    assert "posting_lookup" in summary["operations"]
    assert report_operations(report) == summary["operations"]
    assert as_dict_budgets_pass(summary["budgets"])


def as_dict_budgets_pass(budgets: list[dict[str, object]]) -> bool:
    return all(item["passed"] is True for item in budgets)


def test_budget_evaluation_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    measurements = {
        "tree_interaction": Measurement("tree_interaction", 5.0),
        "first_search": Measurement("first_search", 20.0),
        "startup": Measurement("startup", 30.0, operations={"row_materialize": 50}),
        "incremental_edit": Measurement("incremental_edit", 2.0),
        "event_flush": Measurement("event_flush", 3.0),
        "graph_deferred": Measurement("graph_deferred", 1.0),
    }
    results = evaluate_budgets(measurements)
    assert all(result.passed for result in results)
    assert_budgets(results)
    lines = format_budgets(results)
    assert lines[0].startswith("budget")
    assert any("PASS" in line for line in lines)

    broken = dict(measurements)
    broken["first_search"] = Measurement("first_search", 500.0)
    failed = evaluate_budgets(broken)
    assert any(not result.passed for result in failed)
    with pytest.raises(BudgetError, match="first_search"):
        assert_budgets(failed)
    monkeypatch.setitem(OPERATION_COST_US, "graph_node_project", 1000.0)
    with pytest.raises(BudgetError, match="graph_deferred_frame"):
        run_benchmark(SMALL)


def test_missing_measurement_is_reported() -> None:
    with pytest.raises(ValueError, match="Missing benchmark measurement"):
        evaluate_budgets({})


def test_budget_lookup() -> None:
    assert budget_by_name("first_search").limit_ms == 150.0
    with pytest.raises(ValueError, match="Unknown budget"):
        budget_by_name("missing")


def test_default_fixture_meets_exit_criteria() -> None:
    report = run_benchmark()
    assert report.fixture.spec.notes == 20_000
    assert report.fixture.spec.findings == 10_000
    assert report.fixture.spec.evidence == 5_000
    assert report.passed is True
    assert report.measurements["tree_interaction"].modeled_ms < 100
    assert report.measurements["first_search"].modeled_ms < 150
    assert report.measurements["startup"].operations.get("row_materialize", 0) <= STARTUP_MAX_ROWS


def test_flush_policy_defaults_independent_of_benchmark() -> None:
    assert FlushPolicy().max_size == 128
