"""Graph algorithms used by the V2 graph-intelligence services."""

from __future__ import annotations

import heapq
import itertools
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

from redscribe.v2.graph.model import EDGE_KINDS, GraphModel

WeightMap = dict[int, dict[int, float]]


@dataclass(frozen=True, slots=True)
class Component:
    """One connected group of vertices."""

    index: int
    node_ids: tuple[int, ...]
    labels: tuple[str, ...]
    size: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "index": self.index,
            "node_ids": list(self.node_ids),
            "labels": list(self.labels),
            "size": self.size,
        }


@dataclass(frozen=True, slots=True)
class CentralityScore:
    """One vertex's score for a centrality measure."""

    node_id: int
    label: str
    score: float
    measure: str
    rank: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "node_id": self.node_id,
            "label": self.label,
            "score": self.score,
            "measure": self.measure,
            "rank": self.rank,
        }


@dataclass(frozen=True, slots=True)
class ClusteringScore:
    """Local and neighborhood clustering statistics for a vertex."""

    node_id: int
    label: str
    coefficient: float
    degree: int
    triangles: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "node_id": self.node_id,
            "label": self.label,
            "coefficient": self.coefficient,
            "degree": self.degree,
            "triangles": self.triangles,
        }


@dataclass(frozen=True, slots=True)
class GraphPath:
    """A path between two vertices with its cost and edge identities."""

    node_ids: tuple[int, ...]
    labels: tuple[str, ...]
    edge_keys: tuple[tuple[int, int, str], ...]
    cost: float
    hops: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "node_ids": list(self.node_ids),
            "labels": list(self.labels),
            "edges": [list(key) for key in self.edge_keys],
            "cost": self.cost,
            "hops": self.hops,
        }


@dataclass(frozen=True, slots=True)
class Cycle:
    """A simple cycle discovered in the graph."""

    node_ids: tuple[int, ...]
    labels: tuple[str, ...]
    length: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "node_ids": list(self.node_ids),
            "labels": list(self.labels),
            "length": self.length,
        }


@dataclass(frozen=True, slots=True)
class Community:
    """A densely connected group found by label propagation."""

    index: int
    node_ids: tuple[int, ...]
    labels: tuple[str, ...]
    score: float
    iterations: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "index": self.index,
            "node_ids": list(self.node_ids),
            "labels": list(self.labels),
            "score": self.score,
            "iterations": self.iterations,
        }


def adjacency(
    model: GraphModel,
    *,
    kinds: tuple[str, ...] = EDGE_KINDS,
    directed: bool = False,
    resolved_only: bool = False,
) -> WeightMap:
    """Build a weighted adjacency map from the model's edges."""
    allowed = frozenset(kinds)
    result: WeightMap = {node_id: {} for node_id in model.nodes}
    for edge in model.edges.values():
        if edge.kind not in allowed or (resolved_only and not edge.resolved):
            continue
        weight = max(edge.weight, 1e-9)
        result.setdefault(edge.source, {})
        result.setdefault(edge.target, {})
        result[edge.source][edge.target] = result[edge.source].get(edge.target, 0.0) + weight
        if not directed:
            result[edge.target][edge.source] = result[edge.target].get(edge.source, 0.0) + weight
    return result


def connected_components(
    model: GraphModel,
    *,
    kinds: tuple[str, ...] = EDGE_KINDS,
    min_size: int = 1,
) -> tuple[Component, ...]:
    """Return vertices grouped by undirected reachability."""
    if min_size < 1:
        raise ValueError("min_size must be positive")
    links = adjacency(model, kinds=kinds)
    visited: set[int] = set()
    groups: list[tuple[int, ...]] = []
    for start in sorted(links):
        if start in visited:
            continue
        visited.add(start)
        queue = deque([start])
        members: list[int] = []
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbor in sorted(links[current]):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        if len(members) >= min_size:
            groups.append(tuple(sorted(members)))
    groups.sort(key=lambda group: (-len(group), group))
    return tuple(
        Component(
            index=index,
            node_ids=group,
            labels=tuple(model.nodes[node_id].label for node_id in group),
            size=len(group),
        )
        for index, group in enumerate(groups, start=1)
    )


