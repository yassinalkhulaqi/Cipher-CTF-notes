"""Deterministic DAG compiler for playbook steps.

The compiler is pure: it never executes a step. It produces a stable topological
order, parallel layers, explicit cycle paths, and diagnostics that can be shown
directly in the DAG editor. All ordering uses sorted keys so two independent
runs of the compiler always produce byte-identical plans.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from heapq import heappop, heappush

from redscribe.v3.automation.errors import CycleDetectedError, PlaybookValidationError
from redscribe.v3.automation.types import PlaybookDefinition, StepDefinition, ValidationIssue


def dependency_graph(steps: Sequence[StepDefinition]) -> dict[str, tuple[str, ...]]:
    """Build a normalized adjacency map from step id to dependencies."""
    graph: dict[str, tuple[str, ...]] = {}
    for step in steps:
        unique = sorted({dependency for dependency in step.depends_on if dependency != step.id})
        graph[step.id] = tuple(unique)
    return graph


def detect_cycles(graph: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Return distinct cycles as closed node paths, in stable order."""
    color: dict[str, int] = {}
    stack: list[str] = []
    found: set[tuple[str, ...]] = set()
    cycles: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        color[node] = 1
        stack.append(node)
        for dependency in graph.get(node, ()):
            if dependency not in graph:
                continue
            state = color.get(dependency, 0)
            if state == 0:
                visit(dependency)
            elif state == 1:
                cycle = (*stack[stack.index(dependency) :], dependency)
                reversed_cycle = (cycle[0], *reversed(cycle[1:]))
                canonical = min(cycle, reversed_cycle)
                if canonical not in found:
                    found.add(canonical)
                    cycles.append(cycle)
        stack.pop()
        color[node] = 2

    for node in sorted(graph):
        if color.get(node, 0) == 0:
            visit(node)
    return tuple(sorted(cycles))


