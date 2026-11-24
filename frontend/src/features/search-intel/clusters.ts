/** Client-side cluster grouping and labels. */

import type { ClusterGroupV2, RankedHitV2, SearchResultGroupV2 } from "./types";

export function groupHitsByCluster(
  hits: RankedHitV2[],
  clusters: ClusterGroupV2[],
): SearchResultGroupV2[] {
  const byRef = new Map(hits.map((hit) => [hit.document.ref, hit]));
  return clusters.map((cluster) => ({
    key: cluster.key,
    label: cluster.label,
    count: cluster.count,
    score: cluster.score,
    hits: cluster.refs
      .map((ref) => byRef.get(ref))
      .filter((hit): hit is RankedHitV2 => hit !== undefined),
  }));
}

export function ungroupedHits(hits: RankedHitV2[]): SearchResultGroupV2 {
  return {
    key: "all",
    label: "All results",
    count: hits.length,
    score:
      hits.reduce((total, hit) => total + hit.score, 0) / (hits.length || 1),
    hits,
  };
}

export function clusterTone(key: string): string {
  const known: Record<string, string> = {
    finding: "bad",
    evidence: "good",
    report: "info",
    note: "accent",
    other: "muted",
  };
  return known[key.toLowerCase()] ?? "neutral";
}

export function totalClusterCount(clusters: ClusterGroupV2[]): number {
  return clusters.reduce((total, cluster) => total + cluster.count, 0);
}

export function largestCluster(
  clusters: ClusterGroupV2[],
): ClusterGroupV2 | undefined {
  return clusters.reduce<ClusterGroupV2 | undefined>(
    (best, cluster) => (!best || cluster.count > best.count ? cluster : best),
    undefined,
  );
}

export function clusterSummary(cluster: ClusterGroupV2): string {
  return `${cluster.label} · ${cluster.count} result${cluster.count === 1 ? "" : "s"}`;
}
