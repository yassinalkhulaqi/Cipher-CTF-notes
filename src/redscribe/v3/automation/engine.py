"""High-level automation engine: validate, plan, dry-run, run, replay, roll back."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from redscribe.v3.automation.dag import DagCompilation, compile_dag, connect
from redscribe.v3.automation.encoding import digest
from redscribe.v3.automation.errors import (
    AutomationError,
    ReplayMismatchError,
    RollbackError,
    VariableResolutionError,
)
from redscribe.v3.automation.executor import (
    InMemoryMutationSink,
    MutationSink,
    StepExecutor,
    TraceOnlySink,
    new_run_id,
)
from redscribe.v3.automation.recurrence import occurrences
from redscribe.v3.automation.registry import PlaybookRegistry
from redscribe.v3.automation.rollback import RollbackManager, RollbackReport
from redscribe.v3.automation.runs import InMemoryRunStore, RunRecordStore, RunService
from redscribe.v3.automation.trace import TraceRecorder, diff_traces
from redscribe.v3.automation.types import (
    DiffEntry,
    DryRunTrace,
    PlaybookDefinition,
    RunMode,
    RunRecord,
    RunStatus,
    StepDefinition,
    ValidationIssue,
    Value,
)
from redscribe.v3.automation.variables import (
    VariableResolution,
    fingerprint_values,
    validate_values,
)
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.events import EventBus


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Combined DAG, schema and variable validation result."""

    playbook_ref: str
    compilation: DagCompilation
    resolution: VariableResolution
    issues: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        """Whether the playbook can be executed."""
        return (
            not any(item.is_error for item in self.issues)
            and self.compilation.ok
            and self.resolution.ok
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "playbook_ref": self.playbook_ref,
            "ok": self.ok,
            "issues": [item.as_dict() for item in self.issues],
            "dag": self.compilation.as_dict(),
            "variables": self.resolution.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Determinism check between a stored run and a fresh replay."""

    original_id: str
    replay_trace: DryRunTrace
    differences: tuple[DiffEntry, ...]
    deterministic: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "original_id": self.original_id,
            "deterministic": self.deterministic,
            "trace_digest": self.replay_trace.digest,
            "differences": [item.as_dict() for item in self.differences],
        }


class AutomationEngine:
    """Coordinate all automation services with injectable dependencies."""

    def __init__(
        self,
        *,
        store: RunRecordStore | None = None,
        bus: EventBus | None = None,
        clock: Clock | None = None,
        sink_factory: Callable[[], InMemoryMutationSink] | None = None,
    ) -> None:
        self.registry = PlaybookRegistry()
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self.sink_factory = sink_factory or InMemoryMutationSink
        self.runs = RunService(store or InMemoryRunStore())
        self._sinks: dict[str, MutationSink] = {}
        self._traces: dict[str, DryRunTrace] = {}
        self._rolled_back: set[str] = set()

    def add(self, playbook: PlaybookDefinition) -> PlaybookDefinition:
        """Register a playbook document."""
        return self.registry.add(playbook)

    def validate(
        self,
        ref: str,
        values: Mapping[str, Value] | None = None,
    ) -> ValidationReport:
        """Validate a playbook DAG and its variable values."""
        playbook = self.registry.get(ref)
        compilation = compile_dag(playbook)
        resolution = validate_values(playbook, values)
        issues = list(resolution.issues)
        for step in playbook.steps:
            if step.condition is not None and not step.condition.field:
                issues.append(
                    ValidationIssue("invalid_condition", "Condition field is required", step.id)
                )
        return ValidationReport(
            playbook_ref=playbook.ref,
            compilation=compilation,
            resolution=resolution,
            issues=tuple(issues),
        )

    def compile(self, ref: str) -> DagCompilation:
        """Compile a playbook's DAG."""
        return compile_dag(self.registry.get(ref))

    def connect(
        self,
        ref: str,
        *,
        source: str,
        target: str,
    ) -> tuple[PlaybookDefinition | None, ValidationIssue | None]:
        """Validate a drag-created connection without mutating the registry."""
        playbook = self.registry.get(ref)
        steps, problem = connect(playbook.steps, source=source, target=target)
        if problem is not None:
            return None, problem
        return replace(playbook, steps=steps, version=playbook.version + 1), None

    def dry_run(
        self,
        ref: str,
        values: Mapping[str, Value] | None = None,
    ) -> DryRunTrace:
        """Plan every mutation with a sink that refuses all writes."""
        playbook = self.registry.get(ref)
        report = self.validate(ref, values)
        if not report.ok:
            raise VariableResolutionError(
                "Playbook validation failed",
                path=report.issues[0].path if report.issues else "steps",
            )
        sink = TraceOnlySink()
        return self._execute_plan(playbook, report.resolution, sink, commit=False)

    def run(
        self,
        ref: str,
        values: Mapping[str, Value] | None = None,
        *,
        actor: str = "automation",
    ) -> RunRecord:
        """Execute a live run and persist its result in ``run_records``."""
        playbook = self.registry.get(ref)
        report = self.validate(ref, values)
        if not report.ok:
            raise VariableResolutionError("Playbook validation failed", path="playbook")
        sink = self.sink_factory()
        started = self.clock.now_timestamp()
        record = RunRecord(
            id=new_run_id(playbook, report.resolution.values, self.clock),
            playbook_ref=playbook.ref,
            status=RunStatus.PLANNED,
            mode=RunMode.LIVE,
            started_at=started,
            variables=self._safe_values(playbook, report.resolution),
            input_fingerprint=fingerprint_values(report.resolution.values),
        )
        self.runs.begin(record)
        try:
            trace = self._execute_plan(
                playbook, report.resolution, sink, commit=True, run_id=record.id, actor=actor
            )
        except AutomationError:
            self.runs.fail(record, finished_at=self.clock.now_timestamp())
            raise
        self._sinks[record.id] = sink
        self._traces[record.id] = trace
        return self.runs.finish(
            record,
            trace=trace.entries,
            digest=trace.digest,
            state_digest=trace.state_digest,
            finished_at=self.clock.now_timestamp(),
        )

    def replay(
        self,
        run_id: str,
        *,
        values: Mapping[str, Value] | None = None,
    ) -> ReplayResult:
        """Re-execute a stored run on a fresh sink and compare the traces."""
        record = self.runs.get(run_id)
        playbook = self.registry.get(record.playbook_ref)
        supplied = dict(record.variables)
        if values:
            supplied.update(values)
        report = self.validate(playbook.ref, supplied)
        if not report.ok:
            raise VariableResolutionError("Replay variables are invalid", path="variables")
        if fingerprint_values(report.resolution.values) != record.input_fingerprint:
            raise ReplayMismatchError(
                "Replay variable values do not match the original run", path="variables"
            )
        replay_trace = self._execute_plan(
            playbook,
            report.resolution,
            self.sink_factory(),
            commit=True,
            run_id=run_id,
            publish_events=False,
        )
        original = self._traces.get(run_id)
        if original is None:
            original = DryRunTrace(
                playbook_ref=record.playbook_ref,
                mode=record.mode,
                entries=record.trace,
                variables=record.variables,
                digest=record.trace_digest,
                input_fingerprint=record.input_fingerprint,
                state_digest=record.state_digest,
            )
        differences = diff_traces(original, replay_trace)
        deterministic = not differences and original.digest == replay_trace.digest
        return ReplayResult(
            original_id=run_id,
            replay_trace=replay_trace,
            differences=differences,
            deterministic=deterministic,
        )

    def rollback(self, run_id: str) -> RollbackReport:
        """Compensate a run and persist the rollback as a new run record."""
        record = self.runs.get(run_id)
        if run_id in self._rolled_back:
            raise RollbackError(f"Run is already rolled back: {run_id}", path="run_id")
        sink = self._sinks.get(run_id)
        if sink is None:
            raise RollbackError(f"No live sink is available for run: {run_id}", path="run_id")
        manager = RollbackManager(
            sink, bus=self.bus, clock=self.clock, sink_factory=self.sink_factory
        )
        report = manager.rollback(record, self._traces.get(run_id))
        self.runs.store.save(report.record)
        self._rolled_back.add(run_id)
        return report

    def occurrences(
        self,
        ref: str,
        after: float,
        before: float,
        *,
        limit: int = 20,
    ) -> tuple[float, ...]:
        """Expand a playbook's recurrence rule inside a window."""
        playbook = self.registry.get(ref)
        if playbook.recurrence is None:
            return ()
        return occurrences(playbook.recurrence, after, before, limit=limit)

    def get_run(self, run_id: str) -> RunRecord:
        """Load a persisted run."""
        return self.runs.get(run_id)

    def list_runs(
        self, *, playbook_ref: str | None = None, limit: int = 100
    ) -> tuple[RunRecord, ...]:
        """List persisted runs."""
        return self.runs.list(playbook_ref=playbook_ref, limit=limit)

    def _safe_values(
        self,
        playbook: PlaybookDefinition,
        resolution: VariableResolution,
    ) -> dict[str, Value]:
        """Mask secret values before they can reach a record."""
        return {
            key: "***" if key in resolution.secrets else value
            for key, value in resolution.values.items()
        }

    def _execute_plan(
        self,
        playbook: PlaybookDefinition,
        resolution: VariableResolution,
        sink: MutationSink,
        *,
        commit: bool,
        run_id: str = "",
        actor: str = "automation",
        publish_events: bool = True,
    ) -> DryRunTrace:
        """Walk the compiled order and record one trace entry per step."""
        compilation = compile_dag(playbook)
        compilation.raise_if_invalid()
        recorder = TraceRecorder()
        executor = StepExecutor(
            sink, bus=self.bus if publish_events else None, clock=self.clock, actor=actor
        )
        outputs: dict[str, Any] = {}
        safe_values = self._safe_values(playbook, resolution)
        for step_id in compilation.order:
            step: StepDefinition = playbook.step(step_id)
            outcome = executor.execute(
                step,
                playbook_ref=playbook.ref,
                resolution=resolution,
                outputs=outputs,
                run_id=run_id,
                commit=commit,
            )
            if outcome.ref:
                outputs[step.id] = {
                    "ref": outcome.ref,
                    "kind": step.kind.value,
                    "step_id": step.id,
                }
                if step.output:
                    outputs[step.output] = outcome.ref
            variables = dict(safe_values)
            variables["steps"] = outputs
            recorder.record(step, outcome, variables=variables)
        return recorder.finish(
            playbook_ref=playbook.ref,
            mode=RunMode.LIVE if commit else RunMode.DRY_RUN,
            variables=safe_values,
            input_fingerprint=fingerprint_values(resolution.values),
            state_digest=sink.entity_digest(),
        )


def trace_hash(trace: DryRunTrace) -> str:
    """Return a content hash of a trace for compact comparisons."""
    return digest([trace.digest, trace.input_fingerprint, trace.writes])
