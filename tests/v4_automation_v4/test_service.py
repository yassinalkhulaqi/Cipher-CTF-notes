"""Tests for the deterministic v4 automation domain services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from redscribe.v4.automation_v4.service import (
    DagValidationError,
    DagValidator,
    DryRunExecutor,
    RunManager,
    RunStateError,
    ScheduleError,
    ScheduleEvaluator,
)
from redscribe.v4.automation_v4.storage import RunStore
from redscribe.v4.automation_v4.types import (
    DagEdge,
    DagNode,
    Frequency,
    NodeKind,
    PlaybookDag,
    RunStatus,
    Schedule,
    TraceStatus,
)
from redscribe.v4.clock import Clock
from redscribe.v4.contracts import EntityKind
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox

FROZEN = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)


def node(node_id: str, kind: NodeKind = NodeKind.SETUP, *deps: str) -> DagNode:
    return DagNode(
        id=node_id,
        label=f"Node {node_id}",
        kind=kind,
        depends_on=deps,
        params={"target": node_id},
    )


def diamond() -> PlaybookDag:
    return PlaybookDag(
        id="pb-diamond",
        name="Diamond",
        nodes=(
            node("root"),
            node("left", NodeKind.COLLECT, "root"),
            node("right", NodeKind.ANALYZE, "root"),
            node("join", NodeKind.REPORT, "left", "right"),
        ),
        edges=(DagEdge("root", "left"), DagEdge("root", "right")),
    )


def chain() -> PlaybookDag:
    return PlaybookDag(
        id="pb-chain",
        name="Chain",
        nodes=(node("a"), node("b", NodeKind.COLLECT, "a"), node("c", NodeKind.REPORT, "b")),
    )


def raw_dag(nodes: tuple[DagNode, ...], edges: tuple[DagEdge, ...] = ()) -> PlaybookDag:
    """Build a deliberately unvalidated graph to exercise defensive checks."""
    dag = object.__new__(PlaybookDag)
    object.__setattr__(dag, "id", "pb-raw")
    object.__setattr__(dag, "name", "Raw")
    object.__setattr__(dag, "description", "")
    object.__setattr__(dag, "nodes", nodes)
    object.__setattr__(dag, "edges", edges)
    return dag


def test_validator_merges_declared_and_explicit_edges() -> None:
    validator = DagValidator()
    graph = validator.adjacency(diamond())
    assert graph["root"] == ()
    assert graph["left"] == ("root",)
    assert graph["right"] == ("root",)
    assert graph["join"] == ("left", "right")


def test_validator_topological_order_is_deterministic() -> None:
    validator = DagValidator()
    report = validator.validate(diamond())
    assert report.ok is True
    assert report.order == ("root", "left", "right", "join")
    assert report.edges.count(("root", "left")) == 1
    assert report.order == validator.validate(diamond()).order


def test_validator_tie_break_is_lexicographic() -> None:
    dag = PlaybookDag(
        id="pb-ties",
        name="Ties",
        nodes=(node("z"), node("a"), node("m")),
    )
    report = DagValidator().validate(dag)
    assert report.order == ("a", "m", "z")
    assert report.layers == (("a", "m", "z"),)


def test_validator_layers_and_depths() -> None:
    report = DagValidator().validate(diamond())
    assert report.layers == (("root",), ("left", "right"), ("join",))
    assert report.depth == {"root": 0, "left": 1, "right": 1, "join": 2}
    assert report.critical_path in {
        ("root", "left", "join"),
        ("root", "right", "join"),
    }


def test_validator_cycle_detection_is_canonical() -> None:
    dag = PlaybookDag(
        id="pb-cycle",
        name="Cycle",
        nodes=(
            node("a", NodeKind.SETUP, "c"),
            node("b", NodeKind.COLLECT, "a"),
            node("c", NodeKind.ANALYZE, "b"),
        ),
    )
    validator = DagValidator()
    report = validator.validate(dag)
    assert report.ok is False
    assert report.cycles == (("a", "b", "c"),)
    assert [issue.code for issue in report.errors] == ["cycle_detected"]
    assert report.order == ()
    assert "Cycle detected" in report.errors[0].message
    with pytest.raises(DagValidationError, match="invalid") as exc:
        validator.require_valid(dag)
    assert "cycle_detected" in exc.value.codes


def test_validator_finds_multiple_cycles_deterministically() -> None:
    dag = raw_dag(
        (
            node("a", NodeKind.SETUP, "b"),
            node("b", NodeKind.COLLECT, "a"),
            node("c", NodeKind.SETUP, "d"),
            node("d", NodeKind.COLLECT, "c"),
        )
    )
    cycles = DagValidator().find_cycles(DagValidator().adjacency(dag))
    assert cycles == (("a", "b"), ("c", "d"))


def test_validator_reports_missing_dangling_and_duplicate_ids() -> None:
    dag = raw_dag(
        (node("a"), node("b", NodeKind.COLLECT, "ghost")),
        (DagEdge("ghost", "b"), DagEdge("a", "b")),
    )
    report = DagValidator().validate(dag)
    codes = {issue.code for issue in report.errors}
    assert {"missing_dependency", "dangling_edge"} <= codes
    assert report.missing == ("ghost",)

    duplicated = raw_dag((node("a"), node("a")))
    dup_report = DagValidator().validate(duplicated)
    assert dup_report.duplicates == ("a",)
    assert "duplicate_node" in {issue.code for issue in dup_report.errors}


def test_validator_warns_for_isolated_nodes() -> None:
    isolated = PlaybookDag(id="pb-iso", name="Iso", nodes=(node("solo"),))
    report = DagValidator().validate(isolated)
    assert report.ok is True
    assert report.warnings[0].code == "isolated_node"
    assert DagValidator(warn_isolated=False).validate(isolated).warnings == ()


def test_validation_report_serialization() -> None:
    report = DagValidator().validate(chain())
    data = report.to_dict()
    assert data["ok"] is True
    assert data["order"] == ["a", "b", "c"]
    assert data["critical_path"] == ["a", "b", "c"]
    assert isinstance(data["depth"], dict)
    assert report.summary().startswith("pb-chain: valid")


def test_executor_plan_and_duration_are_stable() -> None:
    executor = DryRunExecutor()
    assert executor.plan(diamond()) == ("root", "left", "right", "join")
    first = executor.duration_for(node("a"))
    assert first == executor.duration_for(node("a"))
    assert first >= NodeKind.SETUP.base_duration_ms
    slow = DagNode("a", "A", NodeKind.SETUP, params={"delay_ms": "25"})
    assert executor.duration_for(slow) >= NodeKind.SETUP.base_duration_ms + 25
    assert node("a").params == {"target": "a"}


def test_executor_dry_run_trace_follows_topological_order() -> None:
    result = DryRunExecutor().execute(diamond())
    assert result.status is RunStatus.SUCCEEDED
    assert result.succeeded is True
    assert tuple(step.node_id for step in result.trace) == ("root", "left", "right", "join")
    assert all(step.status is TraceStatus.SUCCEEDED for step in result.trace)
    assert all("simulated" in step.detail for step in result.trace)
    assert result.waves == 3
    assert result.failed_nodes == ()
    assert result.skipped_nodes == ()
    assert result.to_dict()["dag_id"] == "pb-diamond"


def test_executor_propagates_failure_to_downstream_nodes() -> None:
    result = DryRunExecutor().execute(chain(), frozenset({"b"}))
    assert result.status is RunStatus.FAILED
    assert result.succeeded is False
    assert result.failed_nodes == ("b",)
    assert result.skipped_nodes == ("c",)
    assert result.trace[0].status is TraceStatus.SUCCEEDED
    assert result.trace[2].duration_ms == 0
    assert "did not succeed" in result.trace[2].detail


def test_executor_honours_inert_failure_parameter() -> None:
    dag = PlaybookDag(
        id="pb-fail",
        name="Fail",
        nodes=(
            node("a"),
            DagNode("b", "B", NodeKind.ANALYZE, params={"simulate_failure": "true"}),
            node("c", NodeKind.REPORT, "b"),
        ),
    )
    result = DryRunExecutor().execute(dag)
    assert result.failed_nodes == ("b",)
    assert result.skipped_nodes == ("c",)


def test_executor_digest_is_order_sensitive_and_repeatable() -> None:
    executor = DryRunExecutor()
    first = executor.execute(chain())
    second = executor.execute(chain())
    assert first.digest == second.digest
    assert first.digest == executor.digest_of(first.trace)
    assert len(first.digest) == 24
    failed = executor.execute(chain(), frozenset({"a"}))
    assert failed.digest != first.digest
    assert failed.failed_nodes == ("a",)
    assert failed.skipped_nodes == ("b", "c")
    assert executor.execute(chain(), frozenset({"nonexistent"})).digest == first.digest


def test_executor_rejects_invalid_dag() -> None:
    cyclic = PlaybookDag(
        id="pb-cycle",
        name="Cycle",
        nodes=(
            node("a", NodeKind.SETUP, "b"),
            node("b", NodeKind.COLLECT, "a"),
        ),
    )
    with pytest.raises(DagValidationError, match="invalid"):
        DryRunExecutor().execute(cyclic)


def evaluator() -> tuple[ScheduleEvaluator, Clock]:
    clock = Clock(FROZEN)
    return ScheduleEvaluator(clock), clock


def test_schedule_interval_recurrence() -> None:
    evaluator_instance, _ = evaluator()
    schedule = Schedule("s", "pb", Frequency.INTERVAL, interval_minutes=90)
    assert evaluator_instance.next_after(schedule) == FROZEN + timedelta(minutes=90)
    assert evaluator_instance.upcoming(schedule, 2) == (
        "2026-01-05T11:00:00.000Z",
        "2026-01-05T12:30:00.000Z",
    )


def test_schedule_daily_recurrence_strictly_after_now() -> None:
    evaluator_instance, _ = evaluator()
    schedule = Schedule("s", "pb", Frequency.DAILY, hour=9, minute=30)
    assert evaluator_instance.next_after(schedule) == datetime(
        2026, 1, 6, 9, 30, tzinfo=timezone.utc
    )
    earlier = Schedule("s", "pb", Frequency.DAILY, hour=8, minute=0)
    assert evaluator_instance.next_after(earlier) == datetime(2026, 1, 6, 8, 0, tzinfo=timezone.utc)


def test_schedule_weekly_recurrence() -> None:
    evaluator_instance, _ = evaluator()
    monday = Schedule("s", "pb", Frequency.WEEKLY, hour=6, minute=15, day_of_week=(2,))
    # Monday 2026-01-05 -> Wednesday 2026-01-07.
    assert evaluator_instance.next_after(monday) == datetime(2026, 1, 7, 6, 15, tzinfo=timezone.utc)
    today = Schedule("s", "pb", Frequency.WEEKLY, hour=10, minute=0, day_of_week=(0,))
    assert evaluator_instance.next_after(today) == datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)


def test_schedule_monthly_recurrence_clamps_short_months() -> None:
    evaluator_instance, clock = evaluator()
    schedule = Schedule("s", "pb", Frequency.MONTHLY, hour=12, day_of_month=31)
    assert evaluator_instance.next_after(schedule) == datetime(
        2026, 1, 31, 12, 0, tzinfo=timezone.utc
    )
    clock.freeze(datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc))
    assert evaluator_instance.next_after(schedule) == datetime(
        2026, 2, 28, 12, 0, tzinfo=timezone.utc
    )


def test_schedule_due_refresh_and_descriptions() -> None:
    evaluator_instance, clock = evaluator()
    schedule = Schedule(
        "s",
        "pb",
        Frequency.DAILY,
        hour=7,
        minute=0,
        next_run="2026-01-05T09:00:00.000Z",
    )
    assert evaluator_instance.due(schedule) is True
    assert evaluator_instance.due(schedule, FROZEN - timedelta(hours=1)) is False
    assert evaluator_instance.due(schedule.with_next_run("")) is False
    refreshed = evaluator_instance.refresh(schedule)
    assert refreshed.next_run == "2026-01-06T07:00:00.000Z"
    assert evaluator_instance.due(refreshed) is False
    paused = Schedule(
        "s",
        "pb",
        Frequency.DAILY,
        hour=7,
        minute=0,
        next_run="2026-01-05T08:00:00.000Z",
        enabled=False,
    )
    assert evaluator_instance.due(paused) is False
    assert evaluator_instance.refresh(paused) == paused
    assert "daily at 07:00" in evaluator_instance.describe(schedule)
    assert "every 90 minute" in evaluator_instance.describe(
        Schedule("i", "pb", Frequency.INTERVAL, interval_minutes=90)
    )
    assert "weekly on [0,2]" in evaluator_instance.describe(
        Schedule("w", "pb", Frequency.WEEKLY, day_of_week=(0, 2))
    )
    assert "monthly on day 15" in evaluator_instance.describe(
        Schedule("m", "pb", Frequency.MONTHLY, day_of_month=15)
    )
    assert clock.is_frozen is True


def test_schedule_evaluator_errors() -> None:
    evaluator_instance, _ = evaluator()
    with pytest.raises(ScheduleError, match="count must be >= 1"):
        evaluator_instance.upcoming(Schedule("s", "pb", Frequency.INTERVAL), 0)
    with pytest.raises(ScheduleError, match="invalid timestamp"):
        evaluator_instance.parse("not-a-date")
    with pytest.raises(ScheduleError, match="invalid timestamp"):
        evaluator_instance.parse("")


def manager() -> tuple[RunManager, RunStore, EventBus, DryRunExecutor]:
    store = RunStore()
    bus = EventBus(InMemoryOutbox())
    executor = DryRunExecutor()
    evaluator = ScheduleEvaluator(Clock(FROZEN))
    ids = count(1)
    service = RunManager(
        store,
        bus,
        executor,
        evaluator,
        Clock(FROZEN),
        lambda: f"run-{next(ids)}",
    )
    return service, store, bus, executor


def test_run_manager_start_emits_event() -> None:
    service, store, bus, _ = manager()
    run = service.start("pb-1")
    assert run.id == "run-1"
    assert run.status is RunStatus.RUNNING
    assert run.started_at == "2026-01-05T09:30:00.000Z"
    assert store.get(run.id) == run
    events = bus.published
    assert len(events) == 1
    assert events[0].kind is EventKind.RUN_STARTED
    assert events[0].aggregate_kind is EntityKind.RUN
    assert events[0].payload["playbook_id"] == "pb-1"
    assert bus.outbox is not None
    assert len(bus.outbox.records(EventKind.RUN_STARTED)) == 1


def test_run_manager_finish_publishes_trace_digest() -> None:
    service, store, bus, executor = manager()
    run = service.start("pb-1", "api")
    result = executor.execute(chain(), frozenset({"b"}))
    finished = service.finish(run.id, result)
    assert finished.status is RunStatus.FAILED
    assert finished.finished_at == "2026-01-05T09:30:00.000Z"
    assert len(finished.trace) == 3
    assert store.require(run.id) == finished
    event = bus.published[-1]
    assert event.kind is EventKind.RUN_FINISHED
    assert event.payload["trace_digest"] == result.digest
    assert event.payload["steps"] == 3


def test_run_manager_cancel_and_state_errors() -> None:
    service, store, bus, executor = manager()
    run = service.start("pb-1")
    cancelled = service.cancel(run.id)
    assert cancelled.status is RunStatus.CANCELLED
    assert store.require(run.id).status is RunStatus.CANCELLED
    assert bus.published[-1].payload["status"] == "cancelled"
    with pytest.raises(RunStateError, match="cannot cancel terminal run"):
        service.cancel(run.id)
    with pytest.raises(RunStateError, match="cannot finish"):
        service.finish(run.id, executor.execute(chain()))
    with pytest.raises(RunStateError, match="unknown run"):
        service.require("missing")
    with pytest.raises(RunStateError, match="playbook_id must not be empty"):
        service.start("")


def test_run_manager_lists_and_schedules() -> None:
    service, store, _, executor = manager()
    first = service.start("pb-1")
    second = service.start("pb-2")
    service.finish(first.id, executor.execute(chain()))
    assert service.get("missing") is None
    assert service.list_runs("pb-1")[0].id == first.id
    assert service.list_runs(status=RunStatus.SUCCEEDED) == (store.require(first.id),)
    assert service.list_runs() == (store.require(first.id), store.require(second.id))
    assert service.active() == (store.require(second.id),)
    schedule = Schedule("s", "pb-1", Frequency.DAILY, next_run="2026-01-05T08:00:00.000Z")
    planned = service.plan(schedule)
    assert planned.next_run == "2026-01-06T00:00:00.000Z"
    assert store.get_schedule("s") == planned
    assert service.due_schedules() == ()
    expired = planned.with_next_run("2026-01-05T08:00:00.000Z")
    store.put_schedule(expired)
    assert service.due_schedules() == (expired,)
