/** Pivot chip grouping, scoring, and query construction. */

import type { PivotContextV2, PivotSuggestionV2 } from "./types";

const ROLE_LABELS: Record<string, string> = {
  report: "Report",
  evidences: "Evidence",
  owns: "Owns",
  derives: "Derived from",
  contains: "Contains",
  references: "References",
  relates: "Related",
  sibling: "Nearby",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role.toLowerCase()] ?? role;
}

export function roleTone(role: string): string {
  if (role === "report" || role === "references") return "info";
  if (role === "evidences" || role === "owns") return "good";
  if (role === "relates" || role === "sibling") return "neutral";
  return "accent";
}

export function groupPivotsByRole(
  pivots: PivotSuggestionV2[],
): Array<{ role: string; items: PivotSuggestionV2[] }> {
  const grouped = new Map<string, PivotSuggestionV2[]>();
  for (const pivot of pivots) {
    const items = grouped.get(pivot.role) ?? [];
    items.push(pivot);
    grouped.set(pivot.role, items);
  }
  return Array.from(grouped, ([role, items]) => ({ role, items })).sort(
    (a, b) => b.items.length - a.items.length || a.role.localeCompare(b.role),
  );
}

export function pivotQuery(pivot: PivotSuggestionV2): string {
  return pivot.query || `kind:${pivot.kind}`;
}

export function topPivots(
  context: PivotContextV2 | undefined,
  limit = 6,
): PivotSuggestionV2[] {
  if (!context) return [];
  return [...context.pivots]
    .sort((a, b) => b.score - a.score || a.ref.localeCompare(b.ref))
    .slice(0, limit);
}

export function pivotDestinationCounts(
  context: PivotContextV2 | undefined,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const pivot of context?.pivots ?? []) {
    counts[pivot.kind] = (counts[pivot.kind] ?? 0) + 1;
  }
  return counts;
}

export function pivotChipLabel(pivot: PivotSuggestionV2): string {
  const label = pivot.label || pivot.ref;
  return `${roleLabel(pivot.role)}: ${label}`;
}
