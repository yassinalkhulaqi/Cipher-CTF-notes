from __future__ import annotations

import pytest

from redscribe.v2.playbooks.engine import PlaybookEngine
from redscribe.v2.playbooks.errors import InvalidStateError
from redscribe.v2.playbooks.state import (
    append_event,
    apply_checklist_state,
    apply_step_result,
    can_transition,
    cancel_run,
    complete_run,
    fail_run,
    is_terminal,
    mark_step_ready,
    new_run,
    pause_run,
    restore,
    resume_run,
    run_progress,
    snapshot,
    start_run,
    transition,
)
from redscribe.v2.playbooks.types import (
    Condition,
    ConditionOperator,
    RunStatus,
    StepResult,
    StepStatus,
)


def _values() -> dict[str, str]:
    return {"target": "example.com", "ports": "80,443", "token": "secret"}


def test_can_transition_follows_lifecycle_rules() -> None:
    assert can_transition(RunStatus.PLANNED, RunStatus.RUNNING)
    assert can_transition(RunStatus.RUNNING, RunStatus.PAUSED)
    assert not can_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    assert not can_transition(RunStatus.PLANNED, RunStatus.COMPLETED)


def test_new_run_initializes_all_steps(playbook: object) -> None:
    run = new_run(9, playbook, {"target": "example.com"})

    assert run.id == 9
    assert run.status == RunStatus.PLANNED
    assert set(run.step_status) == {step.id for step in playbook.steps}
    assert all(status == StepStatus.PENDING for status in run.step_status.values())
    assert run.events[0].kind == "created"


def test_start_pause_resume_and_complete_run(playbook: object) -> None:
    run = start_run(new_run(1, playbook))

    assert run.status == RunStatus.RUNNING

    paused = pause_run(run)
    assert paused.status == RunStatus.PAUSED

    resumed = resume_run(paused)
    assert resumed.status == RunStatus.RUNNING

    completed = complete_run(resumed)
    assert completed.status == RunStatus.COMPLETED
    assert completed.finished_at
    assert is_terminal(completed)
    assert [event.kind for event in completed.events][-1] == "transition"


def test_transition_rejects_illegal_moves(playbook: object) -> None:
    with pytest.raises(InvalidStateError, match="Cannot transition"):
        transition(new_run(1, playbook), RunStatus.COMPLETED)


def test_fail_run_can_resume_before_failing(playbook: object) -> None:
    run = pause_run(start_run(new_run(1, playbook)))
    failed = fail_run(run, "Blocked by operator")

    assert failed.status == RunStatus.FAILED
    assert "Blocked" in failed.events[-1].message


def test_cancel_run_from_active_states(playbook: object) -> None:
    assert cancel_run(new_run(1, playbook)).status == RunStatus.CANCELLED
    assert cancel_run(start_run(new_run(2, playbook))).status == RunStatus.CANCELLED
    assert cancel_run(fail_run(start_run(new_run(3, playbook)))).status == RunStatus.CANCELLED


def test_cancel_run_rejects_terminal_run(playbook: object) -> None:
    with pytest.raises(InvalidStateError, match="terminal"):
        cancel_run(complete_run(start_run(new_run(1, playbook))))


def test_append_event_keeps_sequence_numbers(playbook: object) -> None:
    run = new_run(1, playbook)
    updated = append_event(run, "note", "Checked", step_id="a", data={"ok": True})

    assert len(run.events) == 1
    assert len(updated.events) == 2
    assert updated.events[-1].seq == 2
    assert updated.events[-1].data == {"ok": True}


def test_apply_step_result_records_status_and_values(playbook: object) -> None:
    run = start_run(new_run(1, playbook))
    updated = apply_step_result(
        run,
        "a",
        StepResult(status=StepStatus.DONE, message="ok", output="out", variables={"found": "yes"}),
        at="2026-03-01T00:00:00+00:00",
    )

    assert updated.step_status["a"] == StepStatus.DONE
    assert updated.values["found"] == "yes"
    assert updated.context["a"]["output"] == "out"
    assert updated.current_step == ""
    assert updated.updated_at == "2026-03-01T00:00:00+00:00"


def test_apply_step_result_keeps_current_step_for_running(playbook: object) -> None:
    run = start_run(new_run(1, playbook))
    updated = apply_step_result(run, "a", StepResult(status=StepStatus.RUNNING))

    assert updated.current_step == "a"


def test_apply_step_result_requires_active_run_and_known_step(playbook: object) -> None:
    planned = new_run(1, playbook)

    with pytest.raises(InvalidStateError, match="not active"):
        apply_step_result(planned, "a", StepResult())

    with pytest.raises(InvalidStateError, match="Unknown run step"):
        apply_step_result(start_run(planned), "missing", StepResult())


def test_mark_step_ready_sets_current_step(playbook: object) -> None:
    run = start_run(new_run(1, playbook))
    ready = mark_step_ready(run, "b")

    assert ready.step_status["b"] == StepStatus.READY
    assert ready.current_step == "b"
    assert ready.events[-1].kind == "ready"


def test_apply_checklist_state_updates_tracker(playbook: object) -> None:
    run = start_run(new_run(1, playbook))
    updated = apply_checklist_state(run, "c1", "done", note="verified")

    assert updated.checklist["c1"] == "done"
    assert updated.notes["c1"] == "verified"
    assert updated.events[-1].kind == "checklist"


