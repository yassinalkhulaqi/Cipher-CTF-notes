"""Execution state transitions and run snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from redscribe.v2.playbooks.checklists import ChecklistTracker
from redscribe.v2.playbooks.errors import InvalidStateError
from redscribe.v2.playbooks.import_export import run_from_dict
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Playbook,
    RunEvent,
    RunState,
    RunStatus,
    StepResult,
    StepStatus,
    Values,
)

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PLANNED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {RunStatus.PAUSED, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset({RunStatus.RUNNING}),
    RunStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.CANCELLED})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    """Return true when a lifecycle transition is permitted."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def new_run(
    run_id: int,
    playbook: Playbook,
    values: Values | None = None,
    *,
    status: RunStatus = RunStatus.PLANNED,
) -> RunState:
    """Create a fresh run snapshot for a playbook."""
    now = _now()
    run = RunState(
        id=run_id,
        playbook_key=playbook.key,
        version=playbook.version,
        status=status,
        values=dict(values or {}),
        step_status={step.id: StepStatus.PENDING for step in playbook.steps},
        started_at=now if status == RunStatus.RUNNING else "",
        updated_at=now,
    )
    return append_event(run, "created", f"Run created for playbook {playbook.key}")


def transition(
    run: RunState,
    target: RunStatus,
    *,
    message: str = "",
    at: str | None = None,
) -> RunState:
    """Apply a lifecycle transition and append an event."""
    if not can_transition(run.status, target):
        raise InvalidStateError(
            f"Cannot transition run from {run.status.value} to {target.value}",
            details={"from": run.status.value, "to": target.value},
        )
    now = at or _now()
    updates: dict[str, Any] = {
        "status": target,
        "updated_at": now,
        "started_at": run.started_at or (now if target == RunStatus.RUNNING else ""),
        "finished_at": now if target in TERMINAL_STATUSES else "",
    }
    updated = run.with_changes(**updates)
    return append_event(
        updated, "transition", message or f"Status changed to {target.value}", at=now
    )


def start_run(run: RunState) -> RunState:
    """Start a planned run."""
    return transition(run, RunStatus.RUNNING, message="Run started")


def pause_run(run: RunState) -> RunState:
    """Pause a running run."""
    return transition(run, RunStatus.PAUSED, message="Run paused")


def resume_run(run: RunState) -> RunState:
    """Resume a paused run."""
    return transition(run, RunStatus.RUNNING, message="Run resumed")


def complete_run(run: RunState) -> RunState:
    """Complete a running run."""
    return transition(run, RunStatus.COMPLETED, message="Run completed")


def fail_run(run: RunState, reason: str = "Run failed") -> RunState:
    """Fail a running or paused run."""
    if run.status == RunStatus.PAUSED:
        resumed = transition(run, RunStatus.RUNNING, message="Resuming before failure")
        return transition(resumed, RunStatus.FAILED, message=reason)
    return transition(run, RunStatus.FAILED, message=reason)


def cancel_run(run: RunState, reason: str = "Run cancelled") -> RunState:
    """Cancel a run from any active state."""
    if run.status in TERMINAL_STATUSES:
        raise InvalidStateError("Run is already in a terminal state")
    if run.status in (RunStatus.FAILED, RunStatus.PAUSED):
        active = transition(run, RunStatus.RUNNING, message="Resuming before cancellation")
        return transition(active, RunStatus.CANCELLED, message=reason)
    return transition(run, RunStatus.CANCELLED, message=reason)


def apply_step_result(
    run: RunState,
    step_id: str,
    result: StepResult,
    *,
    at: str | None = None,
) -> RunState:
    """Record the outcome of one step."""
    if run.status not in (RunStatus.RUNNING, RunStatus.PAUSED):
        raise InvalidStateError("Run is not active")
    if step_id not in run.step_status:
        raise InvalidStateError(f"Unknown run step: {step_id}")
    statuses = dict(run.step_status)
    statuses[step_id] = result.status
    values = dict(run.values)
    values.update(result.variables)
    context = dict(run.context)
    context[step_id] = {"output": result.output, "message": result.message}
    updated = run.with_changes(
        step_status=statuses,
        values=values,
        context=context,
        current_step=""
        if result.status in (StepStatus.DONE, StepStatus.SKIPPED, StepStatus.FAILED)
        else step_id,
        updated_at=at or _now(),
    )
    return append_event(
        updated,
        "step",
        result.message or f"Step {step_id} is {result.status.value}",
        step_id=step_id,
        data={"status": result.status.value, "output": result.output},
        at=at,
    )


def mark_step_ready(run: RunState, step_id: str, *, at: str | None = None) -> RunState:
    """Mark a step ready for operator action."""
    statuses = dict(run.step_status)
    statuses[step_id] = StepStatus.READY
    updated = run.with_changes(
        step_status=statuses,
        current_step=step_id,
        updated_at=at or _now(),
    )
    return append_event(updated, "ready", f"Step {step_id} is ready", step_id=step_id, at=at)


def apply_checklist_state(
    run: RunState,
    item_id: str,
    state: str,
    *,
    note: str = "",
    at: str | None = None,
) -> RunState:
    """Update one checklist item in a run snapshot."""
    tracker = ChecklistTracker.from_dict(
        {"states": run.checklist, "notes": run.notes},
        items=(ChecklistItem(id=item_id, label=item_id),),
    )
    updated_tracker = tracker.set_state(item_id, state)
    if note:
        updated_tracker = updated_tracker.set_note(item_id, note)
    updated = run.with_changes(
        checklist=dict(updated_tracker.states),
        notes=dict(updated_tracker.notes),
        updated_at=at or _now(),
    )
    return append_event(
        updated,
        "checklist",
        f"Checklist item {item_id} is {state}",
        data={"item": item_id, "state": state},
        at=at,
    )


def append_event(
    run: RunState,
    kind: str,
    message: str,
    *,
    step_id: str = "",
    data: dict[str, Any] | None = None,
    at: str | None = None,
) -> RunState:
    """Append one immutable event to a run."""
    event = RunEvent(
        seq=len(run.events) + 1,
        at=at or _now(),
        kind=kind,
        message=message,
        step_id=step_id,
        data=dict(data or {}),
    )
    return run.with_changes(events=(*run.events, event))


def run_progress(run: RunState, playbook: Playbook) -> dict[str, Any]:
    """Compute step and checklist progress for a run."""
    statuses = run.step_status
    counts = {status.value: 0 for status in StepStatus}
    for status in statuses.values():
        counts[status.value] += 1
    total = len(playbook.steps)
    settled = counts[StepStatus.DONE.value] + counts[StepStatus.SKIPPED.value]
    items = tuple(item for step in playbook.steps for item in step.checklist)
    tracker = ChecklistTracker.from_items(items, state=run.checklist, notes=run.notes)
    return {
        "status": run.status.value,
        "step_total": total,
        "step_settled": settled,
        "percent": round(settled / total * 100) if total else 100,
        "step_counts": counts,
        "checklist": tracker.progress().as_dict(),
    }


def snapshot(run: RunState) -> dict[str, Any]:
    """Serialize a run for storage or transport."""
    return run.as_dict()


def restore(payload: Any) -> RunState:
    """Restore a run from a serialized snapshot."""
    return run_from_dict(payload)


def is_terminal(run: RunState) -> bool:
    """Return true when no further transitions are expected."""
    return run.status in TERMINAL_STATUSES
