"""Remediation checklist construction and progress tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from redscribe.v3.findings.models import RemediationTask, TaskStatus

_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class RemediationError(ValueError):
    """Raised when a remediation checklist is invalid."""


@dataclass(frozen=True, slots=True)
class RemediationPlan:
    """A derived view over a finding's immutable remediation tasks."""

    tasks: tuple[RemediationTask, ...]
    owner: str = ""
    target_date: str = ""
    notes: str = ""

    @property
    def total(self) -> int:
        """Number of tasks in the plan."""
        return len(self.tasks)

    @property
    def done(self) -> int:
        """Number of settled tasks."""
        return sum(1 for task in self.tasks if task.status.is_settled)

    @property
    def skipped(self) -> int:
        """Number of skipped tasks."""
        return sum(1 for task in self.tasks if task.status is TaskStatus.SKIPPED)

    @property
    def blocked(self) -> tuple[RemediationTask, ...]:
        """Tasks still in progress or waiting to start."""
        return tuple(task for task in self.tasks if not task.status.is_settled)

    @property
    def complete(self) -> bool:
        """Whether every task is settled and at least one task exists."""
        return bool(self.tasks) and self.done == self.total

    @property
    def percent(self) -> int:
        """Integer completion percentage in the 0..100 range."""
        return round((self.done / self.total) * 100) if self.tasks else 0

    def next_task(self) -> RemediationTask | None:
        """Return the first unfinished task in checklist order."""
        return self.blocked[0] if self.blocked else None

    def task(self, task_id: str) -> RemediationTask | None:
        """Find a task by id."""
        return next((task for task in self.tasks if task.task_id == task_id), None)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        upcoming = self.next_task()
        return {
            "owner": self.owner,
            "target_date": self.target_date,
            "notes": self.notes,
            "total": self.total,
            "done": self.done,
            "skipped": self.skipped,
            "percent": self.percent,
            "complete": self.complete,
            "next_task": upcoming.task_id if upcoming else "",
            "tasks": [task.as_dict() for task in self.tasks],
        }


def plan_for(
    tasks: tuple[RemediationTask, ...],
    *,
    owner: str = "",
    target_date: str = "",
    notes: str = "",
) -> RemediationPlan:
    """Build a remediation plan view over task snapshots."""
    return RemediationPlan(tasks=tasks, owner=owner, target_date=target_date, notes=notes)


def new_task(
    task_id: str,
    title: str,
    *,
    detail: str = "",
    owner: str = "",
    due_at: float = 0.0,
) -> RemediationTask:
    """Create a validated remediation task."""
    if not _TASK_ID_PATTERN.match(task_id):
        raise RemediationError("Task id must contain only letters, digits, and ._:-")
    return RemediationTask(
        task_id=task_id,
        title=title,
        detail=detail,
        owner=owner,
        due_at=due_at,
    )


def task_from_lines(
    text: str,
    *,
    prefix: str = "task",
    owner: str = "",
) -> tuple[RemediationTask, ...]:
    """Turn newline-separated remediation guidance into a checklist."""
    tasks: list[RemediationTask] = []
    seen: set[str] = set()
    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip().lstrip("-*0123456789. ").strip()
        if not line:
            continue
        task_id = f"{prefix}-{index}"
        while task_id in seen:
            task_id += "-x"
        seen.add(task_id)
        tasks.append(new_task(task_id, line[:240], owner=owner))
    return tuple(tasks)


def update_task(
    tasks: tuple[RemediationTask, ...],
    task_id: str,
    *,
    status: TaskStatus,
    timestamp: float,
    proof_ref: str = "",
) -> tuple[RemediationTask, ...]:
    """Replace one task's status, preserving checklist order."""
    found = False
    updated: list[RemediationTask] = []
    for task in tasks:
        if task.task_id == task_id:
            updated.append(
                task.with_status(status=status, timestamp=timestamp, proof_ref=proof_ref)
            )
            found = True
        else:
            updated.append(task)
    if not found:
        raise RemediationError(f"Unknown remediation task: {task_id}")
    return tuple(updated)


def add_task(
    tasks: tuple[RemediationTask, ...],
    task: RemediationTask,
) -> tuple[RemediationTask, ...]:
    """Append a task, rejecting duplicate ids."""
    if any(existing.task_id == task.task_id for existing in tasks):
        raise RemediationError(f"Duplicate remediation task id: {task.task_id}")
    return (*tasks, task)


def checklist_issues(tasks: tuple[RemediationTask, ...]) -> tuple[str, ...]:
    """Return structural issues with a checklist for validation reporting."""
    issues: list[str] = []
    if not tasks:
        issues.append("checklist is empty")
    ids = [task.task_id for task in tasks]
    if len(ids) != len(set(ids)):
        issues.append("duplicate task ids")
    untitled = [task.task_id for task in tasks if not task.title.strip()]
    if untitled:
        issues.append("untitled tasks: " + ", ".join(untitled))
    return tuple(issues)
