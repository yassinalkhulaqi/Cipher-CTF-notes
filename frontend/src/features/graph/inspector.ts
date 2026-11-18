import { degrees } from "./filters";
import type {
  GraphEdge,
  GraphLinkDetail,
  GraphNode,
  GraphPayload,
  GraphRecommendation,
} from "./types";

export interface InspectorNeighborGroup {
  kind: string;
  nodes: GraphNode[];
}

export interface InspectorModel {
  node: GraphNode;
  edges: GraphEdge[];
  neighbors: InspectorNeighborGroup[];
  degree: number;
  tags: string[];
  links: GraphLinkDetail | null;
  recommendations: GraphRecommendation[];
}

export interface InspectorState {
  selectedId: number | null;
  expanded: Record<string, boolean>;
  showUnresolved: boolean;
}

export function defaultInspectorState(): InspectorState {
  return { selectedId: null, expanded: {}, showUnresolved: true };
}

export function selectInspectorNode(
  state: InspectorState,
  id: number | null,
): InspectorState {
  return { ...state, selectedId: id };
}

export function toggleInspectorSection(
  state: InspectorState,
  key: string,
): InspectorState {
  return {
    ...state,
    expanded: { ...state.expanded, [key]: !state.expanded[key] },
  };
}

export function isSectionExpanded(state: InspectorState, key: string): boolean {
  return state.expanded[key] === true;
}

export function truncateLabel(label: string, length = 32): string {
  const trimmed = label.trim();
  if (trimmed.length <= length) return trimmed;
  return `${trimmed.slice(0, Math.max(1, length - 1)).trimEnd()}…`;
}

export function formatScore(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toFixed(value < 0.1 ? 3 : 2);
}

export function formatCount(
  value: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

export function breadcrumbs(node: GraphNode): string[] {
  if (!node.path) return [node.label];
  return node.path
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean)
    .concat(node.label);
}

export function relatedEdges(
  payload: GraphPayload,
  nodeId: number,
): GraphEdge[] {
  return payload.edges
    .filter((edge) => edge.source === nodeId || edge.target === nodeId)
    .sort((a, b) => {
      const kind = a.kind.localeCompare(b.kind);
      if (kind) return kind;
      const left = a.source === nodeId ? a.target : a.source;
      const right = b.source === nodeId ? b.target : b.source;
      return left - right;
    });
}

export function neighborNodes(
  payload: GraphPayload,
  nodeId: number,
): GraphNode[] {
  const ids = new Set<number>();
  for (const edge of relatedEdges(payload, nodeId)) {
    if (edge.source === nodeId) ids.add(edge.target);
    if (edge.target === nodeId) ids.add(edge.source);
  }
  return payload.nodes
    .filter((node) => ids.has(node.id))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function groupNeighbors(nodes: GraphNode[]): InspectorNeighborGroup[] {
  const groups = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    const key = node.kind;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)?.push(node);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([kind, members]) => ({ kind, nodes: members }));
}

export function inspectorStats(
  payload: GraphPayload,
  nodeId: number,
): Record<string, number> {
  const counts = degrees(payload.nodes, payload.edges);
  const edges = relatedEdges(payload, nodeId);
  return {
    degree: counts.get(nodeId) ?? 0,
    incoming: edges.filter((edge) => edge.target === nodeId).length,
    outgoing: edges.filter((edge) => edge.source === nodeId).length,
    unresolved: edges.filter((edge) => edge.resolved === false).length,
  };
}

export function buildInspectorModel(
  payload: GraphPayload,
  nodeId: number,
  links: GraphLinkDetail | null = null,
  recommendations: GraphRecommendation[] = [],
): InspectorModel | null {
  const node = payload.nodes.find((item) => item.id === nodeId);
  if (!node) return null;
  const edges = relatedEdges(payload, nodeId);
  const neighbors = neighborNodes(payload, nodeId);
  return {
    node,
    edges,
    neighbors: groupNeighbors(neighbors),
    degree: inspectorStats(payload, nodeId).degree,
    tags: (node.tags ?? []).slice(),
    links,
    recommendations: recommendations
      .filter((item) => item.source_id === nodeId || item.target_id === nodeId)
      .sort((a, b) => b.score - a.score || a.target_id - b.target_id),
  };
}

export function recommendationLabel(item: GraphRecommendation): string {
  const direction = item.source_id === 0 ? "Popular" : "Related";
  return `${direction}: ${truncateLabel(item.target_title, 28)}`;
}

export function inspectorTitle(model: InspectorModel | null): string {
  if (!model) return "No selection";
  return model.node.label || `Node ${model.node.id}`;
}

export function nextInspectorSelection(
  state: InspectorState,
  nodes: GraphNode[],
  direction: 1 | -1,
): InspectorState {
  if (!nodes.length) return state;
  const index = nodes.findIndex((node) => node.id === state.selectedId);
  const next = (index + direction + nodes.length) % nodes.length;
  return selectInspectorNode(state, nodes[next].id);
}
