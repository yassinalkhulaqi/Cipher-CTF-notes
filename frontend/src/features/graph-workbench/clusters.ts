/** Clustering helpers for tag, entity-kind, and severity chips. */

import { centroid } from "./geometry";
import type {
  Chip,
  ClusterDimension,
  ClusterInfo,
  ClusterResult,
  GraphPayload,
  Point,
} from "./types";

const PALETTE = [
  "#38bdf8",
  "#a78bfa",
  "#f472b6",
  "#fb7185",
  "#34d399",
  "#fbbf24",
  "#f59e0b",
  "#60a5fa",
  "#94a3b8",
  "#22d3ee",
  "#c084fc",
  "#4ade80",
];

export function clusterColor(key: string): string {
  let value = 0;
  for (let index = 0; index < key.length; index += 1) {
    value = (value * 31 + key.charCodeAt(index)) >>> 0;
  }
  return PALETTE[value % PALETTE.length];
}

function normalizeTags(tags: string[], prefix = ""): string[] {
  const cleanPrefix = prefix.trim().replace(/^#/, "").toLowerCase();
  return tags
    .map((tag) => tag.toLowerCase().replace(/^#+/, ""))
    .filter(
      (tag) =>
        tag.startsWith(cleanPrefix) &&
        (cleanPrefix !== "" || !tag.includes(":")),
    )
    .sort();
}

function severityOf(value: string): string {
  const aliases: Record<string, string> = {
    informational: "info",
    notice: "info",
    moderate: "medium",
    severe: "high",
    urgent: "critical",
  };
  const normalized = aliases[value] ?? value;
  return ["unknown", "info", "low", "medium", "high", "critical"].includes(
    normalized,
  )
    ? normalized
    : "unknown";
}

export function primaryKey(
  graph: GraphPayload,
  id: string,
  dimension: ClusterDimension,
  tagPrefix = "",
): string {
  const node = graph.nodes.find((item) => item.id === id);
  if (!node) return "";
  if (dimension === "tag") return normalizeTags(node.tags, tagPrefix)[0] ?? "";
  if (dimension === "kind") return node.kind;
  return severityOf(node.severity);
}

function labelFor(dimension: ClusterDimension, key: string): string {
  if (dimension === "severity")
    return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  if (dimension === "tag") return key;
  const labels: Record<string, string> = {
    note: "Notes",
    folder: "Folders",
    target: "Targets",
    finding: "Findings",
    evidence: "Evidence",
    playbook: "Playbooks",
    run: "Runs",
    report: "Reports",
    section: "Sections",
    activity: "Activity",
    extension: "Extensions",
    snippet: "Snippets",
  };
  return labels[key] ?? `${key}s`;
}

export function buildClusters(
  graph: GraphPayload,
  dimension: ClusterDimension = "tag",
  tagPrefix = "",
): ClusterResult {
  const assignments: Record<string, string> = {};
  const grouped: Record<string, string[]> = {};
  const unassigned: string[] = [];
  const ids = graph.nodes.map((node) => node.id).sort();
  for (const id of ids) {
    const key = primaryKey(graph, id, dimension, tagPrefix);
    if (!key) {
      unassigned.push(id);
      continue;
    }
    assignments[id] = key;
    grouped[key] = [...(grouped[key] ?? []), id];
  }
  const clusters: ClusterInfo[] = Object.keys(grouped)
    .sort((a, b) => grouped[b].length - grouped[a].length || a.localeCompare(b))
    .map((key) => {
      const counts: Record<string, number> = {};
      for (const id of grouped[key]) {
        const node = graph.nodes.find((item) => item.id === id);
        if (node) counts[node.kind] = (counts[node.kind] ?? 0) + 1;
      }
      return {
        key,
        label: labelFor(dimension, key),
        dimension,
        nodeIds: grouped[key].slice().sort(),
        color: clusterColor(key),
        size: grouped[key].length,
        kindCounts: counts,
      };
    });
  return {
    dimension,
    clusters,
    assignments: Object.fromEntries(Object.entries(assignments).sort()),
    unassigned,
  };
}

export function clusterChips(result: ClusterResult, selected = ""): Chip[] {
  return result.clusters.map((cluster) => ({
    key: cluster.key,
    label: cluster.label,
    count: cluster.size,
    color: cluster.color,
    dimension: result.dimension,
    selected: cluster.key === selected,
  }));
}

export function filterByCluster(
  graph: GraphPayload,
  result: ClusterResult,
  key: string,
): GraphPayload {
  if (!key) return graph;
  const members = new Set(
    Object.entries(result.assignments)
      .filter(([, value]) => value === key)
      .map(([id]) => id),
  );
  return {
    nodes: graph.nodes.filter((node) => members.has(node.id)),
    edges: graph.edges.filter(
      (edge) => members.has(edge.source) && members.has(edge.target),
    ),
  };
}

export function clusterCentroids(
  result: ClusterResult,
  positions: Record<string, Point>,
): Record<string, Point> {
  const output: Record<string, Point> = {};
  for (const cluster of result.clusters) {
    const points = cluster.nodeIds.map((id) => positions[id]).filter(Boolean);
    if (points.length > 0) output[cluster.key] = centroid(points);
  }
  return output;
}

export function clusterSummary(graph: GraphPayload): Record<string, number> {
  const dimensions: ClusterDimension[] = ["tag", "kind", "severity"];
  const summary: Record<string, number> = {};
  for (const dimension of dimensions) {
    summary[dimension] = buildClusters(graph, dimension).clusters.length;
  }
  return summary;
}

export function clusterOf(
  result: ClusterResult,
  id: string,
): ClusterInfo | undefined {
  const key = result.assignments[id];
  return result.clusters.find((cluster) => cluster.key === key);
}

export function isClusterDimension(value: string): value is ClusterDimension {
  return value === "tag" || value === "kind" || value === "severity";
}