def _ranked_scores(
    model: GraphModel,
    values: dict[int, float],
    measure: str,
) -> tuple[CentralityScore, ...]:
    ordered = sorted(values, key=lambda node_id: (-values[node_id], node_id))
    positions = {node_id: index + 1 for index, node_id in enumerate(ordered)}
    return tuple(
        CentralityScore(
            node_id=node_id,
            label=model.nodes[node_id].label,
            score=round(values[node_id], 6),
            measure=measure,
            rank=positions[node_id],
        )
        for node_id in ordered
    )


def degree_centrality(model: GraphModel) -> tuple[CentralityScore, ...]:
    """Rank vertices by normalized neighbor count."""
    links = adjacency(model)
    size = len(links)
    if size <= 1:
        return _ranked_scores(model, dict.fromkeys(links, 0.0), "degree")
    values = {node_id: len(neighbors) / (size - 1) for node_id, neighbors in links.items()}
    return _ranked_scores(model, values, "degree")


def closeness_centrality(model: GraphModel) -> tuple[CentralityScore, ...]:
    """Rank vertices by inverse mean distance to reachable vertices."""
    links = adjacency(model)
    values: dict[int, float] = {}
    for node_id in links:
        distances = _distances(links, node_id)
        reachable = [value for value in distances.values() if value > 0]
        total = sum(reachable)
        values[node_id] = (len(reachable) - 1) / total if total > 0 else 0.0
    return _ranked_scores(model, values, "closeness")


def betweenness_centrality(model: GraphModel) -> tuple[CentralityScore, ...]:
    """Rank vertices by shortest-path brokerage (Brandes, unweighted)."""
    links = adjacency(model)
    scores = dict.fromkeys(links, 0.0)
    for source in sorted(links):
        stack: list[int] = []
        predecessors: dict[int, list[int]] = {node_id: [] for node_id in links}
        paths = dict.fromkeys(links, 0.0)
        distance = dict.fromkeys(links, -1)
        distance[source] = 0
        paths[source] = 1.0
        queue = deque([source])
        while queue:
            current = queue.popleft()
            stack.append(current)
            for neighbor in sorted(links[current]):
                if distance[neighbor] < 0:
                    distance[neighbor] = distance[current] + 1
                    queue.append(neighbor)
                if distance[neighbor] == distance[current] + 1:
                    paths[neighbor] += paths[current]
                    predecessors[neighbor].append(current)
        dependency = dict.fromkeys(links, 0.0)
        while stack:
            current = stack.pop()
            for previous in predecessors[current]:
                share = paths[previous] / paths[current] if paths[current] else 0.0
                dependency[previous] += share * (1.0 + dependency[current])
            if current != source:
                scores[current] += dependency[current]
    size = len(links)
    scale = 2.0 / ((size - 1) * (size - 2)) if size > 2 else 1.0
    return _ranked_scores(
        model, {key: value * scale for key, value in scores.items()}, "betweenness"
    )


