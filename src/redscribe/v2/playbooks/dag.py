"""Dependency graph algorithms for playbook steps."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from redscribe.v2.playbooks.errors import CycleDetectedError
from redscribe.v2.playbooks.types import PlaybookStep


@dataclass(frozen=True, slots=True)
class DagValidation:
    """A validated topological view of a step graph."""

    order: tuple[str, ...]
    layers: tuple[tuple[str, ...], ...]
    cycles: tuple[tuple[str, ...], ...]
    duplicates: tuple[str, ...]
    missing: tuple[str, ...]
    critical_path: tuple[str, ...]
    estimated_minutes: int

    @property
    def ok(self) -> bool:
        return not self.cycles and not self.duplicates and not self.missing

    def as_dict(self) -> dict[str, object]:
        return {
            "order": list(self.order),
            "layers": [list(layer) for layer in self.layers],
            "cycles": [list(cycle) for cycle in self.cycles],
            "duplicates": list(self.duplicates),
            "missing": list(self.missing),
            "critical_path": list(self.critical_path),
            "estimated_minutes": self.estimated_minutes,
            "ok": self.ok,
        }


def build_graph(steps: tuple[PlaybookStep, ...] | list[PlaybookStep]) -> dict[str, tuple[str, ...]]:
    """Return a deterministic adjacency map from step ids to dependencies."""
    graph: dict[str, tuple[str, ...]] = {}
    for step in steps:
        dependencies: list[str] = []
        for key in step.depends_on:
            if key not in dependencies:
                dependencies.append(key)
        graph[step.id] = tuple(sorted(dependencies))
    return graph


def validate_dag(steps: tuple[PlaybookStep, ...] | list[PlaybookStep]) -> DagValidation:
    """Validate a step graph and compute its execution layers."""
    items = list(steps)
    graph = build_graph(items)
    known = set(graph)
    seen: set[str] = set()
    duplicates: list[str] = []
    for step in items:
        if step.id in seen:
            duplicates.append(step.id)
        seen.add(step.id)
    missing = sorted(
        {dependency for dependencies in graph.values() for dependency in dependencies} - known
    )
    cycles = detect_cycles(graph)
    order: tuple[str, ...] = ()
    layers: tuple[tuple[str, ...], ...] = ()
    critical: tuple[str, ...] = ()
    minutes = sum(max(0, step.estimated_minutes) for step in items)
    if not cycles and not duplicates and not missing:
        order = topological_order(graph)
        layers = parallel_layers(graph)
        critical = critical_path(items, graph)
    return DagValidation(
        order=order,
        layers=layers,
        cycles=cycles,
        duplicates=tuple(sorted(set(duplicates))),
        missing=tuple(missing),
        critical_path=critical,
        estimated_minutes=minutes,
    )


def topological_order(graph: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Return a stable Kahn topological ordering of a graph."""
    dependents: dict[str, list[str]] = {node: [] for node in graph}
    indegree: dict[str, int] = dict.fromkeys(graph, 0)
    for node, dependencies in graph.items():
        for dependency in dependencies:
            if dependency in indegree:
                dependents[dependency].append(node)
                indegree[node] += 1
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in sorted(dependents.get(node, [])):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(order) != len(graph):
        raise CycleDetectedError("Step graph contains a cycle")
    return tuple(order)


def detect_cycles(graph: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Return distinct cycles as closed node paths."""
    color: dict[str, int] = {}
    stack: list[str] = []
    cycles: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

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
                canonical = _canonical(cycle)
                if canonical not in seen:
                    seen.add(canonical)
                    cycles.append(cycle)
        stack.pop()
        color[node] = 2

    for node in sorted(graph):
        if color.get(node, 0) == 0:
            visit(node)
    return tuple(cycles)


def parallel_layers(graph: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Group independent nodes into ordered execution layers."""
    remaining = dict(graph)
    layers: list[tuple[str, ...]] = []
    while remaining:
        ready = sorted(
            node
            for node, dependencies in remaining.items()
            if all(dep not in remaining for dep in dependencies)
        )
        if not ready:
            break
        layers.append(tuple(ready))
        for node in ready:
            remaining.pop(node, None)
    return tuple(layers)


def critical_path(
    steps: tuple[PlaybookStep, ...] | list[PlaybookStep],
    graph: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Return the longest duration path through the graph."""
    durations = {step.id: max(0, step.estimated_minutes) for step in steps}
    best: dict[str, int] = {}
    previous: dict[str, str | None] = {}
    for node in topological_order(graph):
        dependencies = [dep for dep in graph.get(node, ()) if dep in graph]
        if not dependencies:
            best[node] = durations.get(node, 0)
            previous[node] = None
            continue
        parent = max(dependencies, key=lambda dep: (best.get(dep, 0), dep))
        best[node] = best.get(parent, 0) + durations.get(node, 0)
        previous[node] = parent
    if not best:
        return ()
    end = max(best, key=lambda node: (best[node], node))
    path: list[str] = []
    cursor: str | None = end
    while cursor is not None and cursor not in path:
        path.append(cursor)
        cursor = previous.get(cursor)
    return tuple(reversed(path))


def ancestors(graph: dict[str, tuple[str, ...]], node: str) -> tuple[str, ...]:
    """Return every transitive dependency of a node."""
    found: set[str] = set()
    pending = list(graph.get(node, ()))
    while pending:
        current = pending.pop()
        if current in found or current not in graph:
            continue
        found.add(current)
        pending.extend(graph[current])
    return tuple(sorted(found))


def descendants(graph: dict[str, tuple[str, ...]], node: str) -> tuple[str, ...]:
    """Return every node that transitively depends on the given node."""
    found: set[str] = set()
    pending = [child for child, dependencies in graph.items() if node in dependencies]
    while pending:
        current = pending.pop()
        if current in found or current not in graph:
            continue
        found.add(current)
        pending.extend(child for child, dependencies in graph.items() if current in dependencies)
    return tuple(sorted(found))


def ready_steps(
    graph: dict[str, tuple[str, ...]],
    statuses: dict[str, object],
    *,
    done_status: str = "done",
    skip_status: str = "skipped",
) -> tuple[str, ...]:
    """Return unfinished nodes whose dependencies are satisfied."""
    settled = {done_status, skip_status}
    ready: list[str] = []
    for node, dependencies in graph.items():
        status = str(statuses.get(node, "pending"))
        if status in settled:
            continue
        if all(
            str(statuses.get(dep, "pending")) in settled for dep in dependencies if dep in graph
        ):
            ready.append(node)
    return tuple(sorted(ready))


def _canonical(cycle: tuple[str, ...]) -> tuple[str, ...]:
    inner = list(cycle[:-1])
    variants: list[tuple[str, ...]] = []
    for values in (inner, list(reversed(inner))):
        for index in range(len(values)):
            variants.append(tuple(values[index:] + values[:index]))
    return min(variants) if variants else cycle
