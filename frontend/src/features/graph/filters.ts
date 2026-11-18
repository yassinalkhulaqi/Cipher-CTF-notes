import type {
  GraphEdge,
  GraphFilterState,
  GraphNode,
  GraphPayload,
} from "./types";
import { DEFAULT_FILTERS, GRAPH_EDGE_KINDS } from "./types";

export function normalizeQuery(value: string): string {
  return value.trim().toLocaleLowerCase();
}

export function normalizeTags(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const tag = value.trim().replace(/^#/, "").toLocaleLowerCase();
    if (!tag || seen.has(tag)) continue;
    seen.add(tag);
    result.push(tag);
  }
  return result;
}

export function withFilterDefaults(
  partial: Partial<GraphFilterState> = {},
): GraphFilterState {
  return {
    ...DEFAULT_FILTERS,
    ...partial,
    kinds: partial.kinds ? [...partial.kinds] : [],
    tags: normalizeTags(partial.tags ?? []),
    statuses: [...(partial.statuses ?? [])],
  };
}

export function nodeMatches(
  node: GraphNode,
  filters: GraphFilterState,
): boolean {
  if (filters.kinds.length && !filters.kinds.includes(node.kind)) return false;
  if (filters.statuses.length) {
    const status = String(node.status ?? "");
    if (!filters.statuses.includes(status)) return false;
  }
  if (filters.tags.length) {
    const tags = normalizeTags(node.tags ?? []);
    if (!filters.tags.some((tag) => tags.includes(tag))) return false;
  }
  const query = normalizeQuery(filters.query);
  if (query) {
    const haystack = [
      node.label,
      node.title ?? "",
      node.path ?? "",
      ...(node.tags ?? []),
    ]
      .join(" ")
      .toLocaleLowerCase();
    if (!haystack.includes(query)) return false;
  }
  return true;
}

export function filterNodes(
  nodes: GraphNode[],
  filters: GraphFilterState,
): GraphNode[] {
  const limited = filters.maxNodes > 0 ? filters.maxNodes : nodes.length;
  const result: GraphNode[] = [];
  for (const node of nodes) {
    if (!nodeMatches(node, filters)) continue;
    result.push(node);
    if (result.length >= limited) break;
  }
  return result;
}

export function filterGraph(
  payload: GraphPayload,
  filters: GraphFilterState,
): GraphPayload {
  const nodes = filterNodes(payload.nodes, filters);
  const ids = new Set(nodes.map((node) => node.id));
  const kinds = new Set<string>(
    Array.isArray(filters.kinds) ? filters.kinds : [],
  );
  const edges = payload.edges.filter((edge) => {
    if (!ids.has(edge.source) || !ids.has(edge.target)) return false;
    if (kinds.size && !kinds.has(edge.kind)) {
      return edge.kind === "link" && kinds.has("note");
    }
    return true;
  });
  return { ...payload, nodes, edges };
}

export function degrees(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<number, number> {
  const result = new Map<number, number>();
  for (const node of nodes) result.set(node.id, 0);
  for (const edge of edges) {
    result.set(edge.source, (result.get(edge.source) ?? 0) + 1);
    result.set(edge.target, (result.get(edge.target) ?? 0) + 1);
  }
  return result;
}

export function sortByDegree(
  nodes: GraphNode[],
  edges: GraphEdge[],
): GraphNode[] {
  const counts = degrees(nodes, edges);
  return [...nodes].sort((a, b) => {
    const difference = (counts.get(b.id) ?? 0) - (counts.get(a.id) ?? 0);
    return difference || a.id - b.id;
  });
}

export function reachableFrom(
  payload: GraphPayload,
  start: number,
  depth: number,
  kinds?: string[],
): GraphPayload {
  const allowed = new Set(kinds ?? GRAPH_EDGE_KINDS);
  const byId = new Map(payload.nodes.map((node) => [node.id, node]));
  const map = new Map<number, number[]>();
  for (const edge of payload.edges) {
    if (
      !allowed.has(edge.kind) ||
      !byId.has(edge.source) ||
      !byId.has(edge.target)
    )
      continue;
    if (!map.has(edge.source)) map.set(edge.source, []);
    if (!map.has(edge.target)) map.set(edge.target, []);
    map.get(edge.source)?.push(edge.target);
    map.get(edge.target)?.push(edge.source);
  }
  const visited = new Set<number>([start]);
  let frontier = [start];
  for (let step = 0; step < Math.max(0, depth); step += 1) {
    const next: number[] = [];
    for (const id of frontier) {
      for (const neighbor of map.get(id) ?? []) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        next.push(neighbor);
      }
    }
    frontier = next;
  }
  return {
    nodes: payload.nodes.filter((node) => visited.has(node.id)),
    edges: payload.edges.filter(
      (edge) =>
        visited.has(edge.source) &&
        visited.has(edge.target) &&
        allowed.has(edge.kind),
    ),
  };
}

export function activeFilterCount(filters: GraphFilterState): number {
  let count = 0;
  if (normalizeQuery(filters.query)) count += 1;
  if (filters.kinds.length) count += 1;
  if (filters.tags.length) count += 1;
  if (filters.statuses.length) count += 1;
  if (filters.maxNodes > 0) count += 1;
  return count;
}

export function filterSummary(filters: GraphFilterState): string {
  const parts: string[] = [];
  if (normalizeQuery(filters.query))
    parts.push(`query: ${filters.query.trim()}`);
  if (filters.kinds.length) parts.push(`kinds: ${filters.kinds.join(", ")}`);
  if (filters.tags.length) parts.push(`tags: ${filters.tags.join(", ")}`);
  if (filters.statuses.length)
    parts.push(`status: ${filters.statuses.join(", ")}`);
  if (filters.maxNodes > 0) parts.push(`max: ${filters.maxNodes}`);
  return parts.join(" · ") || "All notes";
}

export function toggleValue<T>(values: T[], value: T): T[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

export function edgeKindCounts(edges: GraphEdge[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const edge of edges) {
    const key = edge.resolved === false ? `${edge.kind}:unresolved` : edge.kind;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}
