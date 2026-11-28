import type { GraphQuery } from "./client";
import type {
  GraphEdgeDto,
  GraphFilterDto,
  GraphLegendDto,
  GraphMetricsDto,
  GraphNodeDto,
  GraphPointDto,
} from "./client";

export type LayoutName = "force" | "circular" | "grid";
export type WorkbenchStatus = "idle" | "loading" | "ready" | "error";

export interface GraphFilterState {
  kinds: string[];
  relations: string[];
  minWeight: number;
  labelContains: string;
}

export interface GraphSnapshotPayload {
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
  legend: GraphLegendDto[];
  metrics: GraphMetricsDto | null;
  filter: GraphFilterDto | null;
  hiddenNodes: number;
  hiddenEdges: number;
  total: number;
}

export interface GraphWorkbenchState {
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
  layout: LayoutName;
  points: Record<string, GraphPointDto>;
  legend: GraphLegendDto[];
  metrics: GraphMetricsDto | null;
  filter: GraphFilterState;
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  status: WorkbenchStatus;
  error: string | null;
  hiddenNodes: number;
  hiddenEdges: number;
  page: number;
  total: number;
  requestCount: number;
}

export type GraphAction =
  | { type: "load-start" }
  | { type: "load-success"; payload: GraphSnapshotPayload }
  | { type: "load-error"; message: string }
  | { type: "set-layout"; layout: LayoutName }
  | { type: "set-points"; points: GraphPointDto[] }
  | { type: "toggle-kind"; kind: string }
  | { type: "toggle-relation"; relation: string }
  | { type: "set-min-weight"; value: number }
  | { type: "set-label"; value: string }
  | { type: "reset-filter" }
  | { type: "select-node"; nodeId: string | null }
  | { type: "hover-node"; nodeId: string | null }
  | { type: "set-page"; page: number }
  | { type: "set-status"; status: WorkbenchStatus };

export interface NodeInspection {
  node: GraphNodeDto;
  degree: number;
  neighbors: string[];
  relations: string[];
  outgoing: number;
  incoming: number;
}

