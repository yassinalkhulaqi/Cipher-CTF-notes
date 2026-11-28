import { V4_ROUTES } from "./routes";
import type { V4Route } from "./types-v4";

export interface ApiExplorerEntry {
  route: V4Route;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  summary: string;
}

const METHOD_BY_NAME: Record<string, ApiExplorerEntry["method"]> = {
  inbox: "POST",
  findings: "POST",
  "evidence-lab": "GET",
  "blocks-pro": "PUT",
  query: "POST",
  automation: "POST",
  "report-designer": "POST",
  "graph-workbench": "GET",
  "security-vault": "POST",
  "a11y-i18n": "GET",
};

function summaryFor(route: V4Route): string {
  return `${route.label} endpoint for the v4 ${route.name} feature slice.`;
}

export function apiExplorerEntries(): ApiExplorerEntry[] {
  return V4_ROUTES.map((route) => ({
    route,
    method: METHOD_BY_NAME[route.name] ?? "GET",
    summary: summaryFor(route),
  }));
}

export function groupByMethod(
  entries: ApiExplorerEntry[],
): Record<string, ApiExplorerEntry[]> {
  const groups: Record<string, ApiExplorerEntry[]> = {};
  for (const entry of entries) {
    groups[entry.method] = [...(groups[entry.method] ?? []), entry];
  }
  return groups;
}

export function formatCurl(entry: ApiExplorerEntry): string {
  const path = `/api/v4/${entry.route.name}`;
  if (entry.method === "GET") return `curl -s localhost:8000${path}`;
  return `curl -s -X ${entry.method} -H 'Content-Type: application/json' localhost:8000${path}`;
}
