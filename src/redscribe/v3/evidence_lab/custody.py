"""Chain-of-custody graph construction over B00 entity contracts.

The builder converts an ordered list of custody steps into a typed graph whose
vertices are :class:`EntityRef` values and whose edges are B00
:class:`EntityLink` kinds. It detects cycles, computes depths, and emits domain
events through the shared event vocabulary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.entities import (
    EntityId,
    EntityKind,
    EntityLink,
    EntityRef,
    LinkKind,
    slugify,
)
from redscribe.v3.events import DomainEvent, make_event
from redscribe.v3.evidence_lab.errors import CustodyCycleError, InvalidInputError
from redscribe.v3.evidence_lab.types import CustodyEdge, CustodyGraph, CustodyNode

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class CustodyStep:
    """One append-only custody observation supplied by the caller."""

    evidence_id: str
    action: str
    actor: str = ""
    timestamp: str = ""
    description: str = ""
    event_hash: str = GENESIS_HASH
    previous_hash: str = GENESIS_HASH
    parent_id: str = ""
    sequence: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise InvalidInputError("Custody step requires an evidence id")
        if not self.action.strip():
            raise InvalidInputError("Custody step requires an action")
        if self.sequence < 0:
            raise InvalidInputError("Custody sequence cannot be negative")

    @property
    def key(self) -> str:
        """Stable step key."""
        return f"evidence:{self.evidence_id}#{self.sequence}"

    @property
    def day(self) -> str:
        """Day used for timeline grouping."""
        return self.timestamp[:10] or "unknown"


def steps_from_records(records: Iterable[Mapping[str, Any]]) -> tuple[CustodyStep, ...]:
    """Convert JSON-like custody records into typed steps."""
    steps: list[CustodyStep] = []
    for index, record in enumerate(records):
        steps.append(
            CustodyStep(
                evidence_id=str(record.get("evidence_id", "")),
                action=str(record.get("action", "")),
                actor=str(record.get("actor", "")),
                timestamp=str(record.get("timestamp", "")),
                description=str(record.get("description", "")),
                event_hash=str(record.get("event_hash", GENESIS_HASH)),
                previous_hash=str(record.get("previous_hash", GENESIS_HASH)),
                parent_id=str(record.get("parent_id", "")),
                sequence=int(record.get("sequence", index + 1)),
                metadata=dict(record.get("metadata", {})),
            )
        )
    return tuple(sorted(steps, key=lambda step: step.sequence))


def _evidence_node(value: str, label: str, *, sequence: int = 0) -> CustodyNode:
    """Build an evidence-kind node for an item or a step."""
    suffix = "" if sequence == 0 else f"#{sequence}"
    ref = EntityRef.of(EntityKind.EVIDENCE, f"{value}{suffix}", label)
    return CustodyNode(ref=ref, label=label or value)


def _actor_node(actor: str) -> CustodyNode | None:
    """Build an activity-kind node for a custody actor."""
    clean = actor.strip()
    if not clean:
        return None
    ref = EntityRef.of(EntityKind.ACTIVITY, f"actor-{slugify(clean)}", clean)
    return CustodyNode(ref=ref, label=clean)


def build_custody_graph(
    steps: Sequence[CustodyStep],
    *,
    root: str,
    include_actors: bool = True,
) -> CustodyGraph:
    """Build a typed custody graph and annotate node depths."""
    if not root.strip():
        raise InvalidInputError("Custody graph requires a root evidence id")
    ordered = tuple(sorted(steps, key=lambda step: step.sequence))
    nodes: dict[str, CustodyNode] = {}
    root_node = _evidence_node(root, root)
    nodes[root_node.key] = root_node
    edges: list[CustodyEdge] = []
    timeline_entries: list[dict[str, Any]] = []
    previous_key = root_node.key
    for step in ordered:
        node = _evidence_node(
            step.evidence_id, step.description or step.evidence_id, sequence=step.sequence
        )
        node = CustodyNode(
            ref=node.ref,
            label=node.label,
            action=step.action,
            timestamp=step.timestamp,
            terminal=False,
        )
        nodes[node.key] = node
        edges.append(
            CustodyEdge(
                source=previous_key,
                target=node.key,
                kind=LinkKind.DERIVES,
                label=step.action,
                timestamp=step.timestamp,
                sequence=step.sequence,
            )
        )
        if include_actors:
            actor_node = _actor_node(step.actor)
            if actor_node is not None:
                nodes.setdefault(actor_node.key, actor_node)
                edges.append(
                    CustodyEdge(
                        source=actor_node.key,
                        target=node.key,
                        kind=LinkKind.RELATES,
                        label="actor",
                        timestamp=step.timestamp,
                        sequence=step.sequence,
                    )
                )
        if step.parent_id:
            parent = _evidence_node(step.parent_id, step.parent_id)
            nodes.setdefault(parent.key, parent)
            edges.append(
                CustodyEdge(
                    source=parent.key,
                    target=node.key,
                    kind=LinkKind.DERIVES,
                    label="derived_from",
                    timestamp=step.timestamp,
                    sequence=step.sequence,
                )
            )
        timeline_entries.append(
            {
                "date": step.day,
                "sequence": step.sequence,
                "action": step.action,
                "actor": step.actor,
                "description": step.description,
                "timestamp": step.timestamp,
                "hash": step.event_hash,
                "previous_hash": step.previous_hash,
                "node": node.key,
            }
        )
        previous_key = node.key
    if previous_key in nodes:
        last = nodes[previous_key]
        nodes[previous_key] = CustodyNode(
            ref=last.ref,
            label=last.label,
            action=last.action,
            timestamp=last.timestamp,
            depth=last.depth,
            terminal=True,
        )
    annotated = _annotate_depths(nodes, edges, root_node.key)
    graph = CustodyGraph(
        root=root_node.key,
        nodes=tuple(annotated[key] for key in sorted(annotated)),
        edges=tuple(edges),
        timeline=tuple(_group_timeline(timeline_entries)),
    )
    problems = validate_graph(graph)
    return CustodyGraph(
        root=graph.root,
        nodes=graph.nodes,
        edges=graph.edges,
        timeline=graph.timeline,
        problems=problems,
        cycle_free=not detect_cycles(graph),
    )


def _group_timeline(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group timeline entries by calendar day."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(str(entry["date"]), []).append(
            {key: value for key, value in entry.items() if key != "date"}
        )
    return [{"date": day, "events": items} for day, items in sorted(groups.items())]


def _adjacency(graph: CustodyGraph) -> dict[str, list[str]]:
    """Build an adjacency list from graph edges."""
    adjacency: dict[str, list[str]] = {key: [] for key in graph.node_keys}
    for edge in graph.edges:
        if edge.source in adjacency:
            adjacency[edge.source].append(edge.target)
    return adjacency


def detect_cycles(graph: CustodyGraph) -> tuple[tuple[str, ...], ...]:
    """Return every directed cycle found by depth-first search."""
    adjacency = _adjacency(graph)
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    cycles: list[tuple[str, ...]] = []

    def walk(node: str) -> None:
        visiting.add(node)
        stack.append(node)
        for neighbour in adjacency.get(node, ()):
            if neighbour in visiting:
                start = stack.index(neighbour)
                cycles.append((*stack[start:], neighbour))
            elif neighbour not in visited:
                walk(neighbour)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(adjacency):
        if node not in visited:
            walk(node)
    return tuple(cycles)


def topological_order(graph: CustodyGraph) -> tuple[str, ...]:
    """Return a stable topological order or raise on a cycle."""
    cycles = detect_cycles(graph)
    if cycles:
        raise CustodyCycleError("Custody graph contains a cycle", context={"cycles": cycles})
    adjacency = _adjacency(graph)
    indegree = dict.fromkeys(adjacency, 0)
    for targets in adjacency.values():
        for target in targets:
            indegree[target] = indegree.get(target, 0) + 1
    ready = sorted(
        (key for key, degree in indegree.items() if degree == 0),
        key=lambda key: (key != graph.root, key),
    )
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for target in adjacency.get(node, ()):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
        ready.sort()
    return tuple(order)


def _annotate_depths(
    nodes: dict[str, CustodyNode],
    edges: Sequence[CustodyEdge],
    root: str,
) -> dict[str, CustodyNode]:
    """Annotate nodes with their longest distance from the root."""
    adjacency: dict[str, list[str]] = {key: [] for key in nodes}
    for edge in edges:
        if edge.source in adjacency:
            adjacency[edge.source].append(edge.target)
    distances = dict.fromkeys(nodes, -1)
    distances[root] = 0
    queue = [root]
    while queue:
        current = queue.pop(0)
        for target in adjacency.get(current, ()):
            candidate = distances[current] + 1
            if candidate > distances.get(target, -1):
                distances[target] = candidate
                queue.append(target)
    result: dict[str, CustodyNode] = {}
    for key, node in nodes.items():
        depth = max(0, distances[key])
        result[key] = CustodyNode(
            ref=node.ref,
            label=node.label,
            action=node.action,
            timestamp=node.timestamp,
            depth=depth,
            terminal=node.terminal,
        )
    return result


def validate_graph(graph: CustodyGraph) -> tuple[str, ...]:
    """Return structural validation problems for a custody graph."""
    problems: list[str] = []
    for cycle in detect_cycles(graph):
        problems.append(f"Cycle detected: {' -> '.join(cycle)}")
    if graph.root not in graph.node_keys:
        problems.append("Root node is missing from the graph")
    for edge in graph.edges:
        if edge.source not in graph.node_keys:
            problems.append(f"Edge source is unknown: {edge.source}")
        if edge.target not in graph.node_keys:
            problems.append(f"Edge target is unknown: {edge.target}")
    return tuple(problems)


def custody_links(graph: CustodyGraph) -> tuple[EntityLink, ...]:
    """Project the graph onto B00 entity links."""
    links: list[EntityLink] = []
    for edge in graph.edges:
        try:
            source = EntityId.parse(edge.source)
            target = EntityId.parse(edge.target)
        except ValueError:
            continue
        links.append(
            EntityLink(
                source=source,
                target=target,
                kind=edge.kind,
                label=edge.label,
                metadata={"timestamp": edge.timestamp, "sequence": edge.sequence},
            )
        )
    return tuple(links)


def custody_domain_events(graph: CustodyGraph) -> tuple[DomainEvent, ...]:
    """Emit B00 domain events for each custody edge."""
    events: list[DomainEvent] = []
    for edge in graph.edges:
        try:
            subject = EntityId.parse(edge.target)
        except ValueError:
            continue
        events.append(
            make_event(
                "evidence.custody.link",
                subject,
                source=edge.source,
                link_kind=edge.kind.value,
                sequence=edge.sequence,
                timestamp=edge.timestamp,
            )
        )
    return tuple(events)


def subgraph(graph: CustodyGraph, root: str) -> CustodyGraph:
    """Return the descendant subgraph rooted at a node."""
    adjacency = _adjacency(graph)
    reachable = {root}
    queue = [root]
    while queue:
        current = queue.pop(0)
        for target in adjacency.get(current, ()):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    nodes = tuple(node for node in graph.nodes if node.key in reachable)
    edges = tuple(
        edge for edge in graph.edges if edge.source in reachable and edge.target in reachable
    )
    return CustodyGraph(
        root=root,
        nodes=nodes,
        edges=edges,
        timeline=graph.timeline,
        problems=graph.problems,
        cycle_free=graph.cycle_free,
    )


def custody_summary(graph: CustodyGraph) -> dict[str, object]:
    """Return a compact summary for the custody timeline header."""
    actions = sorted({node.action for node in graph.nodes if node.action})
    actors = sorted({edge.label for edge in graph.edges if edge.label == "actor"})
    return {
        "root": graph.root,
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "depth": graph.depth,
        "actions": actions,
        "actors": actors,
        "verified": graph.verified,
    }
