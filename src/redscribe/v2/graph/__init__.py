"""V2 knowledge-graph services."""

from __future__ import annotations

from redscribe.v2.graph.algorithms import (
    CentralityScore,
    ClusteringScore,
    Component,
    Cycle,
    GraphPath,
    adjacency,
    average_clustering,
    betweenness_centrality,
    closeness_centrality,
    clustering_coefficients,
    connected_components,
    degree_centrality,
    detect_communities,
    eigenvector_centrality,
    find_cycles,
    graph_metrics,
    shortest_path,
)
from redscribe.v2.graph.extract import (
    LinkOccurrence,
    TagOccurrence,
    extract_frontmatter,
    extract_inline_tags,
    extract_tags,
    extract_wikilinks,
    normalize_reference,
)
from redscribe.v2.graph.links import LinkDetail, LinkRef, LinkService, UnresolvedRef
from redscribe.v2.graph.model import GraphEdge, GraphModel, GraphNode
from redscribe.v2.graph.recommend import Recommendation, RecommendationService
from redscribe.v2.graph.service import GraphFilters, GraphIntelligenceService
from redscribe.v2.graph.snapshot import (
    GraphSnapshot,
    SnapshotDiff,
    SnapshotMeta,
    SnapshotStore,
    diff_snapshots,
)
from redscribe.v2.graph.store import EdgeStore, GraphStore, NodeStore, build_graph_store

__all__ = [
    "CentralityScore",
    "ClusteringScore",
    "Component",
    "Cycle",
    "EdgeStore",
    "GraphEdge",
    "GraphFilters",
    "GraphIntelligenceService",
    "GraphModel",
    "GraphNode",
    "GraphPath",
    "GraphSnapshot",
    "GraphStore",
    "LinkDetail",
    "LinkOccurrence",
    "LinkRef",
    "LinkService",
    "NodeStore",
    "Recommendation",
    "RecommendationService",
    "SnapshotDiff",
    "SnapshotMeta",
    "SnapshotStore",
    "TagOccurrence",
    "UnresolvedRef",
    "adjacency",
    "average_clustering",
    "betweenness_centrality",
    "build_graph_store",
    "closeness_centrality",
    "clustering_coefficients",
    "connected_components",
    "degree_centrality",
    "detect_communities",
    "diff_snapshots",
    "eigenvector_centrality",
    "extract_frontmatter",
    "extract_inline_tags",
    "extract_tags",
    "extract_wikilinks",
    "find_cycles",
    "graph_metrics",
    "normalize_reference",
    "shortest_path",
]
