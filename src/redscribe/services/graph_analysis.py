"""Graph intelligence over the vault knowledge graph."""

from __future__ import annotations

import dataclasses
from collections import deque
from collections.abc import Iterator
from typing import Any

from redscribe.domain.fuzzy import rank_scored, token_aware_score
from redscribe.services.graph import (
    GRAPH_EDGE_LINK,
    GRAPH_EDGE_PARENT,
    GRAPH_NODE_KIND_NOTE,
    GRAPH_NODE_KIND_REFERENCE,
    GraphEdge,
    GraphNode,
    VaultGraph,
    build_vault_graph,
)
from redscribe.storage.db import Vault

REASON_UNRESOLVED_LINK = "unresolved_link"
REASON_SIMILAR_TITLE = "similar_title"
REASON_SHARED_TAG = "shared_tag"
REASON_SHARED_NEIGHBOR = "shared_neighbor"


@dataclasses.dataclass(frozen=True, slots=True)
class _GraphView:
    nodes: dict[int, GraphNode]
    edges: tuple[GraphEdge, ...]
    outgoing: dict[int, frozenset[int]]
    incoming: dict[int, frozenset[int]]

    def notes(self) -> tuple[GraphNode, ...]:
        return tuple(
            self.nodes[node_id]
            for node_id in sorted(self.nodes)
            if self.nodes[node_id].kind == GRAPH_NODE_KIND_NOTE
        )


def _view(graph: VaultGraph) -> _GraphView:
    nodes = {node.id: node for node in graph.nodes}
    outgoing: dict[int, set[int]] = {node_id: set() for node_id in nodes}
    incoming: dict[int, set[int]] = {node_id: set() for node_id in nodes}
    for edge in graph.edges:
        if edge.kind != GRAPH_EDGE_LINK or not edge.resolved:
            continue
        if edge.source not in outgoing or edge.target not in outgoing:
            continue
        outgoing[edge.source].add(edge.target)
        incoming[edge.target].add(edge.source)
    return _GraphView(
        nodes=nodes,
        edges=graph.edges,
        outgoing={node_id: frozenset(targets) for node_id, targets in outgoing.items()},
        incoming={node_id: frozenset(sources) for node_id, sources in incoming.items()},
    )


def _tags(node: GraphNode) -> frozenset[str]:
    return frozenset(tag.casefold() for tag in node.tags)


def link_adjacency(graph: VaultGraph) -> dict[int, frozenset[int]]:
    """Return the undirected adjacency of resolved wikilinks."""
    view = _view(graph)
    adjacency = {node_id: set(targets) for node_id, targets in view.outgoing.items()}
    for node_id, sources in view.incoming.items():
        adjacency[node_id].update(sources)
    return {node_id: frozenset(targets) for node_id, targets in adjacency.items()}


def link_degrees(graph: VaultGraph) -> dict[int, tuple[int, int]]:
    """Return ``{node_id: (in_degree, out_degree)}`` for resolved wikilinks."""
    view = _view(graph)
    return {
        node_id: (len(view.incoming[node_id]), len(view.outgoing[node_id]))
        for node_id in sorted(view.nodes)
    }


@dataclasses.dataclass(frozen=True, slots=True)
class InfluenceConfig:
    """Tunable parameters for the weighted PageRank-style score."""

    damping: float = 0.85
    iterations: int = 48
    tolerance: float = 1e-9
    link_weight: float = 1.0
    shared_tag_weight: float = 0.5
    pinned_boost: float = 1.5


@dataclasses.dataclass(frozen=True, slots=True)
class InfluenceScore:
    """A note's computed importance plus its link degrees."""

    node_id: int
    title: str
    score: float
    in_degree: int
    out_degree: int


