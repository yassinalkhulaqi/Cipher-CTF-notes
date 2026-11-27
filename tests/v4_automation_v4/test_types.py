"""Tests for v4 automation data contracts."""

from __future__ import annotations

import pytest

from redscribe.v4.automation_v4.types import (
    DagEdge,
    DagNode,
    Frequency,
    IssueSeverity,
    NodeKind,
    PlaybookDag,
    RunRecord,
    RunStatus,
    Schedule,
    TraceStatus,
    TraceStep,
    ValidationIssue,
    integer,
    integer_tuple,
    string_map,
    text,
    text_tuple,
)


def node(node_id: str, kind: NodeKind = NodeKind.COLLECT, *deps: str) -> DagNode:
    return DagNode(
        id=node_id,
        label=f"Node {node_id}",
        kind=kind,
        depends_on=deps,
        params={"target": node_id},
    )


def test_node_kind_parse_and_metadata() -> None:
    assert NodeKind.parse(" collect ") is NodeKind.COLLECT
    assert NodeKind.ANALYZE.label == "Analyze"
    assert NodeKind.SETUP.base_duration_ms < NodeKind.ANALYZE.base_duration_ms
    with pytest.raises(ValueError, match="Unknown node kind"):
        NodeKind.parse("execute")


def test_run_status_parse_and_terminal_states() -> None:
    assert RunStatus.parse("SUCCEEDED") is RunStatus.SUCCEEDED
    assert RunStatus.SUCCEEDED.label == "Succeeded"
    assert RunStatus.PENDING.is_terminal is False
    assert RunStatus.RUNNING.is_terminal is False
    assert RunStatus.FAILED.is_terminal is True
    assert RunStatus.CANCELLED.is_terminal is True
    with pytest.raises(ValueError, match="Unknown run status"):
        RunStatus.parse("done")


def test_trace_and_severity_and_frequency_parse() -> None:
    assert TraceStatus.parse("failed") is TraceStatus.FAILED
    assert IssueSeverity.parse("WARNING") is IssueSeverity.WARNING
    assert Frequency.parse(" Daily ") is Frequency.DAILY
    with pytest.raises(ValueError, match="Unknown trace status"):
        TraceStatus.parse("unknown")
    with pytest.raises(ValueError, match="Unknown issue severity"):
        IssueSeverity.parse("fatal")
    with pytest.raises(ValueError, match="Unknown frequency"):
        Frequency.parse("yearly")


def test_decode_helpers_are_strict() -> None:
    assert text(7, "fallback") == "fallback"
    assert text("value") == "value"
    assert integer(True, 4) == 4
    assert integer("9", 4) == 4
    assert integer(9, 4) == 9
    assert text_tuple(["a", 3, "b"]) == ("a", "b")
    assert text_tuple("a") == ()
    assert integer_tuple([1, True, 2, "3"]) == (1, 2)
    assert string_map({"a": 1, "b": "two"}) == {"a": "", "b": "two"}
    assert string_map(None) == {}


def test_validation_issue_round_trip() -> None:
    issue = ValidationIssue("cycle_detected", "Cycle", "nodes", IssueSeverity.WARNING)
    assert issue.to_dict() == {
        "code": "cycle_detected",
        "message": "Cycle",
        "path": "nodes",
        "severity": "warning",
    }
    assert ValidationIssue.from_dict(issue.to_dict()) == issue
    with pytest.raises(ValueError, match="Invalid issue code"):
        ValidationIssue("bad-code", "message")
    with pytest.raises(ValueError, match="message must not be empty"):
        ValidationIssue("code", "")


def test_dag_node_validation() -> None:
    assert node("a").depends_on == ()
    with pytest.raises(ValueError, match="node id must not be empty"):
        DagNode(id=" ", label="x", kind=NodeKind.SETUP)
    with pytest.raises(ValueError, match="node label must not be empty"):
        DagNode(id="a", label="", kind=NodeKind.SETUP)
    with pytest.raises(ValueError, match="cannot depend on itself"):
        DagNode(id="a", label="A", kind=NodeKind.SETUP, depends_on=("a",))
    with pytest.raises(ValueError, match="duplicate dependency"):
        DagNode(id="a", label="A", kind=NodeKind.SETUP, depends_on=("b", "b"))
    with pytest.raises(ValueError, match="empty parameter key"):
        DagNode(id="a", label="A", kind=NodeKind.SETUP, params={"": "x"})


