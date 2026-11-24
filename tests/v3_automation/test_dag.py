"""DAG compilation, cycle detection and drag-connection validation."""

from __future__ import annotations

import pytest

from redscribe.v3.automation.dag import (
    compile_dag,
    connect,
    critical_path,
    dependency_graph,
    detect_cycles,
    parallel_layers,
    topological_order,
)
from redscribe.v3.automation.errors import CycleDetectedError, PlaybookValidationError
from redscribe.v3.automation.parsing import parse_playbook
from redscribe.v3.automation.types import StepDefinition

from .helpers import linear_steps, playbook_payload


def test_dependency_graph_normalizes_duplicates_and_self_links() -> None:
    steps = (
        StepDefinition(id="a", title="A", depends_on=("a", "b", "b")),
        StepDefinition(id="b", title="B"),
    )
    assert dependency_graph(steps) == {"a": ("b",), "b": ()}


def test_topological_order_is_stable() -> None:
    graph = {"c": ("a", "b"), "a": (), "b": ("a",), "d": ()}
    assert topological_order(graph) == ("a", "b", "c", "d")
    assert topological_order(graph) == topological_order(dict(reversed(list(graph.items()))))
    with pytest.raises(CycleDetectedError):
        topological_order({"a": ("b",), "b": ("a",)})


def test_cycle_detection_returns_closed_paths() -> None:
    cycles = detect_cycles({"a": ("b",), "b": ("c",), "c": ("a",), "d": ()})
    assert len(cycles) == 1
    assert cycles[0][0] == cycles[0][-1]
    assert set(cycles[0]) == {"a", "b", "c"}
    assert detect_cycles({"a": ("b",), "b": ()}) == ()
    assert detect_cycles({"a": ("missing",)}) == ()


def test_parallel_layers_and_critical_path() -> None:
    graph = {"a": (), "b": (), "c": ("a",), "d": ("b",)}
    assert parallel_layers(graph) == (("a", "b"), ("c", "d"))
    steps = linear_steps(5)
    order = topological_order(dependency_graph(steps))
    assert critical_path(steps, order) == tuple(f"s{index}" for index in range(5))
    assert critical_path((), ()) == ()


def test_compile_dag_happy_path() -> None:
    compilation = compile_dag(parse_playbook(playbook_payload()))
    assert compilation.ok is True
    assert compilation.order == ("note", "finding", "evidence", "event")
    assert compilation.depth == {"note": 1, "finding": 2, "evidence": 3, "event": 4}
    assert compilation.critical == compilation.order
    assert compilation.next_ready(
        frozenset({"note"}), dependency_graph(parse_playbook(playbook_payload()).steps)
    ) == ("finding",)
    assert compilation.as_dict()["ok"] is True
    compilation.raise_if_invalid()


def test_compile_dag_rejects_cycles_and_reports_path() -> None:
    payload = playbook_payload()
    payload["steps"][0]["depends_on"] = ["event"]
    compilation = compile_dag(parse_playbook(payload))
    assert compilation.ok is False
    assert compilation.cycles
    assert any(issue.code == "cycle_detected" for issue in compilation.issues)
    with pytest.raises(PlaybookValidationError):
        compilation.raise_if_invalid()


def test_compile_dag_reports_duplicates_and_missing_dependencies() -> None:
    payload = playbook_payload()
    payload["steps"][1]["id"] = "note"
    payload["steps"][1]["depends_on"] = ["ghost"]
    compilation = compile_dag(parse_playbook(payload))
    assert compilation.duplicates == ("note",)
    assert compilation.missing == ("finding", "ghost")
    assert compilation.ok is False
    assert compilation.order == ()


def test_self_dependency_is_reported() -> None:
    payload = playbook_payload()
    payload["steps"][0]["depends_on"] = ["note"]
    compilation = compile_dag(parse_playbook(payload))
    assert compilation.self_dependencies == ("note",)
    assert any(issue.code == "self_dependency" for issue in compilation.issues)


def test_duplicate_output_names_are_rejected() -> None:
    payload = playbook_payload()
    payload["steps"][0]["output"] = "shared"
    payload["steps"][1]["output"] = "shared"
    compilation = compile_dag(parse_playbook(payload))
    assert any(issue.code == "duplicate_output" for issue in compilation.issues)


def test_connect_accepts_valid_edge_and_rejects_cycle() -> None:
    steps = linear_steps(3)
    updated, problem = connect(steps, source="s0", target="s2")
    assert problem is None
    assert updated[2].depends_on == ("s1", "s0")
    assert steps[2].depends_on == ("s1",)

    rejected, problem = connect(steps, source="s2", target="s0")
    assert rejected == steps
    assert problem is not None
    assert problem.code == "cycle_detected"

    rejected, problem = connect(steps, source="s0", target="s0")
    assert rejected == steps
    assert problem is not None
    assert problem.code == "self_dependency"

    rejected, problem = connect(steps, source="ghost", target="s0")
    assert rejected == steps
    assert problem is not None
    assert problem.code == "unknown_step"


def test_large_dag_scales_and_remains_deterministic() -> None:
    steps = linear_steps(20)
    first = compile_dag(
        parse_playbook({"id": "big", "title": "Big", "steps": [step.as_dict() for step in steps]})
    )
    second = compile_dag(
        parse_playbook({"id": "big", "title": "Big", "steps": [step.as_dict() for step in steps]})
    )
    assert first.order == second.order
    assert len(first.order) == 20
    assert len(first.layers) == 20
    assert first.ok is True