def rank_influence(
    graph: VaultGraph, *, config: InfluenceConfig | None = None
) -> tuple[InfluenceScore, ...]:
    """Rank notes by dampened, tag-weighted link influence.

    Links between notes sharing tags carry more weight, and pinned notes get a
    larger teleportation share. Dangling nodes redistribute their rank evenly.
    """
    settings = config if config is not None else InfluenceConfig()
    if not 0 < settings.damping < 1:
        raise ValueError("damping must be between 0 and 1")
    if settings.iterations < 1:
        raise ValueError("iterations must be positive")
    if settings.link_weight <= 0 or settings.shared_tag_weight < 0:
        raise ValueError("link weights must be non-negative and link_weight positive")
    if settings.pinned_boost <= 0:
        raise ValueError("pinned_boost must be positive")
    view = _view(graph)
    notes = view.notes()
    if not notes:
        return ()
    ids = [node.id for node in notes]
    positions = {node_id: index for index, node_id in enumerate(ids)}
    weights: dict[int, dict[int, float]] = {}
    for edge in view.edges:
        if edge.kind != GRAPH_EDGE_LINK or not edge.resolved:
            continue
        if edge.source not in positions or edge.target not in positions:
            continue
        overlap = len(_tags(view.nodes[edge.source]) & _tags(view.nodes[edge.target]))
        weight = settings.link_weight + settings.shared_tag_weight * overlap
        targets = weights.setdefault(edge.source, {})
        targets[edge.target] = targets.get(edge.target, 0.0) + weight
    boosts = [settings.pinned_boost if node.pinned else 1.0 for node in notes]
    total_boost = sum(boosts)
    teleport = [boost / total_boost for boost in boosts]
    size = len(ids)
    rank = [1.0 / size] * size
    for _ in range(settings.iterations):
        following = [(1.0 - settings.damping) * value for value in teleport]
        dangling = settings.damping / size
        for source in ids:
            outgoing = weights.get(source)
            mass = settings.damping * rank[positions[source]]
            if outgoing:
                strength = sum(outgoing.values())
                for target, weight in outgoing.items():
                    following[positions[target]] += mass * weight / strength
            else:
                for index in range(size):
                    following[index] += dangling * rank[positions[source]]
        delta = sum(abs(following[index] - rank[index]) for index in range(size))
        rank = following
        if delta < settings.tolerance:
            break
    results = [
        InfluenceScore(
            node_id=note.id,
            title=note.title,
            score=rank[positions[note.id]],
            in_degree=len(view.incoming[note.id]),
            out_degree=len(view.outgoing[note.id]),
        )
        for note in notes
    ]
    results.sort(key=lambda item: (-item.score, item.node_id))
    return tuple(results)


@dataclasses.dataclass(frozen=True, slots=True)
class NotePath:
    """An undirected path between two notes."""

    node_ids: tuple[int, ...]
    titles: tuple[str, ...]
    hops: int


def _undirected_adjacency(view: _GraphView, *, include_parents: bool) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {node_id: set() for node_id in view.nodes}
    kinds = {GRAPH_EDGE_LINK}
    if include_parents:
        kinds.add(GRAPH_EDGE_PARENT)
    for edge in view.edges:
        if edge.kind not in kinds or not edge.resolved:
            continue
        if edge.source not in adjacency or edge.target not in adjacency:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
    return adjacency


def shortest_path(
    graph: VaultGraph, source_id: int, target_id: int, *, include_parents: bool = False
) -> NotePath | None:
    """Return the shortest resolved link path, or ``None`` when disconnected."""
    view = _view(graph)
    if source_id not in view.nodes or target_id not in view.nodes:
        raise ValueError("Node does not exist")
    if source_id == target_id:
        node = view.nodes[source_id]
        return NotePath(node_ids=(source_id,), titles=(node.title,), hops=0)
    adjacency = _undirected_adjacency(view, include_parents=include_parents)
    previous: dict[int, int | None] = {source_id: None}
    queue = deque([source_id])
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency[current]):
            if neighbor in previous:
                continue
            previous[neighbor] = current
            queue.append(neighbor)
    if target_id not in previous:
        return None
    chain: list[int] = []
    cursor: int | None = target_id
    while cursor is not None:
        chain.append(cursor)
        cursor = previous[cursor]
    chain.reverse()
    return NotePath(
        node_ids=tuple(chain),
        titles=tuple(view.nodes[node_id].title for node_id in chain),
        hops=len(chain) - 1,
    )


def path_payload(path: NotePath | None) -> dict[str, Any] | None:
    """Return a JSON-ready path, if one exists."""
    if path is None:
        return None
    return dataclasses.asdict(path)


@dataclasses.dataclass(frozen=True, slots=True)
class OrphanNote:
    """A live note with no resolved wikilinks in either direction."""

    node_id: int
    title: str
    path: str


def find_orphans(graph: VaultGraph) -> tuple[OrphanNote, ...]:
    """Return notes with no resolved inbound or outbound wikilinks."""
    view = _view(graph)
    orphans = [
        OrphanNote(node_id=node.id, title=node.title, path=node.path)
        for node in view.notes()
        if not view.incoming[node.id] and not view.outgoing[node.id]
    ]
    orphans.sort(key=lambda item: (item.title.casefold(), item.node_id))
    return tuple(orphans)


@dataclasses.dataclass(frozen=True, slots=True)
class BridgeEdge:
    """A link whose removal disconnects part of the link graph."""

    source_id: int
    target_id: int
    source_title: str
    target_title: str


