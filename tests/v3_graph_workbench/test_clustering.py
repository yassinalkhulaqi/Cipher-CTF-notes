"""Tests for tag, kind, and severity clustering."""

from __future__ import annotations

import pytest

from redscribe.v3.graph_workbench.clustering import (
    CLUSTER_DIMENSIONS,
    ClusterDimension,
    all_clusters,
    cluster_centroids,
    cluster_chips,
    cluster_color,
    cluster_graph,
    cluster_summary,
    filter_by_cluster,
)
from redscribe.v3.graph_workbench.layout import Point
from tests.v3_graph_workbench import build_graph


def test_cluster_dimension_parse() -> None:
    assert ClusterDimension.parse(" TAG ") is ClusterDimension.TAG
    assert ClusterDimension.parse("severity") is ClusterDimension.SEVERITY
    with pytest.raises(ValueError, match="Unknown cluster dimension"):
        ClusterDimension.parse("color")
    assert CLUSTER_DIMENSIONS == ("tag", "kind", "severity")


def test_cluster_color_is_stable() -> None:
    assert cluster_color("alpha") == cluster_color("alpha")
    assert cluster_color("alpha").startswith("#")
    assert len({cluster_color(key) for key in ("alpha", "beta", "gamma")}) >= 2


def test_cluster_by_tag_assigns_primary_tag() -> None:
    graph = build_graph()
    result = cluster_graph(graph, "tag")
    assert result.dimension == "tag"
    assert {cluster.key for cluster in result.clusters} == {"alpha", "beta"}
    assert result.key_for("note:root") == "alpha"
    assert result.key_for("finding:sql-001") == "beta"
    assert result.unassigned == ()
    assert result.cluster_for("note:root") is not None
    assert result.cluster_for("missing") is None
    assert result.key_for("missing") == ""


def test_cluster_by_kind_and_severity() -> None:
    graph = build_graph()
    kinds = cluster_graph(graph, ClusterDimension.KIND)
    assert {cluster.key for cluster in kinds.clusters} == {"note", "finding", "evidence", "target"}
    assert kinds.cluster_for("finding:sql-001").label == "Findings"
    severities = cluster_graph(graph, "severity")
    assert severities.key_for("finding:sql-001") == "critical"
    assert severities.key_for("note:root") == "high"
    assert severities.key_for("target:host-01") == "unknown"


def test_cluster_tag_prefix_filters_namespaced_tags() -> None:
    graph = build_graph()
    result = cluster_graph(graph, "tag", tag_prefix="severity/")
    assert {cluster.key for cluster in result.clusters} == {"severity/high"}
    assert result.key_for("finding:sql-001") == ""
    assert "finding:sql-001" in result.unassigned


def test_clusters_are_size_ordered_and_have_counts() -> None:
    graph = build_graph()
    result = cluster_graph(graph, "tag")
    sizes = [cluster.size for cluster in result.clusters]
    assert sizes == sorted(sizes, reverse=True)
    assert result.clusters[0].kind_counts
    assert result.keys() == tuple(cluster.key for cluster in result.clusters)
    assert len(result) == 2


def test_cluster_chips_and_induced_filtering() -> None:
    graph = build_graph()
    result = cluster_graph(graph, "tag")
    chips = cluster_chips(result, selected="alpha")
    assert chips[0]["selected"] is True
    assert chips[0]["count"] == 2
    assert chips[0]["dimension"] == "tag"
    subset = filter_by_cluster(graph, result, "alpha")
    assert len(subset) == 2
    assert len(filter_by_cluster(graph, result, "")) == len(graph)


def test_cluster_centroids() -> None:
    graph = build_graph()
    result = cluster_graph(graph, "tag")
    positions = {key: Point(10.0, 20.0) for key in graph.node_ids}
    centroids = cluster_centroids(result, positions)
    assert centroids["alpha"] == Point(10.0, 20.0)
    assert set(centroids) == set(result.keys())


def test_all_clusters_and_summary() -> None:
    graph = build_graph()
    results = all_clusters(graph)
    assert set(results) == set(CLUSTER_DIMENSIONS)
    summary = cluster_summary(graph)
    assert tuple(summary["dimensions"]) == CLUSTER_DIMENSIONS
    assert summary["counts"]["tag"] == 2
    assert summary["largest"]["kind"] == "Evidence"


def test_max_clusters_buckets_small_groups() -> None:
    graph = build_graph()
    result = cluster_graph(graph, "kind", max_clusters=2)
    assert len(result) == 2
    assert "other" in {cluster.key for cluster in result.clusters}
    with pytest.raises(ValueError, match="max_clusters"):
        cluster_graph(graph, "kind", max_clusters=0)