def topological_order(graph: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Return a stable Kahn topological ordering."""
    dependents: dict[str, list[str]] = {node: [] for node in graph}
    indegree: dict[str, int] = dict.fromkeys(graph, 0)
    for node, dependencies in graph.items():
        for dependency in dependencies:
            if dependency in indegree:
                dependents[dependency].append(node)
                indegree[node] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        node = heappop(queue)
        order.append(node)
        for dependent in dependents[node]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heappush(queue, dependent)
    if len(order) != len(graph):
        raise CycleDetectedError("Step graph contains a cycle", path="steps")
    return tuple(order)


def parallel_layers(graph: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Group independent steps into ordered execution layers."""
    remaining = dict(graph)
    layers: list[tuple[str, ...]] = []
    while remaining:
        ready = sorted(
            node
            for node, dependencies in remaining.items()
            if all(dependency not in remaining for dependency in dependencies)
        )
        if not ready:
            break
        layers.append(tuple(ready))
        for node in ready:
            remaining.pop(node, None)
    return tuple(layers)


def critical_path(steps: Sequence[StepDefinition], order: Sequence[str]) -> tuple[str, ...]:
    """Return the dependency chain with the most steps."""
    by_id = {step.id: step for step in steps}
    best: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    for node in order:
        dependencies = [
            dependency
            for dependency in by_id[node].depends_on
            if dependency in by_id and dependency != node
        ]
        if not dependencies:
            best[node] = 1
            parent[node] = None
            continue
        source = max(dependencies, key=lambda key: (best.get(key, 0), key))
        best[node] = best.get(source, 0) + 1
        parent[node] = source
    if not best:
        return ()
    end = max(best, key=lambda node: (best[node], node))
    result: list[str] = []
    cursor: str | None = end
    while cursor is not None and cursor not in result:
        result.append(cursor)
        cursor = parent.get(cursor)
    return tuple(reversed(result))


def connect(
    steps: Sequence[StepDefinition],
    *,
    source: str,
    target: str,
) -> tuple[tuple[StepDefinition, ...], ValidationIssue | None]:
    """Add a drag-created edge, rejecting cycles and self-links.

    Returns the new step tuple and an optional diagnostic. The caller applies
    the new tuple only when no diagnostic is produced, so a rejected drag never
    mutates editor state.
    """
    from dataclasses import replace

    if source == target:
        return (
            tuple(steps),
            ValidationIssue(
                code="self_dependency",
                message="A step cannot depend on itself",
                path=f"steps.{target}.depends_on",
            ),
        )
    ids = {step.id for step in steps}
    if source not in ids or target not in ids:
        return (
            tuple(steps),
            ValidationIssue(
                code="unknown_step",
                message="Both ends of a connection must be existing steps",
                path=f"steps.{target}.depends_on",
            ),
        )
    updated: list[StepDefinition] = []
    for step in steps:
        if step.id == target:
            dependencies = tuple(dict.fromkeys((*step.depends_on, source)))
            updated.append(replace(step, depends_on=dependencies))
        else:
            updated.append(step)
    graph = dependency_graph(updated)
    if detect_cycles(graph):
        return (
            tuple(steps),
            ValidationIssue(
                code="cycle_detected",
                message=f"Connecting {source} to {target} would create a cycle",
                path=f"steps.{target}.depends_on",
            ),
        )
    return tuple(updated), None


class DagCompilation:
    """A validated plan produced from a playbook's step graph."""

    __slots__ = (
        "critical",
        "cycles",
        "depth",
        "duplicates",
        "issues",
        "layers",
        "missing",
        "order",
        "self_dependencies",
    )

    def __init__(
        self,
        *,
        order: tuple[str, ...] = (),
        layers: tuple[tuple[str, ...], ...] = (),
        cycles: tuple[tuple[str, ...], ...] = (),
        duplicates: tuple[str, ...] = (),
        missing: tuple[str, ...] = (),
        self_dependencies: tuple[str, ...] = (),
        critical: tuple[str, ...] = (),
        issues: tuple[ValidationIssue, ...] = (),
        depth: dict[str, int] | None = None,
    ) -> None:
        self.order = order
        self.layers = layers
        self.cycles = cycles
        self.duplicates = duplicates
        self.missing = missing
        self.self_dependencies = self_dependencies
        self.critical = critical
        self.issues = issues
        self.depth = depth or {}

    @property
    def ok(self) -> bool:
        """Whether the graph is safe to execute."""
        return not self.issues and not self.cycles and not self.duplicates and not self.missing

    def raise_if_invalid(self) -> None:
        """Raise a validation error when the graph cannot be executed."""
        if not self.ok:
            raise PlaybookValidationError(
                "Playbook DAG is invalid",
                path=self.issues[0].path if self.issues else "steps",
            )

    def next_ready(
        self, completed: frozenset[str], graph: Mapping[str, tuple[str, ...]]
    ) -> tuple[str, ...]:
        """Return steps whose dependencies are satisfied and that are not done."""
        return tuple(
            node
            for node in self.order
            if node not in completed
            and all(dependency in completed for dependency in graph.get(node, ()))
        )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation for editors and API responses."""
        return {
            "order": list(self.order),
            "layers": [list(layer) for layer in self.layers],
            "cycles": [list(cycle) for cycle in self.cycles],
            "duplicates": list(self.duplicates),
            "missing": list(self.missing),
            "self_dependencies": list(self.self_dependencies),
            "critical_path": list(self.critical),
            "depth": dict(self.depth),
            "issues": [issue.as_dict() for issue in self.issues],
            "ok": self.ok,
        }


def compile_dag(playbook: PlaybookDefinition) -> DagCompilation:
    """Compile a playbook into a validated execution plan."""
    steps = list(playbook.steps)
    ids = [step.id for step in steps]
    counts: dict[str, int] = {}
    for step_id in ids:
        counts[step_id] = counts.get(step_id, 0) + 1
    duplicates = tuple(sorted(step_id for step_id, count in counts.items() if count > 1))
    known = set(ids)
    graph = dependency_graph(steps)
    missing = tuple(
        sorted(
            {
                dependency
                for dependencies in graph.values()
                for dependency in dependencies
                if dependency not in known
            }
        )
    )
    self_dependencies = tuple(sorted(step.id for step in steps if step.id in step.depends_on))
    cycles = detect_cycles(graph)
    issues: list[ValidationIssue] = []
    if duplicates:
        issues.append(
            ValidationIssue(
                "duplicate_step", f"Duplicate step ids: {', '.join(duplicates)}", "steps"
            )
        )
    if missing:
        issues.append(
            ValidationIssue(
                "missing_dependency",
                f"Unknown dependencies: {', '.join(missing)}",
                "steps.depends_on",
            )
        )
    if self_dependencies:
        issues.append(
            ValidationIssue(
                "self_dependency",
                f"Steps cannot depend on themselves: {', '.join(self_dependencies)}",
                "steps.depends_on",
            )
        )
    for cycle in cycles:
        issues.append(
            ValidationIssue(
                "cycle_detected",
                "Cycle: " + " -> ".join(cycle),
                "steps.depends_on",
            )
        )
    output_counts: dict[str, int] = {}
    for step in steps:
        if step.output:
            output_counts[step.output] = output_counts.get(step.output, 0) + 1
    repeated_outputs = sorted(name for name, count in output_counts.items() if count > 1)
    if repeated_outputs:
        issues.append(
            ValidationIssue(
                "duplicate_output",
                f"Output names must be unique: {', '.join(repeated_outputs)}",
                "steps.output",
            )
        )
    if not duplicates and not missing:
        order = topological_order(graph) if not cycles else ()
        layers = parallel_layers(graph) if not cycles else ()
        critical = critical_path(steps, order) if not cycles else ()
        depth: dict[str, int] = {}
        for node in order:
            dependencies = [dependency for dependency in graph[node] if dependency in depth]
            depth[node] = 1 + max((depth[dependency] for dependency in dependencies), default=0)
    else:
        order, layers, critical, depth = (), (), (), {}
    return DagCompilation(
        order=order,
        layers=layers,
        cycles=cycles,
        duplicates=duplicates,
        missing=missing,
        self_dependencies=self_dependencies,
        critical=critical,
        issues=tuple(issues),
        depth=depth,
    )
