export type GraphNodeKind = "note" | "folder" | "reference" | "tag";
export type GraphEdgeKind = "parent" | "link" | "tag" | "mention";
export type GraphStatus = "todo" | "active" | "done" | "blocked";
export type LayoutKind = "force" | "circle" | "grid" | "radial" | "tree";

export interface GraphNode {
  id: number;
  label: string;
  title?: string;
  kind: GraphNodeKind;
  path?: string;
  tags?: string[];
  status?: GraphStatus | string;
  pinned?: boolean;
  resolved?: boolean;
  weight?: number;
  metadata?: Record<string, unknown>;
}

export interface GraphEdge {
  source: number;
  target: number;
  kind: GraphEdgeKind;
  weight?: number;
  resolved?: boolean;
  alias?: string;
  metadata?: Record<string, unknown>;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats?: Record<string, number>;
}

export interface GraphLayoutPayload extends GraphPayload {
  meta?: Record<string, unknown>;
}

export interface GraphMetrics {
  nodes: number;
  edges: number;
  density: number;
  components: number;
  largest_component: number;
  average_degree: number;
  average_clustering: number;
  cycles: number;
}

export interface GraphOverview {
  stats: Record<string, number>;
  metrics: GraphMetrics;
  tags: string[];
  snapshot_count?: number;
}

export interface GraphFilterState {
  query: string;
  kinds: GraphNodeKind[];
  tags: string[];
  statuses: string[];
  maxNodes: number;
}

export interface ClusterInfo {
  id: number;
  label: string;
  color: string;
  nodeIds: number[];
  size: number;
  collapsed: boolean;
}

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface Rect extends Point, Size {}

export interface Viewport {
  x: number;
  y: number;
  scale: number;
}

export interface PositionedNode {
  id: number;
  node: GraphNode;
  position: Point;
  cluster: number;
}

export interface LayoutOptions {
  kind: LayoutKind;
  seed: number;
  width: number;
  height: number;
  iterations: number;
  linkDistance: number;
  repulsion: number;
  centerGravity: number;
}

export interface GraphPathPayload {
  node_ids?: number[];
  labels?: string[];
  edges?: Array<Array<string | number>>;
  cost: number;
  hops: number;
}

export interface GraphLinkRef {
  node_id: number;
  title: string;
  path?: string;
  status?: string;
  alias?: string;
  snippet?: string;
  line?: number;
}

export interface GraphLinkDetail {
  node_id: number;
  backlinks: GraphLinkRef[];
  outlinks: GraphLinkRef[];
  unresolved: Array<Record<string, unknown>>;
  in_degree: number;
  out_degree: number;
}

export interface GraphRecommendation {
  source_id: number;
  target_id: number;
  source_title: string;
  target_title: string;
  score: number;
  reasons: string[];
  kind: string;
}

export interface GraphSnapshotMeta {
  id: string;
  label: string;
  created_at: string;
  node_count: number;
  edge_count: number;
  digest: string;
  source: string;
}

export const GRAPH_NODE_KINDS: GraphNodeKind[] = [
  "note",
  "folder",
  "reference",
  "tag",
];

export const GRAPH_EDGE_KINDS: GraphEdgeKind[] = [
  "parent",
  "link",
  "tag",
  "mention",
];

export const DEFAULT_FILTERS: GraphFilterState = {
  query: "",
  kinds: [],
  tags: [],
  statuses: [],
  maxNodes: 0,
};

export const DEFAULT_LAYOUT: LayoutOptions = {
  kind: "force",
  seed: 1,
  width: 900,
  height: 620,
  iterations: 180,
  linkDistance: 110,
  repulsion: 9000,
  centerGravity: 0.012,
};
