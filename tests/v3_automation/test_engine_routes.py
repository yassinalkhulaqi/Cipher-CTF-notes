"""End-to-end engine behavior and the automation API namespace."""

from __future__ import annotations

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.router import V3Router
from redscribe.v3.automation import AutomationEngine
from redscribe.v3.automation.errors import (
    ReplayMismatchError,
    RollbackError,
    VariableResolutionError,
)
from redscribe.v3.automation.parsing import parse_playbook
from redscribe.v3.automation.rollback import compensation_plan
from redscribe.v3.automation.trace import diff_traces
from redscribe.v3.clock import FixedClock
from redscribe.v3.events import EventBus
from redscribe.v3.namespaces.automation import get_engine, register, set_engine

from .helpers import linear_steps, playbook_payload, sample_playbook


def _engine(bus: EventBus | None = None) -> AutomationEngine:
    return AutomationEngine(clock=FixedClock(start=1_000.0, step=1.0), bus=bus)


def test_validate_reports_playbook_and_variable_issues() -> None:
    engine = _engine()
    playbook = sample_playbook()
    engine.add(playbook)
    report = engine.validate("smoke", {"target": "target:t1"})
    assert report.ok is True
    assert report.compilation.ok is True
    assert report.as_dict()["variables"]["ok"] is True
    invalid = engine.validate("smoke", {})
    assert invalid.ok is False
    assert any(issue.code == "missing_variable" for issue in invalid.issues)
    assert engine.compile("smoke").order == ("note", "finding", "evidence", "event")
    assert engine.occurrences("smoke", 0.0, 10.0) == ()


def test_connect_updates_registry_without_mutating_on_cycle() -> None:
    engine = _engine()
    engine.add(sample_playbook())
    updated, problem = engine.connect("smoke", source="event", target="note")
    assert problem is not None
    assert updated is None
    assert engine.compile("smoke").order == ("note", "finding", "evidence", "event")
    updated, problem = engine.connect("smoke", source="note", target="event")
    assert problem is None
    assert updated is not None
    engine.registry.replace(updated)
    assert engine.compile("smoke").order == ("note", "finding", "evidence", "event")
    assert engine.registry.get("smoke").step("event").depends_on == ("evidence", "note")


def test_dry_run_records_every_mutation_with_zero_writes() -> None:
    engine = _engine()
    engine.add(sample_playbook())
    values = {"target": "target:t1"}
    trace = engine.dry_run("smoke", values)
    assert trace.writes == 0
    assert trace.mode.value == "dry_run"
    assert len(trace.entries) == 4
    assert len(trace.mutations) == 4
    assert [entry.step_id for entry in trace.entries] == [
        "note",
        "finding",
        "evidence",
        "event",
    ]
    assert all(
        entry.result is not None and entry.result.applied is False for entry in trace.entries
    )
    assert engine.list_runs() == ()


def test_run_persists_and_replay_is_deterministic() -> None:
    bus = EventBus()
    engine = _engine(bus)
    engine.add(sample_playbook())
    record = engine.run("smoke", {"target": "target:t1"})
    assert record.status.value == "completed"
    assert record.mode.value == "live"
    assert record.trace_digest
    assert record.state_digest
    assert len(engine.list_runs()) == 1
    assert engine.get_run(record.id) == record
    assert engine.list_runs(playbook_ref="playbook:smoke", limit=1)[0].id == record.id
    assert bus.of_kind("automation.step.executed")
    assert bus.of_kind("automation.smoke")

    replay = engine.replay(record.id)
    assert replay.deterministic is True
    assert replay.differences == ()
    assert replay.replay_trace.digest == record.trace_digest
    with pytest.raises(ReplayMismatchError):
        engine.replay(record.id, values={"target": "target:other"})


def test_rollback_restores_equivalence_and_persists_new_record() -> None:
    bus = EventBus()
    engine = _engine(bus)
    engine.add(sample_playbook())
    record = engine.run("smoke", {"target": "target:t1"})
    trace = engine._traces[record.id]
    plan = compensation_plan(trace)
    assert len(plan) == len(trace.mutations)
    assert plan[0].step_id == trace.mutations[-1].step_id
    report = engine.rollback(record.id)
    assert report.ok is True
    assert report.equivalent is True
    assert report.record.status.value == "rolled_back"
    assert report.record.rollback_of == record.id
    assert len(report.record.trace) > len(record.trace)
    assert len(engine.list_runs()) == 2
    assert bus.of_kind("automation.rollback.requested")
    assert bus.of_kind("automation.step.compensated")
    assert bus.of_kind("automation.rollback.completed")
    with pytest.raises(RollbackError):
        engine.rollback(record.id)


