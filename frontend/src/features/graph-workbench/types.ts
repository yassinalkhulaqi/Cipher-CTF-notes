/** Wire types and constants for the V3 graph workbench feature. */

import type { EntityKind, EntityRef, LinkKind } from "../../v3/types";

export interface GraphNode {
  id: string;
  ref: EntityRef;
  title: string;
  label: string;
  kind: EntityKind | string;
  tags: string[];
  severity: string;
  status: string;
  owner: string;
  summary: string;
  metadata: Record<string, unknown>;
  timestamp: number;
  version: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: LinkKind | string;
  label: string;
  weight: number;
  metadata: Record<string, unknown>;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export type LayoutKind = "force" | "hierarchical" | "radial" | "timeline";

export const LAYOUT_KINDS: LayoutKind[] = [
  "force",
  "hierarchical",
  "radial",
  "timeline",
];

export const LAYOUT_LABELS: Record<LayoutKind, string> = {
  force: "Force",
  hierarchical: "Hierarchy",
  radial: "Radial",
  timeline: "Timeline",
};

export const LAYOUT_HINTS: Record<LayoutKind, string> = {
  force: "Relationship repulsion with seeded jitter",
  hierarchical: "Dependency layers from source to target",
  radial: "Concentric rings around the hub entity",
  timeline: "Chronological lanes grouped by kind",
};

export interface LayoutOptions {
  seed: number;
  width: number;
  height: number;
  padding: number;
  iterations: number;
  sampleSize: number;
  direction: "LR" | "TB";
  root: string;
  timeKey: string;
  laneHeight: number;
}

export const DEFAULT_LAYOUT_OPTIONS: LayoutOptions = {
  seed: 1,
  width: 1200,
  height: 760,
  padding: 48,
  iterations: 24,
  sampleSize: 16,
  direction: "LR",
  root: "",
  timeKey: "timestamp",
  laneHeight: 88,
};

export interface LayoutResult {
  strategy: string;
  seed: number;
  width: number;
  height: number;
  center: string;
  positions: Record<string, Point>;
}

export type ClusterDimension = "tag" | "kind" | "severity";

export const CLUSTER_DIMENSIONS: ClusterDimension[] = [
  "tag",
  "kind",
  "severity",
];

export const CLUSTER_LABELS: Record<ClusterDimension, string> = {
  tag: "Tag",
  kind: "Entity",
  severity: "Severity",
};

export interface ClusterInfo {
  key: string;
  label: string;
  dimension: string;
  nodeIds: string[];
  color: string;
  size: number;
  kindCounts: Record<string, number>;
}

export interface ClusterResult {
  dimension: string;
  clusters: ClusterInfo[];
  assignments: Record<string, string>;
  unassigned: string[];
}

export interface Chip {
  key: string;
  label: string;
  count: number;
  color: string;
  dimension: string;
  selected: boolean;
}

export interface PathStep {
  index: number;
  source: string;
  target: string;
  kind: string;
  label: string;
  weight: number;
  direction: "forward" | "reverse";
  explanation: string;
}

export interface PathResult {
  source: string;
  target: string;
  found: boolean;
  nodeIds: string[];
  steps: PathStep[];
  explanations: string[];
  hops: number;
  cost: number;
  directed: boolean;
  weighted: boolean;
  maxHops: number | null;
}

export interface CutVertex {
  nodeId: string;
  label: string;
  componentCount: number;
  isolatedCount: number;
  fragments: string[][];
  severity: string;
}

export interface Bridge {
  source: string;
  target: string;
  kind: string;
  key: [string, string, string];
}

export interface Component {
  index: number;
  nodeIds: string[];
  size: number;
}

export interface ArticulationResult {
  cutVertices: CutVertex[];
  bridges: Bridge[];
  components: Component[];
  summary: {
    nodes: number;
    edges: number;
    components: number;
    largestComponent: number;
    isolated: number;
    cutVertices: number;
    bridges: number;
    averageDegree: number;
    density: number;
  };
}

export interface SnapshotMeta {
  id: string;
  label: string;
  createdAt: string;
  nodeCount: number;
  edgeCount: number;
  digest: string;
  source: string;
  sequence: number;
}

export interface SnapshotRecord {
  meta: SnapshotMeta;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
}

export interface SnapshotDiff {
  leftId: string;
  rightId: string;
  addedNodes: string[];
  removedNodes: string[];
  changedNodes: string[];
  addedEdges: string[][];
  removedEdges: string[][];
  changedEdges: string[][];
  changed: boolean;
  totalChanges: number;
}

export interface EditRecord {
  sequence: number;
  action: string;
  link: GraphEdge;
  inverse: Partial<GraphEdge>;
  timestamp: number;
  actor: string;
}

export interface RelationshipDraft {
  source: string;
  target: string;
  kind: string;
  label: string;
  weight: number;
}

export const EMPTY_DRAFT: RelationshipDraft = {
  source: "",
  target: "",
  kind: "relates",
  label: "",
  weight: 1,
};

export const LINK_KINDS: string[] = [
  "contains",
  "relates",
  "evidences",
  "derives",
  "references",
  "duplicates",
  "supersedes",
];

export const SEVERITY_LEVELS: string[] = [
  "unknown",
  "info",
  "low",
  "medium",
  "high",
  "critical",
];

export const KIND_COLORS: Record<string, string> = {
  note: "#38bdf8",
  folder: "#a78bfa",
  target: "#f472b6",
  finding: "#fb7185",
  evidence: "#34d399",
  playbook: "#fbbf24",
  run: "#f59e0b",
  report: "#60a5fa",
  section: "#94a3b8",
  activity: "#22d3ee",
  extension: "#c084fc",
  snippet: "#4ade80",
};

export const SEVERITY_COLORS: Record<string, string> = {
  unknown: "#64748b",
  info: "#38bdf8",
  low: "#4ade80",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#fb7185",
};

export interface InspectorModel {
  id: string;
  title: string;
  label: string;
  kind: string;
  severity: string;
  status: string;
  owner: string;
  summary: string;
  tags: string[];
  degree: number;
  neighbors: Array<{ id: string; label: string }>;
  clusters: Record<string, string>;
  metadata: Array<{ key: string; value: string }>;
  version: number;
}

export interface Viewport {
  x: number;
  y: number;
  width: number;
  height: number;
  zoom: number;
}

export function isGraphPayload(value: unknown): value is GraphPayload {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return Array.isArray(candidate.nodes) && Array.isArray(candidate.edges);
}

export function layoutOptionsFrom(
  overrides: Partial<LayoutOptions> = {},
): LayoutOptions {
  return { ...DEFAULT_LAYOUT_OPTIONS, ...overrides };
}
