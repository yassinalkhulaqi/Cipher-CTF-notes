import { centroid, scale, spiralPoint } from "./geometry";
import type { PositionMap } from "./layout";
import type {
  ClusterInfo,
  GraphEdge,
  GraphNode,
  GraphPayload,
  Point,
} from "./types";

export const CLUSTER_COLORS: string[] = [
  "#7dd3fc",
  "#c4b5fd",
  "#fca5a5",
  "#86efac",
  "#fcd34d",
  "#f9a8d4",
  "#5eead4",
  "#fdba74",
];

export type ClusterStrategy = "component" | "tag" | "kind";

export function clusterColor(index: number): string {
  return CLUSTER_COLORS[Math.abs(index) % CLUSTER_COLORS.length];
}

function adjacency(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<number, number[]> {
  const ids = new Set(nodes.map((node) => node.id));
  const map = new Map<number, number[]>();
  for (const node of nodes) map.set(node.id, []);
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
    map.get(edge.source)?.push(edge.target);
    map.get(edge.target)?.push(edge.source);
  }
  return map;
}

export function connectedGroups(
  nodes: GraphNode[],
  edges: GraphEdge[],
): number[][] {
  const links = adjacency(nodes, edges);
  const visited = new Set<number>();
  const groups: number[][] = [];
  for (const node of nodes) {
    if (visited.has(node.id)) continue;
    visited.add(node.id);
    const members: number[] = [];
    const stack = [node.id];
    while (stack.length) {
      const current = stack.pop() as number;
      members.push(current);
      for (const neighbor of links.get(current) ?? []) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        stack.push(neighbor);
      }
    }
    groups.push(members.sort((a, b) => a - b));
  }
  groups.sort((a, b) => b.length - a.length || a[0] - b[0]);
  return groups;
}

function groupByTag(nodes: GraphNode[]): number[][] {
  const groups = new Map<string, number[]>();
  for (const node of nodes) {
    const tags = (node.tags ?? []).map((tag) => tag.toLocaleLowerCase());
    const tag = tags[0] ?? "untagged";
    if (!groups.has(tag)) groups.set(tag, []);
    groups.get(tag)?.push(node.id);
  }
  return [...groups.values()].sort(
    (a, b) => b.length - a.length || a[0] - b[0],
  );
}

function groupByKind(nodes: GraphNode[]): number[][] {
  const groups = new Map<string, number[]>();
  for (const node of nodes) {
    if (!groups.has(node.kind)) groups.set(node.kind, []);
    groups.get(node.kind)?.push(node.id);
  }
  return [...groups.values()].sort(
    (a, b) => b.length - a.length || a[0] - b[0],
  );
}

function labelFor(
  strategy: ClusterStrategy,
  group: number[],
  byId: Map<number, GraphNode>,
): string {
  if (strategy === "kind") {
    return byId.get(group[0])?.kind ?? "mixed";
  }
  if (strategy === "tag") {
    const tags = byId.get(group[0])?.tags ?? [];
    return tags[0] ?? "untagged";
  }
  const first = byId.get(group[0]);
  return first ? `${first.label} +${Math.max(0, group.length - 1)}` : "cluster";
}

export function buildClusters(
  payload: GraphPayload,
  strategy: ClusterStrategy = "component",
): ClusterInfo[] {
  const byId = new Map(payload.nodes.map((node) => [node.id, node]));
  const groups =
    strategy === "tag"
      ? groupByTag(payload.nodes)
      : strategy === "kind"
        ? groupByKind(payload.nodes)
        : connectedGroups(payload.nodes, payload.edges);
  return groups.map((group, index) => ({
    id: index + 1,
    label: labelFor(strategy, group, byId),
    color: clusterColor(index),
    nodeIds: group,
    size: group.length,
    collapsed: false,
  }));
}

export function clusterOf(clusters: ClusterInfo[], nodeId: number): number {
  const cluster = clusters.find((item) => item.nodeIds.includes(nodeId));
  return cluster?.id ?? 0;
}

export function visibleNodeIds(clusters: ClusterInfo[]): Set<number> {
  const ids = new Set<number>();
  for (const cluster of clusters) {
    if (cluster.collapsed) continue;
    for (const id of cluster.nodeIds) ids.add(id);
  }
  return ids;
}

export function toggleCluster(
  clusters: ClusterInfo[],
  id: number,
): ClusterInfo[] {
  return clusters.map((cluster) =>
    cluster.id === id ? { ...cluster, collapsed: !cluster.collapsed } : cluster,
  );
}

export function setClusterCollapsed(
  clusters: ClusterInfo[],
  id: number,
  collapsed: boolean,
): ClusterInfo[] {
  return clusters.map((cluster) =>
    cluster.id === id ? { ...cluster, collapsed } : cluster,
  );
}

export function collapseAll(
  clusters: ClusterInfo[],
  collapsed: boolean,
): ClusterInfo[] {
  return clusters.map((cluster) => ({ ...cluster, collapsed }));
}

export function clusterCentroids(
  clusters: ClusterInfo[],
  positions: PositionMap,
): Map<number, Point> {
  const result = new Map<number, Point>();
  for (const cluster of clusters) {
    const points = cluster.nodeIds
      .map((id) => positions.get(id))
      .filter((point): point is Point => point !== undefined);
    if (points.length) result.set(cluster.id, centroid(points));
  }
  return result;
}

export function spreadClusters(
  clusters: ClusterInfo[],
  positions: PositionMap,
  spacing = 90,
): PositionMap {
  const centers = clusterCentroids(clusters, positions);
  const result: PositionMap = new Map(positions);
  const active = clusters.filter((cluster) => centers.has(cluster.id));
  active.forEach((cluster, index) => {
    const center = centers.get(cluster.id) as Point;
    const offset = spiralPoint(index, spacing);
    for (const id of cluster.nodeIds) {
      const point = result.get(id);
      if (point)
        result.set(id, { x: point.x + offset.x, y: point.y + offset.y });
    }
    centers.set(cluster.id, {
      x: center.x + offset.x,
      y: center.y + offset.y,
    });
  });
  return result;
}

export function clusterSummary(
  clusters: ClusterInfo[],
): Record<string, number> {
  return {
    total: clusters.length,
    collapsed: clusters.filter((cluster) => cluster.collapsed).length,
    nodes: clusters.reduce((total, cluster) => total + cluster.size, 0),
    largest: clusters.reduce((max, cluster) => Math.max(max, cluster.size), 0),
  };
}

export function clusterColorForNode(
  clusters: ClusterInfo[],
  nodeId: number,
): string {
  const cluster = clusters.find((item) => item.nodeIds.includes(nodeId));
  return cluster ? cluster.color : "#94a3b8";
}

export function offsetClusterPoint(
  center: Point,
  index: number,
  total: number,
  radius: number,
): Point {
  if (total <= 1) return center;
  const angle = (index / total) * Math.PI * 2;
  return {
    x: center.x + Math.cos(angle) * radius,
    y: center.y + Math.sin(angle) * radius,
  };
}

export function clusterRadius(size: number): number {
  return Math.max(24, Math.sqrt(Math.max(1, size)) * 18);
}

export function scalePositions(
  positions: PositionMap,
  factor: number,
): PositionMap {
  const result: PositionMap = new Map();
  for (const [id, point] of positions) result.set(id, scale(point, factor));
  return result;
}
