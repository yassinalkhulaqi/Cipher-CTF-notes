"""Performance and scale tooling for RedScribe V3.

The package provides an incremental index, batched event flushing, query-plan
instrumentation, pure worker-friendly helpers, deterministic in-memory fixtures,
and a benchmark harness with hard budget assertions.
"""

from redscribe.v3.performance.batching import (
    BatchSink,
    EventBatcher,
    FlushPolicy,
)
from redscribe.v3.performance.benchmark import (
    SCENARIO_NAMES,
    render_report,
    report_lines_as_text,
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
from redscribe.v3.performance.incremental import IncrementalIndex
from redscribe.v3.performance.meter import OPERATION_COST_US, Meter
from redscribe.v3.performance.models import (
    BenchmarkReport,
    Budget,
    BudgetResult,
    FixtureSpec,
    FlushReport,
    IndexDelta,
    IndexDocument,
    Measurement,
    PlanNode,
    QueryPlan,
    QueryResult,
    QuerySpec,
    VaultFixture,
)
from redscribe.v3.performance.queryplan import (
    PlanRecorder,
    compare_plans,
    explain_plans,
    plan_cost,
    plan_step_names,
)
from redscribe.v3.performance.workers import (
    apply_delta_postings,
    build_postings,
    chunk,
    estimate_event_bytes,
    event_fingerprint,
    merge_postings,
    paginate_refs,
    rank_refs,
    score_candidates,
    tokenize,
    visible_range,
)

__all__ = [
    "BUDGETS",
    "OPERATION_COST_US",
    "SCENARIO_NAMES",
    "STARTUP_MAX_ROWS",
    "BatchSink",
    "BenchmarkReport",
    "Budget",
    "BudgetError",
    "BudgetResult",
    "EventBatcher",
    "FixtureSpec",
    "FlushPolicy",
    "FlushReport",
    "IncrementalIndex",
    "IndexDelta",
    "IndexDocument",
    "Measurement",
    "Meter",
    "PlanNode",
    "PlanRecorder",
    "QueryPlan",
    "QueryResult",
    "QuerySpec",
    "VaultFixture",
    "apply_delta_postings",
    "assert_budgets",
    "budget_by_name",
    "build_postings",
    "chunk",
    "compare_plans",
    "estimate_event_bytes",
    "evaluate_budgets",
    "event_fingerprint",
    "explain_plans",
    "fixture_documents",
    "format_budgets",
    "generate_fixture",
    "merge_postings",
    "paginate_refs",
    "plan_cost",
    "plan_step_names",
    "rank_refs",
    "render_report",
    "report_lines_as_text",
    "report_summary",
    "run_benchmark",
    "score_candidates",
    "tokenize",
    "visible_range",
]
