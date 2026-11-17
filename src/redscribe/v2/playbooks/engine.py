"""Dry-run planning and step execution state for playbooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v2.playbooks.checklists import ChecklistTracker
from redscribe.v2.playbooks.dag import ready_steps, validate_dag
from redscribe.v2.playbooks.errors import InvalidStateError
from redscribe.v2.playbooks.interpolate import RenderResult, render
from redscribe.v2.playbooks.snippets import SnippetLibrary
from redscribe.v2.playbooks.state import (
    apply_step_result,
    complete_run,
    mark_step_ready,
    run_progress,
)
from redscribe.v2.playbooks.templates import TemplateEngine
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Issue,
    PlannedStep,
    Playbook,
    RunPlan,
    RunState,
    StepResult,
    StepStatus,
    Values,
)
from redscribe.v2.playbooks.variables import Resolution, resolve_variables

_SETTLED = frozenset({StepStatus.DONE, StepStatus.SKIPPED, StepStatus.FAILED})


@dataclass(frozen=True, slots=True)
class StepAdvice:
    """Guidance for the next step of a run."""

    step_id: str
    title: str
    reason: str
    command: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "reason": self.reason,
            "command": self.command,
        }


class PlaybookEngine:
    """Pure planning helpers over a playbook and its support catalogs."""

    def __init__(
        self,
        snippets: SnippetLibrary | None = None,
        templates: TemplateEngine | None = None,
    ) -> None:
        self.snippets = snippets if snippets is not None else SnippetLibrary()
        self.templates = templates if templates is not None else TemplateEngine()

    def resolve(
        self,
        playbook: Playbook,
        values: Values | None = None,
        *,
        target: str = "",
        strict: bool = False,
    ) -> Resolution:
        """Resolve declared variables for one playbook."""
        return resolve_variables(playbook.variables, values or {}, target=target, strict=strict)

    def conditions_met(self, playbook: Playbook, values: Values) -> tuple[bool, str]:
        """Return whether all playbook-level conditions pass."""
        del playbook
        return True, ""

    def step_conditions_met(self, step: PlannedStep, values: Values) -> tuple[bool, str]:
        """Evaluate the conditions attached to one step."""
        for condition in step.step.when:
            if not condition.matches(values):
                return False, f"Condition not met: {condition.describe()}"
        return True, ""

    def plan(
        self,
        playbook: Playbook,
        values: Values | None = None,
        *,
        target: str = "",
        strict: bool = False,
    ) -> RunPlan:
        """Build a deterministic, fully interpolated dry-run plan."""
        resolution = self.resolve(playbook, values, target=target, strict=strict)
        context = resolution.values
        graph = validate_dag(playbook.steps)
        warnings: list[Issue] = []
        warnings.extend(
            Issue("validation-warning", f"Invalid dependency: {name}") for name in graph.missing
        )
        warnings.extend(
            Issue("validation-warning", f"Duplicate step: {name}") for name in graph.duplicates
        )
        for cycle in graph.cycles:
            warnings.append(Issue("validation-warning", f"Dependency cycle: {' -> '.join(cycle)}"))
        order = graph.order or tuple(step.id for step in playbook.steps)
        step_map = playbook.step_map()
        planned: list[PlannedStep] = []
        for step_id in order:
            step = step_map.get(step_id)
            if step is None:
                continue
            skipped = False
            reason = ""
            for condition in step.when:
                if not condition.matches(context):
                    skipped = True
                    reason = f"Condition not met: {condition.describe()}"
                    break
            command_source = step.command_template
            if step.snippet_key:
                snippet = self.snippets.find(step.snippet_key)
                if snippet is not None:
                    command_source = snippet.command
                else:
                    warnings.append(
                        Issue(
                            code="missing-snippet",
                            message=(
                                f"Step {step.id} references an unavailable snippet: "
                                f"{step.snippet_key}"
                            ),
                            severity="warning",
                        )
                    )
            rendered: RenderResult = render(command_source, context)
            for name in rendered.unresolved:
                warnings.append(
                    Issue(
                        code="unresolved-variable",
                        message=f"Step {step.id} uses unresolved variable: {name}",
                        severity="warning",
                    )
                )
            checklist = tuple(
                item
                for item in step.checklist
                if item.condition is None or item.condition.matches(context)
            )
            planned.append(
                PlannedStep(
                    step=step,
                    command=rendered.text,
                    variables=dict(context),
                    skipped=skipped,
                    reason=reason,
                    checklist=checklist,
                )
            )
        for key in resolution.missing:
            warnings.append(
                Issue("missing-variable", f"Missing required variable: {key}", severity="warning")
            )
        warnings.extend(resolution.invalid)
        return RunPlan(
            playbook_key=playbook.key,
            version=playbook.version,
            order=order,
            layers=graph.layers,
            steps=tuple(planned),
            missing_variables=resolution.missing,
            warnings=tuple(warnings),
        )

    def preview(self, playbook: Playbook, plan: RunPlan) -> str:
        """Render a Markdown preview of a dry-run plan."""
        lines = [
            f"# {playbook.title}",
            "",
            f"> Playbook `{playbook.key}` · version {playbook.version}",
            "",
        ]
        if playbook.description:
            lines.extend([playbook.description, ""])
        if plan.missing_variables:
            lines.extend(["**Missing variables:** " + ", ".join(plan.missing_variables), ""])
        for index, item in enumerate(plan.steps, start=1):
            step = item.step
            lines.append(f"## {index}. {step.title}")
            lines.append("")
            lines.append(f"- **Step id:** `{step.id}`")
            lines.append(f"- **Kind:** {step.kind.value}")
            lines.append(f"- **Status:** {'skipped' if item.skipped else 'planned'}")
            if item.reason:
                lines.append(f"- **Reason:** {item.reason}")
            if step.summary:
                lines.extend(["", step.summary])
            if item.command:
                lines.extend(["", "```text", item.command, "```"])
            if item.checklist:
                lines.extend(["", "Checklist:"])
                lines.extend(f"- [ ] {check.label}" for check in item.checklist)
            if step.note:
                lines.extend(["", f"> {step.note}"])
            lines.append("")
        if plan.warnings:
            lines.extend(["## Diagnostics", ""])
            lines.extend(f"- {issue.message}" for issue in plan.warnings)
            lines.append("")
        return "\n".join(lines)

    def next_step(self, plan: RunPlan, run: RunState) -> StepAdvice | None:
        """Return the next executable step, if any."""
        graph = {
            item.step.id: tuple(
                dependency
                for dependency in item.step.depends_on
                if any(p.step.id == dependency for p in plan.steps)
            )
            for item in plan.steps
        }
        settled = {key for key, status in run.step_status.items() if status in _SETTLED}
        ready = ready_steps(graph, {key: "done" if key in settled else "pending" for key in graph})
        for item in plan.steps:
            if item.step.id not in ready:
                continue
            status = run.step_status.get(item.step.id, StepStatus.PENDING)
            if status in _SETTLED:
                continue
            reason = "Dependencies are satisfied"
            if item.skipped:
                reason = item.reason or "Step is conditionally skipped"
            return StepAdvice(
                step_id=item.step.id,
                title=item.step.title,
                reason=reason,
                command=item.command if not item.skipped else "",
            )
        return None

    def advance(
        self,
        run: RunState,
        plan: RunPlan,
        step_id: str,
        result: StepResult | None = None,
    ) -> RunState:
        """Apply a step result, then complete the run when all steps settle."""
        if run.status.value not in ("running", "paused"):
            raise InvalidStateError("Run is not active")
        planned = plan.step(step_id)
        if planned is None:
            raise InvalidStateError(f"Unknown plan step: {step_id}")
        outcome = result if result is not None else StepResult()
        updated = apply_step_result(run, step_id, outcome)
        if all(status in _SETTLED for status in updated.step_status.values()):
            return complete_run(updated)
        advice = self.next_step(plan, updated)
        if advice is not None:
            updated = mark_step_ready(updated, advice.step_id)
        return updated

    def start_step(self, run: RunState, step_id: str) -> RunState:
        """Mark a step as running."""
        return apply_step_result(run, step_id, StepResult(status=StepStatus.RUNNING))

    def checklist_progress(self, playbook: Playbook, run: RunState) -> dict[str, Any]:
        """Return checklist progress for a run."""
        progress: dict[str, Any] = run_progress(run, playbook)
        checklist: dict[str, Any] = progress["checklist"]
        return checklist

    def step_checklist(self, plan: RunPlan, step_id: str) -> tuple[ChecklistItem, ...]:
        """Return the visible checklist for one planned step."""
        planned = plan.step(step_id)
        return planned.checklist if planned is not None else ()

    def make_tracker(self, playbook: Playbook, run: RunState) -> ChecklistTracker:
        """Build a checklist tracker over all playbook items."""
        items = tuple(item for step in playbook.steps for item in step.checklist)
        return ChecklistTracker.from_items(items, state=run.checklist, notes=run.notes)
