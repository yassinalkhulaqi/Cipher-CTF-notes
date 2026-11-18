"""Recommendation services built on graph structure and note metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.domain.fuzzy import token_aware_score
from redscribe.v2.graph.extract import normalize_reference
from redscribe.v2.graph.model import NODE_NOTE, NODE_REFERENCE, GraphNode
from redscribe.v2.graph.store import GraphStore

REASON_SHARED_TAG = "shared_tag"
REASON_SHARED_NEIGHBOR = "shared_neighbor"
REASON_TITLE_SIMILARITY = "title_similarity"
REASON_UNRESOLVED_REFERENCE = "unresolved_reference"
REASON_TWO_HOPS = "two_hops"
REASON_POPULAR = "popular"

KIND_LINK = "link"
KIND_NOTE = "note"
KIND_TAG = "tag"

MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One scored recommendation with human-readable reasons."""

    source_id: int
    target_id: int
    source_title: str
    target_title: str
    score: float
    reasons: tuple[str, ...]
    kind: str = KIND_NOTE

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "source_title": self.source_title,
            "target_title": self.target_title,
            "score": self.score,
            "reasons": list(self.reasons),
            "kind": self.kind,
        }


def _score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


class RecommendationService:
    """Recommend related notes and missing links from graph signals."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def notes(self) -> tuple[GraphNode, ...]:
        """Return all note vertices in stable order."""
        return self.store.nodes.of_kind(NODE_NOTE)

    def _title_score(self, left: GraphNode, right: GraphNode) -> float:
        raw = token_aware_score(left.label, right.label)
        return (raw or 0) / 120.0

    def _shared_neighbors(self, left: int, right: int) -> set[int]:
        outgoing = self.store.edges.outgoing
        incoming = self.store.edges.incoming
        left_neighbors = {*outgoing(left), *incoming(left)}
        right_neighbors = {*outgoing(right), *incoming(right)}
        return left_neighbors & right_neighbors

    def related(
        self,
        node_id: int,
        *,
        limit: int = 10,
        min_score: float = 0.1,
    ) -> tuple[Recommendation, ...]:
        """Rank notes related to one note by tags, neighbors, and titles."""
        if limit < 1 or limit > MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        source = self.store.nodes.get(node_id)
        if source is None or source.kind != NODE_NOTE:
            return ()
        source_tags = source.tag_set
        source_out = set(self.store.edges.outgoing(node_id))
        source_in = set(self.store.edges.incoming(node_id))
        results: list[Recommendation] = []
        for candidate in self.notes():
            if candidate.id == node_id:
                continue
            reasons: list[str] = []
            overlap = source_tags & candidate.tag_set
            if overlap:
                reasons.append(REASON_SHARED_TAG)
            shared = self._shared_neighbors(node_id, candidate.id)
            if shared:
                reasons.append(REASON_SHARED_NEIGHBOR)
            title_score = self._title_score(source, candidate)
            if title_score >= 0.35:
                reasons.append(REASON_TITLE_SIMILARITY)
            if not reasons:
                continue
            score = _score(
                0.30 + 0.18 * min(len(overlap), 3) + 0.14 * min(len(shared), 3) + 0.25 * title_score
            )
            if score < min_score:
                continue
            if candidate.id in source_out or candidate.id in source_in:
                score = _score(score * 0.7)
            results.append(
                Recommendation(
                    source_id=node_id,
                    target_id=candidate.id,
                    source_title=source.label,
                    target_title=candidate.label,
                    score=score,
                    reasons=tuple(sorted(reasons)),
                )
            )
        results.sort(key=lambda item: (-item.score, item.target_title.casefold(), item.target_id))
        return tuple(results[:limit])

    def missing_links(
        self,
        *,
        limit: int = 12,
        min_score: float = 0.2,
    ) -> tuple[Recommendation, ...]:
        """Propose links for unresolved references and weakly connected notes."""
        if limit < 1 or limit > MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        results: dict[tuple[int, int], Recommendation] = {}
        for reference in self.store.nodes.of_kind(NODE_REFERENCE):
            label = str(reference.metadata.get("target", reference.label))
            reference_key = normalize_reference(label)
            candidates = [
                note for note in self.notes() if normalize_reference(note.label) == reference_key
            ]
            if not candidates:
                candidates = [
                    note
                    for note in self.notes()
                    if (token_aware_score(label, note.label) or 0) >= 50
                ]
            for edge in self.store.edges.incident(reference.id):
                source = self.store.nodes.get(edge.source)
                if source is None or source.kind != NODE_NOTE:
                    continue
                for candidate in candidates[:3]:
                    if candidate.id == source.id:
                        continue
                    title = token_aware_score(label, candidate.label) or 0
                    score = _score(0.45 + title / 300 + 0.1)
                    if score < min_score:
                        continue
                    results[(source.id, candidate.id)] = Recommendation(
                        source_id=source.id,
                        target_id=candidate.id,
                        source_title=source.label,
                        target_title=candidate.label,
                        score=score,
                        reasons=(REASON_UNRESOLVED_REFERENCE, REASON_TITLE_SIMILARITY),
                        kind=KIND_LINK,
                    )
        for recommendation in self._two_hop_suggestions():
            key = (recommendation.source_id, recommendation.target_id)
            if key in results:
                continue
            if recommendation.score >= min_score:
                results[key] = recommendation
        ordered = sorted(
            results.values(),
            key=lambda item: (-item.score, item.source_id, item.target_id),
        )
        return tuple(ordered[:limit])

    def _two_hop_suggestions(self) -> tuple[Recommendation, ...]:
        """Suggest links between notes that share two-hop neighborhoods."""
        results: list[Recommendation] = []
        notes = self.notes()
        for index, source in enumerate(notes):
            source_neighbors = set(self.store.edges.neighbors(source.id))
            for target in notes[index + 1 :]:
                if target.id in source_neighbors:
                    continue
                shared = self._shared_neighbors(source.id, target.id)
                if not shared:
                    continue
                tag_overlap = source.tag_set & target.tag_set
                score = _score(0.25 + 0.12 * len(shared) + 0.12 * len(tag_overlap))
                reasons = [REASON_SHARED_NEIGHBOR, REASON_TWO_HOPS]
                if tag_overlap:
                    reasons.append(REASON_SHARED_TAG)
                results.append(
                    Recommendation(
                        source_id=source.id,
                        target_id=target.id,
                        source_title=source.label,
                        target_title=target.label,
                        score=score,
                        reasons=tuple(sorted(reasons)),
                        kind=KIND_LINK,
                    )
                )
        return tuple(results)

    def by_tag(self, tag: str, *, limit: int = 10) -> tuple[Recommendation, ...]:
        """Suggest note pairs among the vertices carrying one tag."""
        key = tag.casefold().lstrip("#")
        members = [node for node in self.store.nodes.with_tag(key) if node.kind == NODE_NOTE]
        results: list[Recommendation] = []
        for index, source in enumerate(members):
            for target in members[index + 1 :]:
                if target.id in {
                    *self.store.edges.outgoing(source.id),
                    *self.store.edges.incoming(source.id),
                }:
                    continue
                score = _score(0.55 + 0.2 * self._title_score(source, target))
                results.append(
                    Recommendation(
                        source_id=source.id,
                        target_id=target.id,
                        source_title=source.label,
                        target_title=target.label,
                        score=score,
                        reasons=(REASON_SHARED_TAG,),
                        kind=KIND_TAG,
                    )
                )
        results.sort(key=lambda item: (-item.score, item.target_id))
        return tuple(results[:limit])

    def popular(self, *, limit: int = 10) -> tuple[Recommendation, ...]:
        """Rank notes by in-degree for discovery widgets."""
        scores: list[tuple[int, GraphNode]] = []
        for node in self.notes():
            degree = len(self.store.edges.incoming(node.id))
            if degree:
                scores.append((degree, node))
        scores.sort(key=lambda item: (-item[0], item[1].label.casefold(), item[1].id))
        return tuple(
            Recommendation(
                source_id=0,
                target_id=node.id,
                source_title="graph",
                target_title=node.label,
                score=_score(0.4 + 0.1 * degree),
                reasons=(REASON_POPULAR,),
            )
            for degree, node in scores[:limit]
        )

    def dashboard(self, *, limit: int = 10) -> dict[str, Any]:
        """Return a combined recommendation payload for the graph view."""
        return {
            "missing_links": [item.as_dict() for item in self.missing_links(limit=limit)],
            "popular": [item.as_dict() for item in self.popular(limit=limit)],
            "notes": len(self.notes()),
            "unresolved": len(self.store.nodes.of_kind(NODE_REFERENCE)),
        }
