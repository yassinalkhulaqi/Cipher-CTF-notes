"""Domain services for declarative playbook automation.

The executor never touches the host: it walks a validated DAG in topological
order and records what *would* happen. Schedule evaluation and run lifecycle
are driven by injected clocks and id factories so every outcome is reproducible
in tests and safe to expose through the API.
"""

from __future__ import annotations

import calendar
import hashlib
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from redscribe.v4.automation_v4.storage import RunStore
from redscribe.v4.automation_v4.types import (
    DagNode,
    Frequency,
    IssueSeverity,
    PlaybookDag,
    RunRecord,
    RunStatus,
    Schedule,
    TraceStatus,
    TraceStep,
    ValidationIssue,
)
from redscribe.v4.clock import Clock
from redscribe.v4.contracts import EntityKind, new_entity_id
from redscribe.v4.events import DomainEvent, EventBus, EventKind


class DagValidationError(ValueError):
    """Raised when a graph cannot be safely planned."""

    def __init__(self, message: str, codes: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.codes = codes


class RunStateError(ValueError):
    """Raised when a lifecycle transition is not allowed."""


class ScheduleError(ValueError):
    """Raised when a schedule cannot be evaluated."""


class Color(str, Enum):
    WHITE = "white"
    GREY = "grey"
    BLACK = "black"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The complete, deterministic result of validating a playbook."""

    dag_id: str
    issues: tuple[ValidationIssue, ...]
    order: tuple[str, ...]
    layers: tuple[tuple[str, ...], ...]
    depth: dict[str, int] = field(default_factory=dict)
    cycles: tuple[tuple[str, ...], ...] = ()
    missing: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.severity.value == "error" for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity.value == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity.value == "warning")

    @property
    def critical_path(self) -> tuple[str, ...]:
        if not self.depth:
            return ()
        deepest = max(self.depth, key=lambda node: (self.depth[node], node))
        parents: dict[str, tuple[str, ...]] = {}
        for source, target in self.edges:
            parents[target] = tuple(sorted((*parents.get(target, ()), source)))
        chain: list[str] = []
        cursor: str | None = deepest
        while cursor is not None and cursor not in chain:
            chain.append(cursor)
            candidates = parents.get(cursor, ())
            cursor = (
                max(candidates, key=lambda node: (self.depth.get(node, 0), node))
                if candidates
                else None
            )
        return tuple(reversed(chain))

    def to_dict(self) -> dict[str, object]:
        return {
            "dag_id": self.dag_id,
            "ok": self.ok,
            "order": list(self.order),
            "layers": [list(layer) for layer in self.layers],
            "depth": dict(self.depth),
            "critical_path": list(self.critical_path),
            "cycles": [list(cycle) for cycle in self.cycles],
            "missing": list(self.missing),
            "duplicates": list(self.duplicates),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def summary(self) -> str:
        state = "valid" if self.ok else "invalid"
        return (
            f"{self.dag_id}: {state}, {len(self.order)} node(s), "
            f"{len(self.edges)} edge(s), {len(self.errors)} error(s)"
        )


class DagValidator:
    """Validate DAG shape and produce a deterministic execution plan."""

    def __init__(self, warn_isolated: bool = True) -> None:
        self.warn_isolated = warn_isolated

    def adjacency(self, dag: PlaybookDag) -> dict[str, tuple[str, ...]]:
        """Merge declared dependencies and explicit edges into an adjacency map."""
        ids = dag.node_ids
        known = set(ids)
        graph: dict[str, set[str]] = {node_id: set() for node_id in ids}
        for node in dag.nodes:
            for dependency in node.depends_on:
                if dependency in known and dependency != node.id:
                    graph[node.id].add(dependency)
        for edge in dag.edges:
            if edge.source in known and edge.target in known and edge.source != edge.target:
                graph[edge.target].add(edge.source)
        return {node_id: tuple(sorted(deps)) for node_id, deps in graph.items()}

    def validate(self, dag: PlaybookDag) -> ValidationReport:
        """Return issues, topological order, parallel layers and depths."""
        issues: list[ValidationIssue] = []
        ids = dag.node_ids
        counts = Counter(ids)
        duplicates = tuple(sorted(node_id for node_id, count in counts.items() if count > 1))
        if duplicates:
            issues.append(
                ValidationIssue(
                    "duplicate_node",
                    f"Duplicate node ids: {', '.join(duplicates)}",
                    "nodes",
                )
            )

        known = set(ids)
        missing = tuple(
            sorted(
                {
                    dependency
                    for node in dag.nodes
                    for dependency in node.depends_on
                    if dependency not in known
                }
            )
        )
        if missing:
            issues.append(
                ValidationIssue(
                    "missing_dependency",
                    f"Unknown dependencies: {', '.join(missing)}",
                    "nodes.depends_on",
                )
            )

        dangling = tuple(
            sorted({node_id for edge in dag.edges for node_id in edge.key if node_id not in known})
        )
        if dangling:
            issues.append(
                ValidationIssue(
                    "dangling_edge",
                    f"Edges reference unknown nodes: {', '.join(dangling)}",
                    "edges",
                )
            )

        self_loops = tuple(sorted(node.id for node in dag.nodes if node.id in node.depends_on))
        if self_loops:
            issues.append(
                ValidationIssue(
                    "self_dependency",
                    f"Self dependencies: {', '.join(self_loops)}",
                    "nodes.depends_on",
                )
            )

        graph = self.adjacency(dag)
        cycles = self.find_cycles(graph)
        for cycle in cycles:
            issues.append(
                ValidationIssue(
                    "cycle_detected",
                    f"Cycle detected: {' -> '.join((*cycle, cycle[0]))}",
                    "nodes.depends_on",
                )
            )

        if self.warn_isolated:
            isolated = tuple(
                sorted(
                    node_id
                    for node_id, deps in graph.items()
                    if not deps and not any(node_id in others for others in graph.values())
                )
            )
            if isolated:
                issues.append(
                    ValidationIssue(
                        "isolated_node",
                        f"Nodes without edges: {', '.join(isolated)}",
                        "nodes",
                        IssueSeverity.WARNING,
                    )
                )

        order = self.topological_sort(graph)
        layers = self.parallel_layers(graph)
        depth = self.depths(graph, order)
        edges = tuple(
            sorted(
                {(dependency, node_id) for node_id, deps in graph.items() for dependency in deps}
            )
        )
        return ValidationReport(
            dag_id=dag.id,
            issues=tuple(issues),
            order=order,
            layers=layers,
            depth=depth,
            cycles=cycles,
            missing=missing,
            duplicates=duplicates,
            edges=edges,
        )

    def require_valid(self, dag: PlaybookDag) -> ValidationReport:
        """Validate and raise a structured error for invalid graphs."""
        report = self.validate(dag)
        if not report.ok:
            raise DagValidationError(report.summary(), tuple(issue.code for issue in report.errors))
        return report

    def topological_sort(self, graph: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
        """Kahn's algorithm with lexicographic tie-breaking at every layer."""
        indegree = {node: len(deps) for node, deps in graph.items()}
        dependents: dict[str, list[str]] = {node: [] for node in graph}
        for node, deps in graph.items():
            for dependency in deps:
                if dependency in dependents:
                    dependents[dependency].append(node)
        ready = sorted(node for node, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for dependent in sorted(dependents[node]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort()
        if len(order) != len(graph):
            return ()
        return tuple(order)

    def parallel_layers(self, graph: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
        """Group nodes that can be evaluated in the same deterministic wave."""
        remaining = dict(graph)
        layers: list[tuple[str, ...]] = []
        while remaining:
            ready = tuple(
                sorted(
                    node
                    for node, deps in remaining.items()
                    if all(dependency not in remaining for dependency in deps)
                )
            )
            if not ready:
                break
            layers.append(ready)
            for node in ready:
                del remaining[node]
        return tuple(layers)

    def depths(
        self, graph: Mapping[str, tuple[str, ...]], order: tuple[str, ...]
    ) -> dict[str, int]:
        """Longest-path depth of each node, computed only for acyclic graphs."""
        result: dict[str, int] = {}
        for node in order:
            deps = [result[dep] for dep in graph[node] if dep in result]
            result[node] = 1 + max(deps) if deps else 0
        return result

    def find_cycles(self, graph: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
        """Return canonical, deduplicated cycles in sorted order."""
        colors = dict.fromkeys(graph, Color.WHITE)
        stack: list[str] = []
        found: set[tuple[str, ...]] = set()
        for start in sorted(graph):
            if colors[start] is Color.WHITE:
                self._visit(start, graph, colors, stack, found)
        return tuple(sorted(found))

    def _visit(
        self,
        node: str,
        graph: Mapping[str, tuple[str, ...]],
        colors: dict[str, Color],
        stack: list[str],
        found: set[tuple[str, ...]],
    ) -> None:
        colors[node] = Color.GREY
        stack.append(node)
        for dependency in graph.get(node, ()):
            state = colors.get(dependency, Color.WHITE)
            if state is Color.WHITE:
                self._visit(dependency, graph, colors, stack, found)
            elif state is Color.GREY:
                index = stack.index(dependency)
                cycle = tuple(stack[index:])
                reverse = (cycle[0], *tuple(reversed(cycle[1:])))
                found.add(min(cycle, reverse))
        stack.pop()
        colors[node] = Color.BLACK


@dataclass(frozen=True, slots=True)
class DryRunResult:
    """A complete simulated run with a content digest."""

    dag_id: str
    status: RunStatus
    trace: tuple[TraceStep, ...]
    digest: str
    waves: int

    @property
    def succeeded(self) -> bool:
        return self.status is RunStatus.SUCCEEDED

    @property
    def failed_nodes(self) -> tuple[str, ...]:
        return tuple(step.node_id for step in self.trace if step.status is TraceStatus.FAILED)

    @property
    def skipped_nodes(self) -> tuple[str, ...]:
        return tuple(step.node_id for step in self.trace if step.status is TraceStatus.SKIPPED)

    def to_dict(self) -> dict[str, object]:
        return {
            "dag_id": self.dag_id,
            "status": self.status.value,
            "trace": [step.to_dict() for step in self.trace],
            "digest": self.digest,
            "waves": self.waves,
        }


class DryRunExecutor:
    """Simulate playbook execution; no external effects are possible."""

    def __init__(self, validator: DagValidator | None = None) -> None:
        self.validator = validator or DagValidator()

    def duration_for(self, node: DagNode) -> int:
        """Derive a stable simulated duration from inert node data."""
        digest = hashlib.sha256(node.signature.encode("utf-8")).hexdigest()
        jitter = int(digest[:2], 16) % 9
        raw = node.params.get("delay_ms", "")
        explicit = int(raw) if raw.isdigit() else 0
        return node.kind.base_duration_ms + jitter + min(explicit, 5000)

    def plan(self, dag: PlaybookDag) -> tuple[str, ...]:
        report = self.validator.require_valid(dag)
        return report.order

    def execute(
        self,
        dag: PlaybookDag,
        fail_nodes: frozenset[str] = frozenset(),
    ) -> DryRunResult:
        """Walk the DAG in topological order and record simulated outcomes."""
        report = self.validator.require_valid(dag)
        nodes = dag.node_map()
        incoming: dict[str, list[str]] = {}
        for source, target in report.edges:
            incoming.setdefault(target, []).append(source)
        statuses: dict[str, TraceStatus] = {}
        trace: list[TraceStep] = []
        for node_id in report.order:
            node = nodes[node_id]
            blockers = tuple(
                dep
                for dep in incoming.get(node_id, ())
                if statuses.get(dep) is not TraceStatus.SUCCEEDED
            )
            if blockers:
                detail = "skipped: " + ", ".join(f"{dep} did not succeed" for dep in blockers)
                statuses[node_id] = TraceStatus.SKIPPED
                trace.append(TraceStep(node_id, TraceStatus.SKIPPED, detail, 0))
                continue
            should_fail = node_id in fail_nodes or node.params.get("simulate_failure") == "true"
            duration = self.duration_for(node)
            if should_fail:
                statuses[node_id] = TraceStatus.FAILED
                trace.append(
                    TraceStep(
                        node_id,
                        TraceStatus.FAILED,
                        f"simulated failure for {node.kind.value}",
                        duration,
                    )
                )
                continue
            statuses[node_id] = TraceStatus.SUCCEEDED
            trace.append(
                TraceStep(
                    node_id,
                    TraceStatus.SUCCEEDED,
                    f"{node.kind.label} simulated with {len(node.params)} parameter(s)",
                    duration,
                )
            )
        status = (
            RunStatus.FAILED
            if any(step.status is TraceStatus.FAILED for step in trace)
            else RunStatus.SUCCEEDED
        )
        digest = self.digest_of(trace)
        return DryRunResult(
            dag_id=dag.id,
            status=status,
            trace=tuple(trace),
            digest=digest,
            waves=len(report.layers),
        )

    @staticmethod
    def digest_of(steps: Iterable[TraceStep]) -> str:
        """Hash a trace in a canonical, order-sensitive way."""
        canonical = "|".join(
            f"{step.node_id}:{step.status.value}:{step.duration_ms}" for step in steps
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class ScheduleEvaluator:
    """Compute the next occurrence of a schedule from an injected clock."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    @staticmethod
    def _aware(moment: datetime) -> datetime:
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)

    @staticmethod
    def to_iso(moment: datetime) -> str:
        return (
            ScheduleEvaluator._aware(moment)
            .astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def parse(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as exc:
            raise ScheduleError(f"invalid timestamp: {value}") from exc

    def next_after(self, schedule: Schedule, moment: datetime | None = None) -> datetime:
        """Return the first occurrence strictly after ``moment`` (UTC)."""
        now = self._aware(moment or self.clock.now()).astimezone(timezone.utc)
        if schedule.frequency is Frequency.INTERVAL:
            return now + timedelta(minutes=schedule.interval_minutes)
        if schedule.frequency is Frequency.DAILY:
            candidate = now.replace(
                hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0
            )
            return candidate if candidate > now else candidate + timedelta(days=1)
        if schedule.frequency is Frequency.WEEKLY:
            weekdays = schedule.day_of_week or tuple(range(7))
            for offset in range(0, 8):
                day = (now.weekday() + offset) % 7
                candidate = (now + timedelta(days=offset)).replace(
                    hour=schedule.hour,
                    minute=schedule.minute,
                    second=0,
                    microsecond=0,
                )
                if day in weekdays and candidate > now:
                    return candidate
            raise ScheduleError("weekly schedule has no future occurrence")
        if schedule.frequency is Frequency.MONTHLY:
            for offset in range(0, 14):
                year = now.year + (now.month - 1 + offset) // 12
                month = (now.month - 1 + offset) % 12 + 1
                last = calendar.monthrange(year, month)[1]
                day = min(schedule.day_of_month, last)
                candidate = datetime(
                    year,
                    month,
                    day,
                    schedule.hour,
                    schedule.minute,
                    tzinfo=timezone.utc,
                )
                if candidate > now:
                    return candidate
            raise ScheduleError("monthly schedule has no future occurrence")
        raise ScheduleError(f"unsupported frequency: {schedule.frequency}")

    def refresh(self, schedule: Schedule, moment: datetime | None = None) -> Schedule:
        """Advance a schedule's ``next_run`` field."""
        if not schedule.enabled:
            return schedule
        return schedule.with_next_run(self.to_iso(self.next_after(schedule, moment)))

    def upcoming(
        self, schedule: Schedule, count: int = 3, moment: datetime | None = None
    ) -> tuple[str, ...]:
        """Preview the next ``count`` occurrences without mutating anything."""
        if count < 1:
            raise ScheduleError("count must be >= 1")
        cursor = self._aware(moment or self.clock.now())
        result: list[str] = []
        for _ in range(count):
            cursor = self.next_after(schedule, cursor)
            result.append(self.to_iso(cursor))
        return tuple(result)

    def due(self, schedule: Schedule, moment: datetime | None = None) -> bool:
        """Whether a schedule's declared next run has passed."""
        if not schedule.enabled or not schedule.next_run:
            return False
        reference = self._aware(moment or self.clock.now())
        return self.parse(schedule.next_run) <= reference

    def describe(self, schedule: Schedule) -> str:
        """Human-readable summary used by the API and UI."""
        if schedule.frequency is Frequency.INTERVAL:
            core = f"every {schedule.interval_minutes} minute(s)"
        elif schedule.frequency is Frequency.DAILY:
            core = f"daily at {schedule.hour:02d}:{schedule.minute:02d}"
        elif schedule.frequency is Frequency.WEEKLY:
            days = ",".join(str(day) for day in (schedule.day_of_week or tuple(range(7))))
            core = f"weekly on [{days}] at {schedule.hour:02d}:{schedule.minute:02d}"
        else:
            time = f"{schedule.hour:02d}:{schedule.minute:02d}"
            core = f"monthly on day {schedule.day_of_month} at {time}"
        state = "enabled" if schedule.enabled else "paused"
        return f"{core} ({state})"


class RunManager:
    """Coordinate run lifecycle, events and schedule precomputation."""

    def __init__(
        self,
        store: RunStore,
        bus: EventBus,
        executor: DryRunExecutor,
        evaluator: ScheduleEvaluator,
        clock: Clock,
        id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.store = store
        self.bus = bus
        self.executor = executor
        self.evaluator = evaluator
        self.clock = clock
        self.id_factory = id_factory

    def start(self, playbook_id: str, trigger: str = "manual") -> RunRecord:
        """Create and persist a running run, publishing RUN_STARTED."""
        if not playbook_id:
            raise RunStateError("playbook_id must not be empty")
        run = RunRecord(
            id=self.id_factory(),
            playbook_id=playbook_id,
            status=RunStatus.RUNNING,
            started_at=self.clock.iso(),
            trigger=trigger or "manual",
        )
        self.store.put(run)
        self.bus.publish(
            DomainEvent(
                kind=EventKind.RUN_STARTED,
                aggregate_id=run.id,
                aggregate_kind=EntityKind.RUN,
                occurred_at=run.started_at,
                payload={"playbook_id": playbook_id, "trigger": run.trigger},
            )
        )
        return run

    def dry_run(self, dag: PlaybookDag, fail_nodes: frozenset[str] = frozenset()) -> DryRunResult:
        """Execute a dry run against a playbook definition."""
        return self.executor.execute(dag, fail_nodes)

    def finish(self, run_id: str, result: DryRunResult) -> RunRecord:
        """Complete a run with a dry-run result, publishing RUN_FINISHED."""
        run = self.require(run_id)
        if run.status is not RunStatus.RUNNING:
            raise RunStateError(f"cannot finish {run.status.value} run: {run_id}")
        finished = run.with_status(result.status, self.clock.iso(), result.trace)
        self.store.put(finished)
        self.bus.publish(
            DomainEvent(
                kind=EventKind.RUN_FINISHED,
                aggregate_id=finished.id,
                aggregate_kind=EntityKind.RUN,
                occurred_at=finished.finished_at,
                payload={
                    "playbook_id": finished.playbook_id,
                    "status": finished.status.value,
                    "trace_digest": result.digest,
                    "steps": len(result.trace),
                },
            )
        )
        return finished

    def cancel(self, run_id: str) -> RunRecord:
        """Cancel a non-terminal run, publishing RUN_FINISHED."""
        run = self.require(run_id)
        if run.status.is_terminal:
            raise RunStateError(f"cannot cancel terminal run: {run_id}")
        cancelled = run.with_status(RunStatus.CANCELLED, self.clock.iso())
        self.store.put(cancelled)
        self.bus.publish(
            DomainEvent(
                kind=EventKind.RUN_FINISHED,
                aggregate_id=cancelled.id,
                aggregate_kind=EntityKind.RUN,
                occurred_at=cancelled.finished_at,
                payload={
                    "playbook_id": cancelled.playbook_id,
                    "status": RunStatus.CANCELLED.value,
                    "trace_digest": "",
                    "steps": 0,
                },
            )
        )
        return cancelled

    def get(self, run_id: str) -> RunRecord | None:
        return self.store.get(run_id)

    def require(self, run_id: str) -> RunRecord:
        run = self.store.get(run_id)
        if run is None:
            raise RunStateError(f"unknown run: {run_id}")
        return run

    def list_runs(
        self, playbook_id: str = "", status: RunStatus | None = None
    ) -> tuple[RunRecord, ...]:
        return self.store.history(playbook_id or None, status)

    def active(self) -> tuple[RunRecord, ...]:
        return self.store.by_status(RunStatus.RUNNING) + self.store.by_status(RunStatus.PENDING)

    def plan(self, schedule: Schedule, moment: datetime | None = None) -> Schedule:
        """Persist a schedule with a freshly computed next run."""
        advanced = self.evaluator.refresh(schedule, moment)
        self.store.put_schedule(advanced)
        return advanced

    def due_schedules(self, moment: datetime | None = None) -> tuple[Schedule, ...]:
        """Return enabled schedules whose next run is due."""
        reference = moment or self.clock.now()
        return tuple(
            schedule
            for schedule in self.store.all_schedules()
            if self.evaluator.due(schedule, reference)
        )