def test_twenty_step_playbook_dry_run_execute_replay() -> None:
    steps = tuple(step.as_dict() for step in linear_steps(20))
    engine = _engine()
    engine.add(parse_playbook({"id": "large", "title": "Large", "steps": list(steps)}))
    trace = engine.dry_run("large")
    assert len(trace.entries) == 20
    assert trace.writes == 0
    record = engine.run("large")
    assert len(record.trace) == 20
    replay = engine.replay(record.id)
    assert replay.deterministic is True
    assert diff_traces(engine.dry_run("large"), engine.dry_run("large")) == ()
    report = engine.rollback(record.id)
    assert report.ok is True
    assert len(report.compensations) == 20


def test_secrets_are_never_persisted_in_run_records() -> None:
    payload = playbook_payload(
        variables=[{"key": "token", "kind": "text", "secret": True, "required": True}]
    )
    payload["steps"][0]["inputs"]["title"] = "Note"
    engine = _engine()
    engine.add(parse_playbook(payload))
    record = engine.run("smoke", {"token": "s3cr3t"})
    assert record.variables == {"token": "***"}
    assert "s3cr3t" not in str(record.as_dict())
    with pytest.raises(ReplayMismatchError):
        engine.replay(record.id)
    replay = engine.replay(record.id, values={"token": "s3cr3t"})
    assert replay.deterministic is True


def test_namespace_routes_are_registered_and_dispatchable() -> None:
    engine = _engine()
    set_engine(engine)
    router = V3Router()
    register(router)
    actions = {route.action for route in router.routes() if route.namespace == "automation"}
    assert actions == {
        "validate",
        "compile",
        "connect",
        "dry_run",
        "run",
        "runs",
        "run_get",
        "replay",
        "rollback",
        "recurrence",
        "diff",
    }
    assert get_engine() is engine
    assert "automation" in router.namespaces()

    data = router.dispatch(
        "automation", "dry_run", {"playbook": playbook_payload(), "values": {"target": "target:t"}}
    )
    assert data["trace"]["writes"] == 0
    data = router.dispatch(
        "automation", "run", {"playbook_ref": "playbook:smoke", "values": {"target": "target:t"}}
    )
    run_id = data["run"]["id"]
    assert router.dispatch("automation", "runs", {})["runs"][0]["id"] == run_id
    assert router.dispatch("automation", "run_get", {"run_id": run_id})["run"]["id"] == run_id
    assert router.dispatch("automation", "replay", {"run_id": run_id})["replay"]["deterministic"]
    assert (
        router.dispatch("automation", "diff", {"left": run_id, "right": run_id})["differences"]
        == []
    )
    assert router.dispatch("automation", "rollback", {"run_id": run_id})["rollback"]["ok"]

    recurrence = router.dispatch(
        "automation",
        "recurrence",
        {"rule": {"frequency": "daily"}, "after": 0.0, "before": 3 * 86_400},
    )
    assert len(recurrence["timestamps"]) == 3
    assert recurrence["description"].startswith("Daily")
    set_engine(None)


def test_namespace_errors_are_stable_and_capability_is_checked() -> None:
    set_engine(_engine())
    router = V3Router()
    register(router)
    with pytest.raises(V3Error) as error:
        router.dispatch("automation", "dry_run", {"playbook": {"id": "x"}})
    assert error.value.code.value == "invalid_request"

    with pytest.raises(V3Error) as forbidden:
        router.dispatch(
            "automation",
            "validate",
            {"playbook": playbook_payload(), "values": {"target": "target:t"}},
            {"X-Capability": "encryption"},
        )
    assert forbidden.value.status == 403
    set_engine(None)


def test_validation_failures_never_write() -> None:
    engine = _engine()
    engine.add(sample_playbook())
    with pytest.raises(VariableResolutionError):
        engine.run("smoke", {})
    assert engine.list_runs() == ()
