import type {
  GraphEdge,
  GraphNode,
  GraphPathPayload,
  GraphPayload,
} from "./types";
import { GRAPH_EDGE_KINDS } from "./types";

export interface PathOptions {
  directed?: boolean;
  weighted?: boolean;
  kinds?: string[];
}

interface AdjacencyEntry {
  id: number;
  weight: number;
  edge: GraphEdge;
}

export type AdjacencyMap = Map<number, AdjacencyEntry[]>;

export function buildAdjacency(
  payload: GraphPayload,
  options: PathOptions = {},
): AdjacencyMap {
  const kinds = new Set(options.kinds ?? GRAPH_EDGE_KINDS);
  const map: AdjacencyMap = new Map();
  for (const node of payload.nodes) map.set(node.id, []);
  for (const edge of payload.edges) {
    if (!kinds.has(edge.kind) || !map.has(edge.source) || !map.has(edge.target))
      continue;
    const weight = Math.max(0.0001, edge.weight ?? 1);
    map.get(edge.source)?.push({ id: edge.target, weight, edge });
    if (!options.directed) {
      map.get(edge.target)?.push({ id: edge.source, weight, edge });
    }
  }
  for (const entries of map.values()) {
    entries.sort(
      (a, b) => a.id - b.id || a.edge.kind.localeCompare(b.edge.kind),
    );
  }
  return map;
}

export function depthMap(
  payload: GraphPayload,
  source: number,
  options: PathOptions = {},
): Map<number, number> {
  const map = buildAdjacency(payload, options);
  const depth = new Map<number, number>([[source, 0]]);
  const queue = [source];
  let cursor = 0;
  while (cursor < queue.length) {
    const current = queue[cursor];
    cursor += 1;
    const currentDepth = depth.get(current) ?? 0;
    for (const neighbor of map.get(current) ?? []) {
      if (depth.has(neighbor.id)) continue;
      depth.set(neighbor.id, currentDepth + 1);
      queue.push(neighbor.id);
    }
  }
  return depth;
}

export function findGraphPath(
  payload: GraphPayload,
  source: number,
  target: number,
  options: PathOptions = {},
): GraphPathPayload | null {
  const map = buildAdjacency(payload, options);
  if (!map.has(source) || !map.has(target)) return null;
  if (source === target) {
    const node = payload.nodes.find((item) => item.id === source);
    return {
      node_ids: [source],
      labels: [node?.label ?? String(source)],
      edges: [],
      cost: 0,
      hops: 0,
    };
  }
  const costs = new Map<number, number>([[source, 0]]);
  const previous = new Map<number, number>();
  const previousEdges = new Map<number, GraphEdge>();
  const visited = new Set<number>();
  while (visited.size < map.size) {
    let current = -1;
    let best = Infinity;
    for (const [id, cost] of costs) {
      if (!visited.has(id) && cost < best) {
        best = cost;
        current = id;
      }
    }
    if (current < 0) break;
    if (current === target) break;
    visited.add(current);
    for (const neighbor of map.get(current) ?? []) {
      if (visited.has(neighbor.id)) continue;
      const step = options.weighted ? 1 / neighbor.weight : 1;
      const candidate = best + step;
      if (candidate >= (costs.get(neighbor.id) ?? Infinity)) continue;
      costs.set(neighbor.id, candidate);
      previous.set(neighbor.id, current);
      previousEdges.set(neighbor.id, neighbor.edge);
    }
  }
  if (!previous.has(target)) return null;
  const ids: number[] = [target];
  const edges: GraphEdge[] = [];
  let cursor = target;
  while (cursor !== source) {
    const parent = previous.get(cursor);
    const edge = previousEdges.get(cursor);
    if (parent === undefined || !edge) return null;
    edges.unshift(edge);
    ids.unshift(parent);
    cursor = parent;
  }
  const byId = new Map(payload.nodes.map((node) => [node.id, node]));
  return {
    node_ids: ids,
    labels: ids.map((id) => byId.get(id)?.label ?? String(id)),
    edges: edges.map((edge) => [edge.source, edge.target, edge.kind]),
    cost: Math.round((costs.get(target) ?? 0) * 1000) / 1000,
    hops: ids.length - 1,
  };
}

export function pathNodeIds(path: GraphPathPayload | null): Set<number> {
  return new Set(path?.node_ids ?? []);
}

export function pathEdgeKeys(path: GraphPathPayload | null): Set<string> {
  const keys = new Set<string>();
  for (const edge of path?.edges ?? []) {
    const [source, target, kind] = edge;
    keys.add(`${source}:${target}:${kind ?? "link"}`);
  }
  return keys;
}

export function pathLabel(
  path: GraphPathPayload | null,
  separator = " → ",
): string {
  if (!path || !path.labels?.length) return "No path";
  return path.labels.join(separator);
}

export function formatHop(index: number, total: number): string {
  if (total <= 1) return "direct";
  return `${index + 1}/${total - 1} hops`;
}

export function pathSummary(
  path: GraphPathPayload | null,
): Record<string, number | string> {
  if (!path) return { hops: 0, cost: 0, status: "disconnected" };
  return {
    hops: path.hops,
    cost: path.cost,
    nodes: path.node_ids?.length ?? 0,
    status: path.hops === 0 ? "same node" : "connected",
  };
}

export function pushPathHistory(
  history: GraphPathPayload[],
  path: GraphPathPayload | null,
  limit = 8,
): GraphPathPayload[] {
  if (!path || !path.node_ids?.length) return history;
  const signature = path.node_ids.join(":");
  const filtered = history.filter(
    (item) => (item.node_ids ?? []).join(":") !== signature,
  );
  return [path, ...filtered].slice(0, Math.max(1, limit));
}

export function pathEndpointLabels(path: GraphPathPayload | null): {
  source: string;
  target: string;
} {
  const labels = path?.labels ?? [];
  return {
    source: labels[0] ?? "—",
    target: labels[labels.length - 1] ?? "—",
  };
}

export function reachableCount(payload: GraphPayload, source: number): number {
  return depthMap(payload, source).size;
}

export function nodeById(payload: GraphPayload, id: number): GraphNode | null {
  return payload.nodes.find((node) => node.id === id) ?? null;
}

export function pathKinds(path: GraphPathPayload | null): string[] {
  const kinds = new Set<string>();
  for (const edge of path?.edges ?? []) {
    const kind = edge[2];
    if (typeof kind === "string") kinds.add(kind);
  }
  return [...kinds].sort();
}