def eigenvector_centrality(
    model: GraphModel, *, iterations: int = 80
) -> tuple[CentralityScore, ...]:
    """Rank vertices by the principal eigenvector of their adjacency."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    links = adjacency(model)
    scores = dict.fromkeys(links, 1.0)
    for _ in range(iterations):
        updated = {
            node_id: sum(scores[neighbor] for neighbor in neighbors)
            for node_id, neighbors in links.items()
        }
        norm = math.sqrt(sum(value * value for value in updated.values()))
        if norm == 0:
            return _ranked_scores(model, dict.fromkeys(links, 0.0), "eigenvector")
        scores = {node_id: value / norm for node_id, value in updated.items()}
    return _ranked_scores(model, scores, "eigenvector")


def _distances(links: WeightMap, source: int) -> dict[int, float]:
    """Return hop distances from one vertex."""
    result = {source: 0.0}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        for neighbor in links[current]:
            if neighbor in result:
                continue
            result[neighbor] = result[current] + 1.0
            queue.append(neighbor)
    return result


def clustering_coefficients(model: GraphModel) -> tuple[ClusteringScore, ...]:
    """Compute local clustering coefficients and triangle counts."""
    links = adjacency(model)
    scores: list[ClusteringScore] = []
    for node_id in sorted(links):
        neighbors = set(links[node_id])
        degree = len(neighbors)
        triangles = 0
        if degree >= 2:
            for left in neighbors:
                for right in neighbors:
                    if left < right and right in links[left]:
                        triangles += 1
        possible = degree * (degree - 1) / 2
        coefficient = triangles / possible if possible else 0.0
        node = model.nodes[node_id]
        scores.append(
            ClusteringScore(
                node_id=node_id,
                label=node.label,
                coefficient=round(coefficient, 6),
                degree=degree,
                triangles=triangles,
            )
        )
    return tuple(scores)


def average_clustering(model: GraphModel) -> float:
    """Return the mean local clustering coefficient."""
    scores = clustering_coefficients(model)
    if not scores:
        return 0.0
    return round(sum(item.coefficient for item in scores) / len(scores), 6)


def shortest_path(
    model: GraphModel,
    source: int,
    target: int,
    *,
    weighted: bool = False,
    directed: bool = False,
    max_hops: int | None = None,
) -> GraphPath | None:
    """Find a deterministic shortest path between two vertices."""
    if source not in model.nodes or target not in model.nodes:
        raise ValueError("Path endpoints must exist in the graph")
    if max_hops is not None and max_hops < 0:
        raise ValueError("max_hops cannot be negative")
    links = adjacency(model, directed=directed)
    if source == target:
        node = model.nodes[source]
        return GraphPath((source,), (node.label,), (), 0.0, 0)

    previous: dict[int, tuple[int, float]] = {}
    costs: dict[int, float] = {source: 0.0}
    hops: dict[int, int] = {source: 0}
    frontier: list[tuple[float, int]] = [(0.0, source)]
    while frontier:
        cost, current = heapq.heappop(frontier)
        if cost > costs.get(current, math.inf):
            continue
        if current == target:
            break
        if max_hops is not None and hops[current] >= max_hops:
            continue
        for neighbor in sorted(links[current]):
            step = links[current][neighbor] if weighted else 1.0
            candidate = cost + step
            candidate_hops = hops[current] + 1
            if candidate >= costs.get(neighbor, math.inf):
                continue
            costs[neighbor] = candidate
            hops[neighbor] = candidate_hops
            previous[neighbor] = (current, step)
            heapq.heappush(frontier, (candidate, neighbor))
    if target not in previous:
        return None

    chain: list[int] = []
    steps: list[float] = []
    cursor = target
    while cursor != source:
        parent, step = previous[cursor]
        chain.append(cursor)
        steps.append(step)
        cursor = parent
    chain.append(source)
    chain.reverse()
    steps.reverse()
    edge_keys: list[tuple[int, int, str]] = []
    for left, right in itertools.pairwise(chain):
        candidates = [
            edge.key for edge in model.edges.values() if {edge.source, edge.target} == {left, right}
        ]
        if candidates:
            edge_keys.append(min(candidates))
    return GraphPath(
        node_ids=tuple(chain),
        labels=tuple(model.nodes[node_id].label for node_id in chain),
        edge_keys=tuple(edge_keys),
        cost=round(sum(steps), 6),
        hops=len(chain) - 1,
    )


def _canonical_cycle(cycle: tuple[int, ...]) -> tuple[int, ...]:
    """Return the lexicographically smallest rotation and direction."""
    rotations: list[tuple[int, ...]] = []
    for sequence in (cycle, tuple(reversed(cycle))):
        rotations.extend(sequence[index:] + sequence[:index] for index in range(len(sequence)))
    return min(rotations)


def find_cycles(model: GraphModel, *, limit: int = 25) -> tuple[Cycle, ...]:
    """Discover simple cycles via DFS back edges, deduplicated canonically."""
    if limit < 1:
        raise ValueError("limit must be positive")
    links = adjacency(model)
    discovered: set[tuple[int, ...]] = set()
    budget = max(limit * 2000, 5000)
    for start in sorted(links):
        if len(discovered) >= limit or budget <= 0:
            break
        stack: list[tuple[int, tuple[int, ...]]] = [(start, (start,))]
        while stack and budget > 0:
            current, chain = stack.pop()
            for neighbor in sorted(links[current]):
                budget -= 1
                if budget <= 0:
                    break
                if neighbor == start and len(chain) >= 3:
                    discovered.add(_canonical_cycle(chain))
                elif neighbor > start and neighbor not in chain:
                    stack.append((neighbor, (*chain, neighbor)))
            if len(discovered) >= limit:
                break
    ordered = sorted(discovered, key=lambda cycle: (len(cycle), cycle))
    return tuple(
        Cycle(
            node_ids=cycle,
            labels=tuple(model.nodes[node_id].label for node_id in cycle),
            length=len(cycle),
        )
        for cycle in ordered[:limit]
    )


def detect_communities(
    model: GraphModel,
    *,
    max_iterations: int = 30,
    seed: int = 1,
) -> tuple[Community, ...]:
    """Group vertices with deterministic asynchronous label propagation."""
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive")
    links = adjacency(model)
    labels = {node_id: node_id for node_id in sorted(links)}
    order = sorted(links)
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        changed = False
        offset = iteration * seed
        for index, node_id in enumerate(order):
            rotated = order[offset % len(order) :] + order[: offset % len(order)]
            neighbors = sorted(
                links[node_id], key=lambda item: (index + item + offset) % len(order)
            )
            if not neighbors:
                continue
            counts: dict[int, int] = {}
            for neighbor in rotated:
                if neighbor not in neighbors:
                    continue
                label = labels[neighbor]
                counts[label] = counts.get(label, 0) + 1
            if not counts:
                continue
            best = max(counts.values())
            choice = min(label for label, count in counts.items() if count == best)
            if labels[node_id] != choice:
                labels[node_id] = choice
                changed = True
        if not changed:
            break

    groups: dict[int, list[int]] = {}
    for node_id in order:
        groups.setdefault(labels[node_id], []).append(node_id)
    memberships = sorted(groups.values(), key=lambda group: (-len(group), group))
    communities: list[Community] = []
    for index, group in enumerate(memberships, start=1):
        interior = 0
        for node_id in group:
            interior += sum(1 for neighbor in links[node_id] if neighbor in set(group))
        score = interior / 2 / max(1, len(group))
        communities.append(
            Community(
                index=index,
                node_ids=tuple(group),
                labels=tuple(model.nodes[node_id].label for node_id in group),
                score=round(score, 6),
                iterations=iterations,
            )
        )
    return tuple(communities)


def graph_metrics(model: GraphModel) -> dict[str, float]:
    """Return a compact numeric summary of a graph."""
    links = adjacency(model)
    directed_count = sum(1 for edge in model.edges.values() if edge.source != edge.target)
    components = connected_components(model)
    degrees = [len(neighbors) for neighbors in links.values()]
    return {
        "nodes": float(len(links)),
        "edges": float(directed_count),
        "density": round(
            (2 * directed_count) / (len(links) * (len(links) - 1)) if len(links) > 1 else 0.0,
            6,
        ),
        "components": float(len(components)),
        "largest_component": float(max((item.size for item in components), default=0)),
        "average_degree": round(sum(degrees) / len(degrees), 6) if degrees else 0.0,
        "average_clustering": average_clustering(model),
        "cycles": float(len(find_cycles(model))),
    }
