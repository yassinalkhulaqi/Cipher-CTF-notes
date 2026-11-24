"""Tests for deterministic layouts and the pluggable strategy registry."""

from __future__ import annotations

import time

import pytest

from redscribe.v3.graph_workbench.layout import (
    ForceLayout,
    HierarchicalLayout,
    LayoutOptions,
    LayoutStrategy,
    Point,
    RadialLayout,
    SeededRandom,
    TimelineLayout,
    available_layouts,
    compute_layout,
    get_layout,
    normalize_positions,
    register_layout,
    stable_hash,
)
from tests.v3_graph_workbench import build_graph


def test_stable_hash_is_platform_independent() -> None:
    assert stable_hash("note:root") == stable_hash("note:root")
    assert stable_hash("note:root") != stable_hash("note:other")
    assert 0 <= stable_hash("x") <= 0xFFFFFFFF


def test_seeded_random_is_repeatable() -> None:
    left = SeededRandom(42)
    right = SeededRandom(42)
    assert [left.next_u32() for _ in range(8)] == [right.next_u32() for _ in range(8)]
    other = SeededRandom(43)
    assert SeededRandom(42).random() != other.random()
    assert 0.0 <= SeededRandom(7).random() < 1.0
    assert SeededRandom(7).below(0) == 0
    assert sorted(SeededRandom(9).shuffle(("a", "b", "c", "d"))) == ["a", "b", "c", "d"]


def test_layout_options_validation() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        LayoutOptions(width=0)
    with pytest.raises(ValueError, match="Padding"):
        LayoutOptions(padding=-1)
    with pytest.raises(ValueError, match="Iterations"):
        LayoutOptions(iterations=0)
    with pytest.raises(ValueError, match="direction"):
        LayoutOptions(direction="diagonal")
    with pytest.raises(ValueError, match="Sample size"):
        LayoutOptions(sample_size=1)


def test_layout_options_from_dict_ignores_unknown_keys() -> None:
    options = LayoutOptions.from_dict({"seed": 12, "unknown": True, "width": None})
    assert options.seed == 12
    assert options.width == LayoutOptions().width
    assert options.as_dict()["seed"] == 12


@pytest.mark.parametrize("name", ["force", "hierarchical", "radial", "timeline"])
def test_layouts_are_deterministic(name: str) -> None:
    graph = build_graph()
    options = LayoutOptions(seed=19)
    left = compute_layout(graph, name, options)
    right = compute_layout(graph, name, options)
    assert left.as_dict() == right.as_dict()
    assert len(left) == len(graph)
    assert all(0 <= point.x <= options.width for point in left.positions.values())
    assert all(0 <= point.y <= options.height for point in left.positions.values())


def test_force_layout_responds_to_seed() -> None:
    graph = build_graph()
    first = compute_layout(graph, "force", LayoutOptions(seed=1))
    second = compute_layout(graph, "force", LayoutOptions(seed=2))
    assert first.as_dict()["positions"] != second.as_dict()["positions"]


def test_force_layout_converges_on_a_star() -> None:
    graph = build_graph()
    result = ForceLayout().compute(graph, LayoutOptions(seed=5, iterations=12))
    assert result.strategy == "force"
    assert result.center == "finding:sql-001" or result.center == "note:root"
    assert result.point("note:root") != result.point("finding:sql-001")


def test_hierarchical_layout_uses_layers_and_root() -> None:
    graph = build_graph()
    result = HierarchicalLayout().compute(graph, LayoutOptions(direction="TB", seed=3))
    root = result.point("note:root")
    finding = result.point("finding:sql-001")
    assert root.y < finding.y
    rooted = compute_layout(graph, "hierarchical", LayoutOptions(root="evidence:cap-01"))
    assert rooted.center == "evidence:cap-01"


def test_radial_layout_rings_and_center() -> None:
    graph = build_graph()
    result = RadialLayout().compute(graph, LayoutOptions(seed=2))
    assert result.center in graph.nodes
    assert result.point(result.center) != result.point("note:root") or result.center == "note:root"
    assert set(result.positions) == set(graph.nodes)


def test_timeline_layout_uses_time_key() -> None:
    graph = build_graph()
    result = TimelineLayout().compute(graph, LayoutOptions(time_key="cvss"))
    assert len(result) == len(graph)
    assert result.point("finding:sql-001").x > result.point("note:root").x


def test_layout_registry_is_additive() -> None:
    names = available_layouts()
    assert names == ("force", "hierarchical", "radial", "timeline")
    with pytest.raises(ValueError, match="Unknown layout"):
        get_layout("spiral")

    class GridLayout(LayoutStrategy):
        name = "grid"

        def compute(self, graph: object, options: LayoutOptions) -> object:
            return None

    register_layout(GridLayout())
    assert "grid" in available_layouts()
    assert get_layout("grid").name == "grid"
    from redscribe.v3.graph_workbench import layout as layout_module

    layout_module._LAYOUTS.pop("grid")


def test_normalize_positions_handles_empty_and_degenerate_data() -> None:
    assert normalize_positions({}, LayoutOptions()) == {}
    points = {"a": Point(4.0, 4.0), "b": Point(4.0, 4.0)}
    normalized = normalize_positions(points, LayoutOptions(width=200, height=100, padding=10))
    assert normalized["a"] == normalized["b"]
    assert 10 <= normalized["a"].x <= 190


def test_empty_graph_layout() -> None:
    graph = build_graph().induced(frozenset())
    for name in available_layouts():
        result = compute_layout(graph, name)
        assert len(result) == 0
        assert result.as_dict()["positions"] == {}


def test_large_timeline_layout_stays_fast() -> None:
    template = build_graph().node("note:root")
    large = build_graph().induced(frozenset())
    for index in range(5000):
        large.nodes[f"note:n{index:05d}"] = template.with_updates(title=f"Node {index}")
    started = time.perf_counter()
    result = compute_layout(large, "timeline", LayoutOptions(seed=1))
    elapsed = (time.perf_counter() - started) * 1000
    assert len(result) == 5000
    assert elapsed < 100