def test_dag_node_round_trip_and_signature() -> None:
    original = DagNode(
        id="a",
        label="Collect",
        kind=NodeKind.COLLECT,
        depends_on=("b", "c"),
        params={"z": "last", "a": "first"},
    )
    decoded = DagNode.from_dict(original.to_dict())
    assert decoded == original
    assert decoded.signature == "collect|b,c|a=first,z=last"
    assert node("a").signature != node("b").signature


def test_dag_edge_validation_and_round_trip() -> None:
    edge = DagEdge("a", "b", "depends on")
    assert edge.key == ("a", "b")
    assert DagEdge.from_dict(edge.to_dict()) == edge
    with pytest.raises(ValueError, match="endpoints must not be empty"):
        DagEdge("", "b")
    with pytest.raises(ValueError, match="self edge"):
        DagEdge("a", "a")


def sample_dag() -> PlaybookDag:
    return PlaybookDag(
        id="pb-1",
        name="Triage",
        description="A data-only workflow",
        nodes=(
            node("a", NodeKind.SETUP),
            node("b", NodeKind.COLLECT, "a"),
            node("c", NodeKind.REPORT, "b"),
        ),
        edges=(DagEdge("a", "b"), DagEdge("b", "c")),
    )


def test_playbook_dag_round_trip_and_accessors() -> None:
    dag = sample_dag()
    assert dag.node_ids == ("a", "b", "c")
    assert set(dag.node_map()) == {"a", "b", "c"}
    assert PlaybookDag.from_dict(dag.to_dict()) == dag
    assert dag.description == "A data-only workflow"


def test_playbook_dag_with_node_replaces_by_id() -> None:
    dag = sample_dag()
    updated = dag.with_node(DagNode("b", "Updated", NodeKind.ENRICH))
    assert len(updated.nodes) == 3
    assert updated.node_map()["b"].label == "Updated"
    assert updated.node_ids == ("a", "b", "c")
    added = dag.with_node(node("d", NodeKind.NOTIFY, "c"))
    assert added.node_ids == ("a", "b", "c", "d")


def test_playbook_dag_without_node_drops_edges() -> None:
    dag = sample_dag()
    reduced = dag.without_node("b")
    assert reduced.node_ids == ("a", "c")
    assert reduced.edges == ()
    assert sample_dag().without_node("missing").edges == dag.edges


def test_playbook_dag_rejects_inconsistent_shapes() -> None:
    with pytest.raises(ValueError, match="playbook id must not be empty"):
        PlaybookDag(id="", name="x")
    with pytest.raises(ValueError, match="playbook name must not be empty"):
        PlaybookDag(id="a", name=" ")
    with pytest.raises(ValueError, match="duplicate node ids"):
        PlaybookDag(id="a", name="A", nodes=(node("x"), node("x")))
    with pytest.raises(ValueError, match="missing dependency"):
        PlaybookDag(id="a", name="A", nodes=(node("x", NodeKind.COLLECT, "missing"),))
    with pytest.raises(ValueError, match="edge references unknown node"):
        PlaybookDag(id="a", name="A", edges=(DagEdge("x", "y"),))
    with pytest.raises(ValueError, match="duplicate edge"):
        PlaybookDag(
            id="a",
            name="A",
            nodes=(node("x"), node("y")),
            edges=(DagEdge("x", "y"), DagEdge("x", "y")),
        )


