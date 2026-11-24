/** Layout and aggregation helpers for the custody timeline. */

import type {
  CustodyEdgeData,
  CustodyEventData,
  CustodyGraphData,
  CustodyNodeData,
} from "./types";
import { maskHash } from "./format";

export function flattenTimeline(
  graph: CustodyGraphData | null,
): CustodyEventData[] {
  if (!graph) return [];
  return graph.timeline.flatMap((group) => group.events);
}

export function nodeByKey(
  graph: CustodyGraphData | null,
  key: string,
): CustodyNodeData | null {
  return graph?.nodes.find((node) => node.ref === key) ?? null;
}

export function edgesFrom(
  graph: CustodyGraphData | null,
  key: string,
): CustodyEdgeData[] {
  return graph?.edges.filter((edge) => edge.source === key) ?? [];
}

export function custodyColumns(
  graph: CustodyGraphData | null,
): CustodyNodeData[][] {
  if (!graph || graph.nodes.length === 0) return [];
  const maxDepth = Math.max(...graph.nodes.map((node) => node.depth));
  const columns: CustodyNodeData[][] = Array.from(
    { length: maxDepth + 1 },
    () => [],
  );
  for (const node of graph.nodes) {
    const depth = Math.max(0, Math.min(maxDepth, node.depth));
    columns[depth].push(node);
  }
  return columns.map((column) =>
    [...column].sort((a, b) => a.ref.localeCompare(b.ref)),
  );
}

export function actorChains(
  graph: CustodyGraphData | null,
): Record<string, string[]> {
  const chains: Record<string, string[]> = {};
  for (const edge of graph?.edges ?? []) {
    if (edge.label !== "actor") continue;
    const node = nodeByKey(graph, edge.target);
    if (!node) continue;
    (chains[edge.source] ??= []).push(node.label || node.ref);
  }
  return chains;
}

export function custodyIssues(graph: CustodyGraphData | null): string[] {
  if (!graph) return [];
  const issues = [...graph.problems];
  if (!graph.cycle_free) issues.push("Custody graph contains a cycle");
  if (!graph.verified && issues.length === 0)
    issues.push("Custody graph is not verified");
  return issues;
}

export function custodyHeadline(graph: CustodyGraphData | null): string {
  if (!graph) return "No custody data";
  return `${graph.summary.nodes} nodes / ${graph.summary.edges} edges / depth ${graph.summary.depth}`;
}

export function eventHashLabel(event: CustodyEventData): string {
  return maskHash(event.hash, 6);
}

export function eventsForActor(
  graph: CustodyGraphData | null,
  actor: string,
): CustodyEventData[] {
  const needle = actor.trim().toLowerCase();
  if (!needle) return [];
  return flattenTimeline(graph).filter((event) =>
    event.actor.toLowerCase().includes(needle),
  );
}

export function firstTimestamp(graph: CustodyGraphData | null): string {
  const events = flattenTimeline(graph);
  return events.length ? events[0].timestamp : "";
}