def find_bridges(graph: VaultGraph) -> tuple[BridgeEdge, ...]:
    """Find bridge links in the undirected graph using Tarjan's algorithm."""
    view = _view(graph)
    adjacency = _undirected_adjacency(view, include_parents=False)
    discovery: dict[int, int] = {}
    low: dict[int, int] = {}
    parent: dict[int, int | None] = {}
    bridges: set[tuple[int, int]] = set()
    timer = 0
    for start in sorted(adjacency):
        if start in discovery:
            continue
        discovery[start] = low[start] = timer
        timer += 1
        parent[start] = None
        stack: list[tuple[int, Iterator[int]]] = [(start, iter(sorted(adjacency[start])))]
        while stack:
            node, neighbours = stack[-1]
            descended = False
            for neighbor in neighbours:
                if neighbor == parent.get(node):
                    continue
                if neighbor not in discovery:
                    parent[neighbor] = node
                    discovery[neighbor] = low[neighbor] = timer
                    timer += 1
                    stack.append((neighbor, iter(sorted(adjacency[neighbor]))))
                    descended = True
                    break
                low[node] = min(low[node], discovery[neighbor])
            if descended:
                continue
            stack.pop()
            ancestor = parent.get(node)
            if ancestor is None:
                continue
            low[ancestor] = min(low[ancestor], low[node])
            if low[node] > discovery[ancestor]:
                bridges.add((min(ancestor, node), max(ancestor, node)))
    result = [
        BridgeEdge(
            source_id=source,
            target_id=target,
            source_title=view.nodes[source].title,
            target_title=view.nodes[target].title,
        )
        for source, target in sorted(bridges)
    ]
    result.sort(
        key=lambda item: (
            item.source_title.casefold(),
            item.target_title.casefold(),
            item.source_id,
            item.target_id,
        )
    )
    return tuple(result)


@dataclasses.dataclass(frozen=True, slots=True)
class Community:
    """A connected cluster of notes joined by resolved wikilinks."""

    key: int
    node_ids: tuple[int, ...]
    titles: tuple[str, ...]
    size: int


def find_communities(graph: VaultGraph, *, min_size: int = 2) -> tuple[Community, ...]:
    """Group notes into link-connected communities, largest first."""
    if min_size < 1:
        raise ValueError("min_size must be positive")
    view = _view(graph)
    parent = {node.id: node.id for node in view.notes()}

    def find(node_id: int) -> int:
        root = node_id
        while parent[root] != root:
            root = parent[root]
        while parent[node_id] != root:
            following = parent[node_id]
            parent[node_id] = root
            node_id = following
        return root

    for edge in view.edges:
        if edge.kind != GRAPH_EDGE_LINK or not edge.resolved:
            continue
        if edge.source not in parent or edge.target not in parent:
            continue
        left, right = find(edge.source), find(edge.target)
        if left == right:
            continue
        if left < right:
            parent[right] = left
        else:
            parent[left] = right
    groups: dict[int, list[int]] = {}
    for node_id in parent:
        groups.setdefault(find(node_id), []).append(node_id)
    clusters: list[tuple[int, int, tuple[int, ...], tuple[str, ...]]] = []
    for members in groups.values():
        if len(members) < min_size:
            continue
        ordered = tuple(sorted(members))
        titles = tuple(view.nodes[node_id].title for node_id in ordered)
        clusters.append((len(ordered), ordered[0], ordered, titles))
    clusters.sort(key=lambda item: (-item[0], item[2]))
    return tuple(
        Community(key=index, node_ids=item[2], titles=item[3], size=item[0])
        for index, item in enumerate(clusters, start=1)
    )


@dataclasses.dataclass(frozen=True, slots=True)
class LinkSuggestion:
    """A proposed wikilink between two live notes."""

    source_id: int
    source_title: str
    target_id: int
    target_title: str
    score: float
    reasons: tuple[str, ...]


def _merge_suggestion(
    suggestions: dict[tuple[int, int], LinkSuggestion], candidate: LinkSuggestion
) -> None:
    key = (candidate.source_id, candidate.target_id)
    current = suggestions.get(key)
    if current is None:
        suggestions[key] = candidate
        return
    reasons = tuple(sorted({*current.reasons, *candidate.reasons}))
    suggestions[key] = dataclasses.replace(
        current, score=max(current.score, candidate.score), reasons=reasons
    )


def _unresolved_suggestions(
    view: _GraphView, suggestions: dict[tuple[int, int], LinkSuggestion], min_score: int
) -> None:
    notes = view.notes()
    for edge in view.edges:
        if edge.kind != GRAPH_EDGE_LINK or edge.resolved:
            continue
        reference = view.nodes.get(edge.target)
        source = view.nodes.get(edge.source)
        if reference is None or source is None or reference.kind != GRAPH_NODE_KIND_REFERENCE:
            continue
        linked = {source.id, *view.outgoing.get(source.id, ())}
        candidates = [note for note in notes if note.id not in linked]
        ranked = rank_scored(reference.title, candidates, key=lambda note: note.title, limit=3)
        for entry in ranked:
            if entry.score < min_score:
                continue
            _merge_suggestion(
                suggestions,
                LinkSuggestion(
                    source_id=source.id,
                    source_title=source.title,
                    target_id=entry.item.id,
                    target_title=entry.item.title,
                    score=round(min(1.0, entry.score / 120), 3),
                    reasons=(REASON_UNRESOLVED_LINK, REASON_SIMILAR_TITLE),
                ),
            )


