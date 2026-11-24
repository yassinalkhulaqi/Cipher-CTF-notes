"""Result clustering by field and token similarity."""

from __future__ import annotations

import pytest

from redscribe.v3.search_intel.clustering import (
    _UnionFind,
    cluster_documents,
    jaccard,
)
from redscribe.v3.search_intel.ranking import rank_documents
from redscribe.v3.search_intel.types import ClusterStrategy
from tests.v3_search_intel.helpers import build_service


def _hits(query: str = "web"):
    service = build_service()
    return rank_documents(service.index.documents(), service.parse(query))


def test_union_find_transitivity() -> None:
    uf = _UnionFind(5)
    uf.union(0, 1)
    uf.union(1, 2)
    assert uf.find(0) == uf.find(2)
    assert uf.find(3) != uf.find(0)
    uf.union(2, 3)
    assert uf.find(3) == uf.find(0)


def test_jaccard_edges() -> None:
    assert jaccard(frozenset(), frozenset()) == 1.0
    assert jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0
    assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b", "c"})) == pytest.approx(2 / 3)


def test_field_clustering_groups_by_kind() -> None:
    clusters = cluster_documents(_hits(), field="kind")
    assert clusters
    assert all(cluster.strategy == "field" for cluster in clusters)
    assert all(cluster.count == len(cluster.refs) for cluster in clusters)
    assert [cluster.count for cluster in clusters] == sorted(
        (cluster.count for cluster in clusters), reverse=True
    )


def test_field_clustering_by_tag() -> None:
    clusters = cluster_documents(_hits(), field="tag")
    assert any(cluster.key == "web" for cluster in clusters)


def test_similarity_clustering_joins_related_docs() -> None:
    clusters = cluster_documents(_hits(), strategy=ClusterStrategy.SIMILARITY, threshold=0.2)
    assert clusters
    assert all(cluster.strategy == "similarity" for cluster in clusters)
    assert sum(cluster.count for cluster in clusters) == len(_hits())


def test_similarity_threshold_controls_group_count() -> None:
    hits = _hits()
    loose = cluster_documents(hits, strategy="similarity", threshold=0.05)
    strict = cluster_documents(hits, strategy="similarity", threshold=0.95)
    assert len(loose) <= len(strict)


def test_no_clustering_returns_single_group() -> None:
    hits = _hits()
    clusters = cluster_documents(hits, strategy="none")
    assert len(clusters) == 1
    assert clusters[0].count == len(hits)


def test_empty_hits_produce_no_clusters() -> None:
    assert cluster_documents(()) == ()


def test_min_size_filters_small_groups() -> None:
    clusters = cluster_documents(_hits(), field="kind", min_size=100)
    assert clusters == ()


def test_max_clusters_creates_other_bucket() -> None:
    clusters = cluster_documents(_hits(), field="kind", max_clusters=2)
    assert len(clusters) == 2
    assert clusters[-1].key == "other"


def test_clusters_are_deterministic() -> None:
    hits = _hits()
    assert cluster_documents(hits) == cluster_documents(hits)


def test_parse_strategy_falls_back_to_field() -> None:
    clusters = cluster_documents(_hits(), strategy="not-a-strategy")
    assert clusters[0].strategy == "field"