def test_trace_step_validation_and_round_trip() -> None:
    step = TraceStep("a", TraceStatus.SUCCEEDED, "simulated", 17)
    assert step.to_dict() == {
        "node_id": "a",
        "status": "succeeded",
        "detail": "simulated",
        "duration_ms": 17,
    }
    assert TraceStep.from_dict(step.to_dict()) == step
    with pytest.raises(ValueError, match="trace node id must not be empty"):
        TraceStep("", TraceStatus.SUCCEEDED, "x", 0)
    with pytest.raises(ValueError, match="duration must be >= 0"):
        TraceStep("a", TraceStatus.FAILED, "x", -1)


def run_record(run_id: str = "run-1", status: RunStatus = RunStatus.RUNNING) -> RunRecord:
    return RunRecord(
        id=run_id,
        playbook_id="pb-1",
        status=status,
        started_at="2026-01-05T09:00:00.000Z",
        finished_at="2026-01-05T09:01:00.000Z" if status.is_terminal else "",
        trace=(TraceStep("a", TraceStatus.SUCCEEDED, "ok", 10),),
    )


def test_run_record_validation() -> None:
    assert run_record().duration_ms == 10
    with pytest.raises(ValueError, match="run id and playbook id"):
        RunRecord("", "pb", RunStatus.RUNNING, "now")
    with pytest.raises(ValueError, match="start timestamp"):
        RunRecord("r", "pb", RunStatus.RUNNING, "")
    with pytest.raises(ValueError, match="terminal run must have a finish timestamp"):
        RunRecord("r", "pb", RunStatus.SUCCEEDED, "now")
    with pytest.raises(ValueError, match="duplicate node in run trace"):
        RunRecord(
            "r",
            "pb",
            RunStatus.RUNNING,
            "now",
            trace=(
                TraceStep("a", TraceStatus.SUCCEEDED, "ok", 1),
                TraceStep("a", TraceStatus.FAILED, "no", 2),
            ),
        )


def test_run_record_round_trip_and_transition() -> None:
    record = run_record(status=RunStatus.SUCCEEDED)
    assert RunRecord.from_dict(record.to_dict()) == record
    transitioned = run_record().with_status(RunStatus.FAILED, "2026-01-05T09:02:00.000Z")
    assert transitioned.status is RunStatus.FAILED
    assert transitioned.finished_at == "2026-01-05T09:02:00.000Z"
    assert transitioned.trace == run_record().trace
    assert RunRecord.from_dict(record.to_dict()).trigger == "manual"


def schedule() -> Schedule:
    return Schedule(
        id="s-1",
        playbook_id="pb-1",
        frequency=Frequency.DAILY,
        interval_minutes=90,
        minute=30,
        hour=7,
        day_of_week=(0, 2),
        day_of_month=15,
        next_run="2026-01-06T07:30:00.000Z",
    )


def test_schedule_validation() -> None:
    assert schedule().to_dict()["frequency"] == "daily"
    with pytest.raises(ValueError, match="schedule id and playbook id"):
        Schedule("", "pb", Frequency.INTERVAL)
    with pytest.raises(ValueError, match="interval_minutes"):
        Schedule("s", "pb", Frequency.INTERVAL, interval_minutes=0)
    with pytest.raises(ValueError, match="minute must be between"):
        Schedule("s", "pb", Frequency.INTERVAL, minute=60)
    with pytest.raises(ValueError, match="hour must be between"):
        Schedule("s", "pb", Frequency.INTERVAL, hour=24)
    with pytest.raises(ValueError, match="day_of_week values"):
        Schedule("s", "pb", Frequency.WEEKLY, day_of_week=(7,))
    with pytest.raises(ValueError, match="day_of_month must be between"):
        Schedule("s", "pb", Frequency.MONTHLY, day_of_month=32)
    with pytest.raises(ValueError, match="monthly schedules require"):
        Schedule("s", "pb", Frequency.MONTHLY)


def test_schedule_round_trip_and_next_run() -> None:
    original = schedule()
    assert Schedule.from_dict(original.to_dict()) == original
    advanced = original.with_next_run("2026-01-07T07:30:00.000Z")
    assert advanced.next_run == "2026-01-07T07:30:00.000Z"
    assert advanced.id == original.id
    assert advanced.enabled is True