def _tag_suggestions(view: _GraphView, suggestions: dict[tuple[int, int], LinkSuggestion]) -> None:
    notes = view.notes()
    tags = {node.id: _tags(node) for node in notes}
    for index, left in enumerate(notes):
        for right in notes[index + 1 :]:
            if right.id in view.outgoing.get(left.id, ()) or left.id in view.outgoing.get(
                right.id, ()
            ):
                continue
            overlap = tags[left.id] & tags[right.id]
            shared = view.outgoing.get(left.id, frozenset()) & view.outgoing.get(
                right.id, frozenset()
            )
            if not overlap and not shared:
                continue
            title_score = token_aware_score(left.title, right.title) or 0
            reasons = []
            if overlap:
                reasons.append(REASON_SHARED_TAG)
            if shared:
                reasons.append(REASON_SHARED_NEIGHBOR)
            if title_score >= 45:
                reasons.append(REASON_SIMILAR_TITLE)
            _merge_suggestion(
                suggestions,
                LinkSuggestion(
                    source_id=left.id,
                    source_title=left.title,
                    target_id=right.id,
                    target_title=right.title,
                    score=round(
                        0.3
                        + 0.2 * len(overlap)
                        + 0.12 * len(shared)
                        + min(0.15, title_score / 600),
                        3,
                    ),
                    reasons=tuple(sorted(reasons)),
                ),
            )


def suggest_links(
    graph: VaultGraph, *, limit: int = 12, min_score: int = 45
) -> tuple[LinkSuggestion, ...]:
    """Suggest unresolved targets and linked-but-unrelated note pairs."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if not 0 <= min_score <= 120:
        raise ValueError("min_score must be between 0 and 120")
    view = _view(graph)
    suggestions: dict[tuple[int, int], LinkSuggestion] = {}
    _unresolved_suggestions(view, suggestions, min_score)
    _tag_suggestions(view, suggestions)
    ordered = sorted(
        suggestions.values(),
        key=lambda item: (-item.score, item.source_id, item.target_id, item.reasons),
    )
    return tuple(ordered[:limit])


@dataclasses.dataclass(frozen=True, slots=True)
class GraphInsights:
    """The complete graph-intelligence view of a vault."""

    influence: tuple[InfluenceScore, ...]
    orphans: tuple[OrphanNote, ...]
    bridges: tuple[BridgeEdge, ...]
    communities: tuple[Community, ...]
    suggestions: tuple[LinkSuggestion, ...]


def build_graph_insights(
    graph: VaultGraph,
    *,
    config: InfluenceConfig | None = None,
    max_suggestions: int = 12,
    min_suggestion_score: int = 45,
) -> GraphInsights:
    """Compute all graph-intelligence signals from one graph snapshot."""
    if max_suggestions < 0:
        raise ValueError("max_suggestions must be non-negative")
    suggestions: tuple[LinkSuggestion, ...] = ()
    if max_suggestions:
        suggestions = suggest_links(graph, limit=max_suggestions, min_score=min_suggestion_score)
    return GraphInsights(
        influence=rank_influence(graph, config=config),
        orphans=find_orphans(graph),
        bridges=find_bridges(graph),
        communities=find_communities(graph),
        suggestions=suggestions,
    )


def vault_graph_insights(
    vault: Vault,
    *,
    config: InfluenceConfig | None = None,
    max_suggestions: int = 12,
    min_suggestion_score: int = 45,
) -> GraphInsights:
    """Build graph insights directly from a vault."""
    return build_graph_insights(
        build_vault_graph(vault),
        config=config,
        max_suggestions=max_suggestions,
        min_suggestion_score=min_suggestion_score,
    )


def graph_insights_payload(insights: GraphInsights) -> dict[str, Any]:
    """Return the JSON payload for graph insights."""
    return {
        "summary": {
            "notes": len(insights.influence),
            "orphans": len(insights.orphans),
            "bridges": len(insights.bridges),
            "communities": len(insights.communities),
            "suggestions": len(insights.suggestions),
        },
        "influence": [dataclasses.asdict(item) for item in insights.influence],
        "orphans": [dataclasses.asdict(item) for item in insights.orphans],
        "bridges": [dataclasses.asdict(item) for item in insights.bridges],
        "communities": [dataclasses.asdict(item) for item in insights.communities],
        "suggestions": [dataclasses.asdict(item) for item in insights.suggestions],
    }