export function clampWeight(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

export function normalizeToken(value: string): string {
  return value.trim().toLowerCase();
}

export function parseLayout(value: string): LayoutName {
  const normalized = normalizeToken(value);
  if (normalized === "circular" || normalized === "grid") return normalized;
  return "force";
}

export function initialFilterState(): GraphFilterState {
  return { kinds: [], relations: [], minWeight: 0, labelContains: "" };
}

export function initialGraphState(): GraphWorkbenchState {
  return {
    nodes: [],
    edges: [],
    layout: "force",
    points: {},
    legend: [],
    metrics: null,
    filter: initialFilterState(),
    selectedNodeId: null,
    hoveredNodeId: null,
    status: "idle",
    error: null,
    hiddenNodes: 0,
    hiddenEdges: 0,
    page: 1,
    total: 0,
    requestCount: 0,
  };
}

function toggle(list: string[], value: string): string[] {
  const token = normalizeToken(value);
  if (!token) return list;
  if (list.includes(token)) return list.filter((item) => item !== token);
  return [...list, token].sort();
}

export function reduceGraph(
  state: GraphWorkbenchState,
  action: GraphAction,
): GraphWorkbenchState {
  switch (action.type) {
    case "load-start":
      return {
        ...state,
        status: "loading",
        error: null,
        requestCount: state.requestCount + 1,
      };
    case "load-success":
      return {
        ...state,
        nodes: action.payload.nodes,
        edges: action.payload.edges,
        legend: action.payload.legend,
        metrics: action.payload.metrics,
        filter: action.payload.filter
          ? fromFilterDto(action.payload.filter)
          : state.filter,
        hiddenNodes: action.payload.hiddenNodes,
        hiddenEdges: action.payload.hiddenEdges,
        total: action.payload.total,
        status: "ready",
        error: null,
        selectedNodeId: null,
        hoveredNodeId: null,
      };
    case "load-error":
      return { ...state, status: "error", error: action.message };
    case "set-layout":
      return { ...state, layout: parseLayout(action.layout) };
    case "set-points": {
      const points: Record<string, GraphPointDto> = {};
      for (const point of action.points) points[point.node_id] = point;
      return { ...state, points };
    }
    case "toggle-kind":
      return {
        ...state,
        filter: {
          ...state.filter,
          kinds: toggle(state.filter.kinds, action.kind),
        },
      };
    case "toggle-relation":
      return {
        ...state,
        filter: {
          ...state.filter,
          relations: toggle(state.filter.relations, action.relation),
        },
      };
    case "set-min-weight":
      return {
        ...state,
        filter: { ...state.filter, minWeight: clampWeight(action.value) },
      };
    case "set-label":
      return {
        ...state,
        filter: { ...state.filter, labelContains: action.value.slice(0, 120) },
      };
    case "reset-filter":
      return { ...state, filter: initialFilterState(), selectedNodeId: null };
    case "select-node":
      return { ...state, selectedNodeId: action.nodeId };
    case "hover-node":
      return { ...state, hoveredNodeId: action.nodeId };
    case "set-page":
      return { ...state, page: Math.max(1, Math.floor(action.page)) };
    case "set-status":
      return { ...state, status: action.status };
    default:
      return state;
  }
}

export function toFilterDto(filter: GraphFilterState): GraphFilterDto {
  return {
    kinds: [...filter.kinds],
    relations: [...filter.relations],
    min_weight: clampWeight(filter.minWeight),
    label_contains: filter.labelContains.trim(),
  };
}

export function fromFilterDto(dto: GraphFilterDto): GraphFilterState {
  return {
    kinds: dto.kinds.map(normalizeToken),
    relations: dto.relations.map(normalizeToken),
    minWeight: clampWeight(dto.min_weight),
    labelContains: dto.label_contains,
  };
}

export function toGraphQuery(state: GraphWorkbenchState): GraphQuery {
  return {
    page: state.page,
    pageSize: 50,
    kinds: state.filter.kinds,
    relations: state.filter.relations,
    minWeight: state.filter.minWeight,
    labelContains: state.filter.labelContains,
    layout: state.layout,
  };
}

export function visibleNodes(state: GraphWorkbenchState): GraphNodeDto[] {
  const kinds = state.filter.kinds;
  const needle = normalizeToken(state.filter.labelContains);
  return state.nodes.filter((node) => {
    if (kinds.length > 0 && !kinds.includes(normalizeToken(node.kind)))
      return false;
    if (needle && !normalizeToken(node.label).includes(needle)) return false;
    return true;
  });
}

export function visibleEdges(state: GraphWorkbenchState): GraphEdgeDto[] {
  const visible = new Set(visibleNodes(state).map((node) => node.id));
  const relations = state.filter.relations;
  return state.edges.filter((edge) => {
    if (!visible.has(edge.source) || !visible.has(edge.target)) return false;
    if (
      relations.length > 0 &&
      !relations.includes(normalizeToken(edge.relation))
    )
      return false;
    return edge.weight >= state.filter.minWeight;
  });
}

export function legendFor(edges: GraphEdgeDto[]): GraphLegendDto[] {
  const grouped = new Map<string, { count: number; total: number }>();
  for (const edge of edges) {
    const relation = normalizeToken(edge.relation);
    const entry = grouped.get(relation) ?? { count: 0, total: 0 };
    entry.count += 1;
    entry.total += edge.weight;
    grouped.set(relation, entry);
  }
  return [...grouped.entries()]
    .map(([relation, entry]) => ({
      relation,
      count: entry.count,
      average_weight: Number((entry.total / entry.count).toFixed(3)),
    }))
    .sort((a, b) => b.count - a.count || a.relation.localeCompare(b.relation));
}

export function uniqueKinds(nodes: GraphNodeDto[]): string[] {
  return [...new Set(nodes.map((node) => normalizeToken(node.kind)))].sort();
}

export function neighborsOf(
  state: GraphWorkbenchState,
  nodeId: string,
): string[] {
  const neighbors = new Set<string>();
  for (const edge of state.edges) {
    if (edge.source === nodeId) neighbors.add(edge.target);
    if (edge.target === nodeId) neighbors.add(edge.source);
  }
  return [...neighbors].sort();
}

export function inspectNode(
  state: GraphWorkbenchState,
  nodeId: string | null,
): NodeInspection | null {
  if (!nodeId) return null;
  const node = state.nodes.find((item) => item.id === nodeId);
  if (!node) return null;
  const relations = new Set<string>();
  let outgoing = 0;
  let incoming = 0;
  for (const edge of state.edges) {
    if (edge.source === nodeId) {
      outgoing += 1;
      relations.add(normalizeToken(edge.relation));
    }
    if (edge.target === nodeId) {
      incoming += 1;
      relations.add(normalizeToken(edge.relation));
    }
  }
  return {
    node,
    degree: outgoing + incoming,
    neighbors: neighborsOf(state, nodeId),
    relations: [...relations].sort(),
    outgoing,
    incoming,
  };
}

export function metricsFromGraph(
  nodes: GraphNodeDto[],
  edges: GraphEdgeDto[],
): GraphMetricsDto {
  const degree: Record<string, number> = {};
  const adjacency = new Map<string, Set<string>>();
  for (const node of nodes) {
    degree[node.id] = 0;
    adjacency.set(node.id, new Set());
  }
  for (const edge of edges) {
    if (!adjacency.has(edge.source) || !adjacency.has(edge.target)) continue;
    degree[edge.source] = (degree[edge.source] ?? 0) + 1;
    degree[edge.target] = (degree[edge.target] ?? 0) + 1;
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }
  const seen = new Set<string>();
  let components = 0;
  for (const node of nodes) {
    if (seen.has(node.id)) continue;
    components += 1;
    const queue = [node.id];
    seen.add(node.id);
    while (queue.length > 0) {
      const current = queue.shift();
      if (!current) continue;
      for (const neighbor of adjacency.get(current) ?? []) {
        if (seen.has(neighbor)) continue;
        seen.add(neighbor);
        queue.push(neighbor);
      }
    }
  }
  const values = Object.values(degree);
  const total = values.reduce((sum, value) => sum + value, 0);
  const possible = nodes.length > 1 ? nodes.length * (nodes.length - 1) : 0;
  return {
    node_count: nodes.length,
    edge_count: edges.length,
    degree,
    component_count: components,
    isolated_count: values.filter((value) => value === 0).length,
    max_degree: values.length ? Math.max(...values) : 0,
    average_degree: values.length
      ? Number((total / values.length).toFixed(4))
      : 0,
    density: possible ? Number(((edges.length * 2) / possible).toFixed(4)) : 0,
  };
}

export function filterSummary(state: GraphWorkbenchState): string {
  const parts: string[] = [];
  if (state.filter.kinds.length)
    parts.push(`kinds: ${state.filter.kinds.join(", ")}`);
  if (state.filter.relations.length)
    parts.push(`relations: ${state.filter.relations.join(", ")}`);
  if (state.filter.minWeight > 0)
    parts.push(`weight ≥ ${state.filter.minWeight.toFixed(2)}`);
  if (state.filter.labelContains)
    parts.push(`label ~ ${state.filter.labelContains}`);
  return parts.length ? parts.join(" · ") : "No filters applied";
}

export function nodeLabel(state: GraphWorkbenchState, nodeId: string): string {
  return (
    state.nodes.find((node) => node.id === nodeId)?.label ?? nodeId.slice(0, 8)
  );
}
