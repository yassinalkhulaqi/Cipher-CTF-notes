"""Deterministic clustering of ranked search results."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from redscribe.v3.search_intel.facets import document_values
from redscribe.v3.search_intel.types import (
    ClusterGroup,
    ClusterStrategy,
    FacetField,
    RankedHit,
)

_MIN_SIMILARITY = 0.05


class _UnionFind:
    """Small union-find used by similarity clustering."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        """Return the representative for an item with path compression."""
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first: int, second: int) -> None:
        """Merge two sets by rank."""
        left = self.find(first)
        right = self.find(second)
        if left == right:
            return
        if self.rank[left] < self.rank[right]:
            left, right = right, left
        self.parent[right] = left
        if self.rank[left] == self.rank[right]:
            self.rank[left] += 1


def jaccard(first: frozenset[str], second: frozenset[str]) -> float:
    """Return the Jaccard similarity of two token sets."""
    if not first and not second:
        return 1.0
    union = first | second
    if not union:
        return 0.0
    return len(first & second) / len(union)


def _similarity_groups(
    hits: Sequence[RankedHit],
    threshold: float,
) -> dict[int, list[int]]:
    union = _UnionFind(len(hits))
    threshold = max(_MIN_SIMILARITY, min(1.0, threshold))
    for index, hit in enumerate(hits):
        for other in range(index + 1, len(hits)):
            if jaccard(hit.doc.tokens, hits[other].doc.tokens) >= threshold:
                union.union(index, other)
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(hits)):
        groups[union.find(index)].append(index)
    return dict(groups)


def _label_for(hits: Sequence[RankedHit], indexes: Sequence[int]) -> str:
    counter: Counter[str] = Counter()
    for index in indexes:
        counter.update(hits[index].doc.tokens)
    if not counter:
        return "ungrouped"
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return "/".join(token for token, _count in ranked[:3])


def cluster_documents(
    hits: Sequence[RankedHit],
    *,
    strategy: ClusterStrategy | str = ClusterStrategy.FIELD,
    field: str = FacetField.KIND.value,
    threshold: float = 0.25,
    max_clusters: int = 12,
    min_size: int = 1,
) -> tuple[ClusterGroup, ...]:
    """Group ranked hits into labeled clusters.

    The ``similarity`` strategy joins documents whose token sets have at least
    ``threshold`` Jaccard overlap. The ``field`` strategy groups by one facet
    field. Results are always ordered by descending size then key so the UI has
    a stable reading order.
    """
    if not hits:
        return ()
    method = strategy if isinstance(strategy, ClusterStrategy) else ClusterStrategy.parse(strategy)
    if method is ClusterStrategy.NONE:
        return (
            ClusterGroup(
                key="all",
                label="All results",
                refs=tuple(hit.ref for hit in hits),
                count=len(hits),
                score=sum(hit.score for hit in hits) / len(hits),
                strategy=method.value,
            ),
        )

    buckets: dict[str, list[RankedHit]] = defaultdict(list)
    if method is ClusterStrategy.FIELD:
        for hit in hits:
            values = document_values(hit.doc, field)
            key = values[0] if values else "(none)"
            buckets[key].append(hit)
    else:
        for indexes in _similarity_groups(hits, threshold).values():
            key = _label_for(hits, indexes)
            buckets[key] = [hits[index] for index in indexes]

    clusters = [
        ClusterGroup(
            key=key,
            label=key.replace("_", " ").title() if method is ClusterStrategy.FIELD else key,
            refs=tuple(hit.ref for hit in members),
            count=len(members),
            score=sum(hit.score for hit in members) / len(members),
            strategy=method.value,
        )
        for key, members in buckets.items()
        if len(members) >= max(1, min_size)
    ]
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.key))
    cap = max(1, max_clusters)
    if len(clusters) <= cap:
        return tuple(clusters)
    kept = clusters[: cap - 1]
    overflow = clusters[cap - 1 :]
    others = [hit for cluster in overflow for hit in cluster.refs]
    kept.append(
        ClusterGroup(
            key="other",
            label="Other",
            refs=tuple(others),
            count=len(others),
            score=sum(cluster.score for cluster in overflow) / len(overflow),
            strategy=method.value,
        )
    )
    return tuple(kept)
