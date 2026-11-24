/** Inspector model building and metadata formatting. */

import type { ClusterResult, GraphNode } from "./types";
import { SEVERITY_COLORS } from "./types";
import type { InspectorModel } from "./types";

export interface EntityDetail {
  entityId: string;
  title: string;
  status: string;
  tags: string[];
  summary: string;
  owner: string;
  createdAt: number;
  updatedAt: number;
  version: number;
  metadata: Record<string, unknown>;
}

export interface InspectorExtra {
  degree: number;
  neighbors: Array<{ id: string; label: string }>;
  clusters: Record<string, string>;
}

export function formatValue(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function formatMetadata(
  metadata: Record<string, unknown>,
): Array<{ key: string; value: string }> {
  return Object.keys(metadata)
    .sort()
    .map((key) => ({ key, value: formatValue(metadata[key]) }));
}

export function severityTone(severity: string): string {
  const known = ["unknown", "info", "low", "medium", "high", "critical"];
  return known.includes(severity) ? severity : "unknown";
}

export function severityColor(severity: string): string {
  return SEVERITY_COLORS[severityTone(severity)] ?? SEVERITY_COLORS.unknown;
}

export function formatTimestamp(timestamp: number): string {
  if (!timestamp || !Number.isFinite(timestamp)) return "—";
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

export function truncateLabel(label: string, length = 42): string {
  const clean = label.replace(/\s+/g, " ").trim();
  return clean.length <= length ? clean : `${clean.slice(0, length - 1)}…`;
}

export function groupNeighbors(
  neighbors: Array<{ id: string; label: string }>,
  nodes: Array<{ id: string; kind: string }>,
): Record<string, Array<{ id: string; label: string }>> {
  const kinds: Record<string, string> = {};
  for (const node of nodes) kinds[node.id] = node.kind;
  const groups: Record<string, Array<{ id: string; label: string }>> = {};
  for (const neighbor of neighbors
    .slice()
    .sort((a, b) => a.id.localeCompare(b.id))) {
    const kind = kinds[neighbor.id] ?? "unknown";
    groups[kind] = [...(groups[kind] ?? []), neighbor];
  }
  return groups;
}

export function buildInspector(
  node: GraphNode,
  entity: EntityDetail | undefined,
  extra: InspectorExtra,
): InspectorModel {
  const metadata = entity?.metadata ?? node.metadata;
  return {
    id: node.id,
    title: entity?.title ?? node.title,
    label: node.label || entity?.title || node.id,
    kind: node.kind,
    severity: node.severity,
    status: entity?.status ?? node.status,
    owner: entity?.owner ?? node.owner,
    summary: entity?.summary ?? node.summary,
    tags: entity?.tags ?? node.tags,
    degree: extra.degree,
    neighbors: extra.neighbors,
    clusters: extra.clusters,
    metadata: formatMetadata(metadata),
    version: entity?.version ?? node.version,
  };
}

export function inspectorSections(model: InspectorModel): string[] {
  const sections = ["identity", "relationships"];
  if (model.tags.length > 0) sections.push("tags");
  if (Object.keys(model.clusters).length > 0) sections.push("clusters");
  if (model.metadata.length > 0) sections.push("metadata");
  return sections;
}

export function clusterMemberships(
  result: ClusterResult | undefined,
  nodeId: string,
): string {
  if (!result) return "—";
  return result.assignments[nodeId] || "unassigned";
}

export function inspectorTitle(model: InspectorModel): string {
  return truncateLabel(model.title || model.label || model.id, 48);
}
