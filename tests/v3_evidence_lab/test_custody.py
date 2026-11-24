"""Tests for chain-of-custody graph construction and cycle handling."""

from __future__ import annotations

import pytest

from redscribe.v3.entities import EntityKind, EntityLink, LinkKind
from redscribe.v3.evidence_lab.custody import (
    CustodyStep,
    build_custody_graph,
    custody_domain_events,
    custody_links,
    custody_summary,
    detect_cycles,
    steps_from_records,
    subgraph,
    topological_order,
)
from redscribe.v3.evidence_lab.errors import CustodyCycleError, InvalidInputError


def make_steps(count: int = 3) -> tuple[CustodyStep, ...]:
    actions = ("acquired", "analyzed", "verified", "sealed")
    return tuple(
        CustodyStep(
            evidence_id=f"item-{index}",
            action=actions[index % len(actions)],
            actor=f"analyst-{index}",
            timestamp=f"2026-01-0{index + 1}T12:00:00Z",
            description=f"step {index}",
            event_hash=f"{index:064x}",
            previous_hash=f"{(index - 1) % 8:064x}",
            sequence=index + 1,
        )
        for index in range(count)
    )


def test_step_construction_and_records() -> None:
    step = CustodyStep("asset", "acquired", sequence=2)
    assert step.key == "evidence:asset#2"
    assert step.day == "unknown"
    records = (
        {"evidence_id": "a", "action": "acquired", "sequence": 2, "metadata": {"tool": "xxd"}},
        {"evidence_id": "b", "action": "analyzed", "sequence": 1},
    )
    steps = steps_from_records(records)
    assert [step.sequence for step in steps] == [1, 2]
    assert steps[1].metadata == {"tool": "xxd"}
    with pytest.raises(InvalidInputError):
        CustodyStep("", "acquired")
    with pytest.raises(InvalidInputError):
        CustodyStep("a", "", sequence=-1)


def test_build_graph_structure() -> None:
    graph = build_custody_graph(make_steps(), root="item-0")
    assert graph.root == "evidence:item-0"
    assert graph.cycle_free is True
    assert graph.verified is True
    assert len(graph.nodes) >= 7
    assert len(graph.edges) >= 6
    assert graph.depth >= 3
    assert graph.problems == ()
    root_node = next(node for node in graph.nodes if node.key == graph.root)
    assert root_node.as_dict()["kind"] == "evidence"


def test_graph_timeline_grouping() -> None:
    graph = build_custody_graph(make_steps(2), root="item-0")
    assert len(graph.timeline) == 2
    assert graph.timeline[0]["date"] == "2026-01-01"
    assert graph.timeline[0]["events"][0]["action"] == "acquired"
    assert "hash" in graph.timeline[0]["events"][0]


def test_graph_edges_are_b00_links() -> None:
    graph = build_custody_graph(make_steps(2), root="item-0")
    links = custody_links(graph)
    assert links
    assert all(isinstance(link, EntityLink) for link in links)
    assert any(link.kind is LinkKind.DERIVES for link in links)
    assert any(link.kind is LinkKind.RELATES for link in links)
    assert all(
        link.target.kind is EntityKind.EVIDENCE for link in links if link.kind is LinkKind.DERIVES
    )


def test_graph_domain_events_use_b00_contracts() -> None:
    graph = build_custody_graph(make_steps(2), root="item-0")
    events = custody_domain_events(graph)
    assert len(events) == len(graph.edges)
    assert all(event.subject is not None for event in events)
    assert events[0].kind == "evidence.custody.link"
    assert "link_kind" in events[0].payload


def test_topological_order_and_subgraph() -> None:
    graph = build_custody_graph(make_steps(3), root="item-0")
    order = topological_order(graph)
    assert len(order) == len(graph.nodes)
    assert order[0] == graph.root
    child = graph.edges[0].target
    part = subgraph(graph, child)
    assert part.root == child
    assert child in part.node_keys
    assert graph.root not in part.node_keys


def test_cycle_detection() -> None:
    from dataclasses import replace

    from redscribe.v3.evidence_lab.types import CustodyEdge

    graph = build_custody_graph(make_steps(1), root="item-0", include_actors=False)
    a, b = graph.node_keys[:2]
    cyclic = replace(
        graph,
        edges=(
            CustodyEdge(a, b, LinkKind.DERIVES),
            CustodyEdge(b, a, LinkKind.DERIVES),
        ),
    )
    cycles = detect_cycles(cyclic)
    assert cycles
    assert cycles[0][0] == cycles[0][-1]
    with pytest.raises(CustodyCycleError):
        topological_order(cyclic)


def test_custody_summary() -> None:
    graph = build_custody_graph(make_steps(3), root="item-0")
    summary = custody_summary(graph)
    assert summary["root"] == "evidence:item-0"
    assert summary["nodes"] == len(graph.nodes)
    assert summary["verified"] is True
    assert "acquired" in summary["actions"]


def test_graph_requires_root() -> None:
    with pytest.raises(InvalidInputError):
        build_custody_graph(make_steps(1), root="")