def test_run_progress_counts_steps_and_checklists(playbook: object) -> None:
    run = start_run(new_run(1, playbook))
    run = apply_step_result(run, "a", StepResult(status=StepStatus.DONE))
    run = apply_checklist_state(run, "c1", "done")

    progress = run_progress(run, playbook)

    assert progress["status"] == "running"
    assert progress["step_total"] == 3
    assert progress["step_settled"] == 1
    assert progress["step_counts"]["done"] == 1
    assert progress["checklist"]["done"] == 1


def test_snapshot_and_restore_round_trip(playbook: object) -> None:
    run = start_run(new_run(7, playbook, _values()))
    run = apply_step_result(run, "a", StepResult(status=StepStatus.DONE))

    restored = restore(snapshot(run))

    assert restored.id == run.id
    assert restored.status == run.status
    assert restored.values == run.values
    assert restored.step_status == run.step_status
    assert len(restored.events) == len(run.events)


def test_engine_plan_orders_steps_and_interpolates(playbook: object) -> None:
    engine = PlaybookEngine()
    plan = engine.plan(playbook, _values())

    assert plan.order == ("a", "b", "c")
    assert plan.layers == (("a",), ("b",), ("c",))
    assert "example.com" in plan.steps[0].command
    assert "80,443" in plan.steps[0].command
    assert plan.missing_variables == ()


def test_engine_plan_reports_missing_required_variables(playbook: object) -> None:
    plan = PlaybookEngine().plan(playbook, {})

    assert "target" in plan.missing_variables
    assert "token" in plan.missing_variables
    assert any(issue.code == "missing-variable" for issue in plan.warnings)


def test_engine_plan_marks_condition_skips(playbook: object) -> None:
    conditional = playbook.with_changes(
        steps=(
            playbook.steps[0].with_changes(
                when=(Condition(field="target", operator=ConditionOperator.EQ, value="nope"),)
            ),
            *playbook.steps[1:],
        )
    )
    plan = PlaybookEngine().plan(conditional, _values())

    assert plan.steps[0].skipped is True
    assert "Condition not met" in plan.steps[0].reason


def test_engine_preview_contains_markdown_sections(playbook: object) -> None:
    engine = PlaybookEngine()
    plan = engine.plan(playbook, _values())
    preview = engine.preview(playbook, plan)

    assert preview.startswith("# Fixture Playbook")
    assert "## 1. Enumerate" in preview
    assert "```text" in preview
    assert "Checklist:" in preview


def test_engine_next_step_respects_dependencies(playbook: object) -> None:
    engine = PlaybookEngine()
    plan = engine.plan(playbook, _values())
    run = start_run(new_run(1, playbook, _values()))

    first = engine.next_step(plan, run)

    assert first is not None
    assert first.step_id == "a"

    ready = mark_step_ready(run, "b")
    second = engine.next_step(plan, ready)

    assert second is not None
    assert second.step_id == "a"


def test_engine_next_step_returns_none_when_all_steps_settled(playbook: object) -> None:
    engine = PlaybookEngine()
    plan = engine.plan(playbook, _values())
    run = start_run(new_run(1, playbook, _values()))
    run = run.with_changes(step_status={step.id: StepStatus.DONE for step in playbook.steps})

    assert engine.next_step(plan, run) is None


def test_engine_advance_moves_through_run_to_completion(playbook: object) -> None:
    engine = PlaybookEngine()
    plan = engine.plan(playbook, _values())
    run = start_run(new_run(1, playbook, _values()))

    run = engine.advance(run, plan, "a", StepResult(status=StepStatus.DONE))
    assert run.step_status["a"] == StepStatus.DONE
    assert run.current_step == "b"

    run = engine.advance(run, plan, "b", StepResult(status=StepStatus.DONE))
    assert run.current_step == "c"

    run = engine.advance(run, plan, "c", StepResult(status=StepStatus.SKIPPED))
    assert run.status == RunStatus.COMPLETED


def test_engine_advance_rejects_inactive_run_and_unknown_step(playbook: object) -> None:
    engine = PlaybookEngine()
    plan = engine.plan(playbook, _values())
    planned = new_run(1, playbook, _values())

    with pytest.raises(InvalidStateError, match="not active"):
        engine.advance(planned, plan, "a")

    with pytest.raises(InvalidStateError, match="Unknown plan step"):
        engine.advance(start_run(planned), plan, "missing")


def test_engine_step_checklist_uses_conditions(playbook: object) -> None:
    from redscribe.v2.playbooks.types import ChecklistItem, PlaybookStep

    step = PlaybookStep(
        id="a",
        title="A",
        checklist=(
            ChecklistItem(id="always", label="Always"),
            ChecklistItem(
                id="conditional",
                label="Conditional",
                condition=Condition(field="target", operator=ConditionOperator.EXISTS),
            ),
        ),
    )
    plan = PlaybookEngine().plan(
        playbook.with_changes(steps=(step,), variables=()), {"target": "example.com"}
    )

    assert [item.id for item in PlaybookEngine().step_checklist(plan, "a")] == [
        "always",
        "conditional",
    ]
