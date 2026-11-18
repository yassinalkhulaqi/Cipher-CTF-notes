from __future__ import annotations

import pytest

from redscribe.v2.playbooks.dag import (
    ancestors,
    build_graph,
    critical_path,
    descendants,
    detect_cycles,
    parallel_layers,
    ready_steps,
    topological_order,
    validate_dag,
)
from redscribe.v2.playbooks.errors import CycleDetectedError
from redscribe.v2.playbooks.types import PlaybookStep


def _step(step_id: str, *dependencies: str, minutes: int = 0) -> PlaybookStep:
    return PlaybookStep(
        id=step_id,
        title=step_id.title(),
        depends_on=dependencies,
        estimated_minutes=minutes,
    )


def test_build_graph_sorts_and_deduplicates_dependencies() -> None:
    steps = [_step("b", "c", "a", "a"), _step("a"), _step("c")]

    assert build_graph(steps) == {"b": ("a", "c"), "a": (), "c": ()}


def test_validate_dag_returns_stable_order_and_layers(steps: tuple[PlaybookStep, ...]) -> None:
    result = validate_dag(steps)

    assert result.ok
    assert result.order == ("a", "b", "c")
    assert result.layers == (("a",), ("b",), ("c",))
    assert result.critical_path == ("a", "b", "c")
    assert result.estimated_minutes == 18
    assert result.as_dict()["ok"] is True


def test_validate_dag_detects_cycles() -> None:
    result = validate_dag([_step("a", "b"), _step("b", "a")])

    assert not result.ok
    assert result.cycles
    assert result.order == ()
    assert result.layers == ()


def test_validate_dag_detects_duplicate_ids() -> None:
    result = validate_dag([_step("a"), _step("a")])

    assert result.duplicates == ("a",)
    assert not result.ok


def test_validate_dag_detects_missing_dependencies() -> None:
    result = validate_dag([_step("a", "missing")])

    assert result.missing == ("missing",)
    assert not result.ok


def test_topological_order_is_stable_for_independent_nodes() -> None:
    graph = {"c": (), "a": (), "b": ()}

    assert topological_order(graph) == ("a", "b", "c")


def test_topological_order_raises_for_cycle() -> None:
    with pytest.raises(CycleDetectedError):
        topological_order({"a": ("b",), "b": ("a",)})


def test_detect_cycles_returns_closed_paths() -> None:
    cycles = detect_cycles({"a": ("b",), "b": ("c",), "c": ("a",), "d": ()})

    assert len(cycles) == 1
    assert cycles[0][0] == cycles[0][-1]
    assert set(cycles[0]) == {"a", "b", "c"}


def test_detect_cycles_ignores_missing_dependencies() -> None:
    assert detect_cycles({"a": ("missing",)}) == ()


def test_parallel_layers_groups_independent_nodes() -> None:
    graph = {"a": (), "b": (), "c": ("a",), "d": ("b",), "e": ("c", "d")}

    assert parallel_layers(graph) == (("a", "b"), ("c", "d"), ("e",))


def test_parallel_layers_stops_on_cycle() -> None:
    assert parallel_layers({"a": ("b",), "b": ("a",)}) == ()


def test_critical_path_prefers_longest_dependency_chain() -> None:
    steps = [
        _step("a", minutes=2),
        _step("b", minutes=10),
        _step("c", "a", minutes=3),
        _step("d", "b", minutes=1),
    ]
    graph = build_graph(steps)

    assert critical_path(steps, graph) == ("b", "d")


def test_critical_path_handles_empty_graph() -> None:
    assert critical_path([], {}) == ()


def test_ancestors_returns_transitive_dependencies() -> None:
    graph = {"a": (), "b": ("a",), "c": ("b",), "d": ()}

    assert ancestors(graph, "c") == ("a", "b")
    assert ancestors(graph, "a") == ()


def test_descendants_returns_transitive_dependents() -> None:
    graph = {"a": (), "b": ("a",), "c": ("b",), "d": ()}

    assert descendants(graph, "a") == ("b", "c")
    assert descendants(graph, "c") == ()


def test_ready_steps_respects_settled_dependencies() -> None:
    graph = {"a": (), "b": ("a",), "c": ("a",), "d": ("b",)}
    statuses = {"a": "done", "b": "pending", "c": "skipped", "d": "pending"}

    assert ready_steps(graph, statuses) == ("b",)


def test_ready_steps_custom_settled_statuses() -> None:
    graph = {"a": (), "b": ("a",)}

    assert ready_steps(graph, {"a": "complete"}, done_status="complete") == ("b",)


def test_ready_steps_treats_unknown_dependencies_as_satisfied() -> None:
    graph = {"a": ("missing",)}

    assert ready_steps(graph, {}) == ("a",)
