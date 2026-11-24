/** Facet selection helpers for the search intelligence sidebar. */

import type { FacetCountV2, FacetResultV2, SavedFacetSetV2 } from "./types";

export type FacetSelection = Record<string, string[]>;

export function selectedValues(
  selection: FacetSelection,
  field: string,
): string[] {
  return selection[field] ?? [];
}

export function toggleFacetValue(
  selection: FacetSelection,
  field: string,
  value: string,
): FacetSelection {
  const current = selectedValues(selection, field);
  const folded = value.toLowerCase();
  const next = current.some((item) => item.toLowerCase() === folded)
    ? current.filter((item) => item.toLowerCase() !== folded)
    : [...current, value];
  const updated = { ...selection };
  if (next.length) updated[field] = next;
  else delete updated[field];
  return updated;
}

export function clearFacets(): FacetSelection {
  return {};
}

export function facetSelectionCount(selection: FacetSelection): number {
  return Object.values(selection).reduce(
    (total, values) => total + values.length,
    0,
  );
}

export function mergeFacetResult(
  facet: FacetResultV2,
  selection: FacetSelection,
): FacetResultV2 {
  const chosen = selectedValues(selection, facet.field);
  return {
    ...facet,
    values: facet.values.map((value: FacetCountV2) => ({
      ...value,
      selected: chosen.some(
        (item) => item.toLowerCase() === value.value.toLowerCase(),
      ),
    })),
  };
}

export function facetDisplayCount(facet: FacetResultV2): number {
  return facet.values.reduce((total, value) => total + value.count, 0);
}

export function sortFacetValues(facet: FacetResultV2): FacetCountV2[] {
  return [...facet.values].sort(
    (a, b) => b.count - a.count || a.value.localeCompare(b.value),
  );
}

export function facetSetFields(set: SavedFacetSetV2 | undefined): string[] {
  return set
    ? [...new Set(set.fields.map((field) => field.toLowerCase()))]
    : [];
}

export function selectionFromQuery(query: string): FacetSelection {
  const selection: FacetSelection = {};
  for (const match of query.matchAll(
    /(-?)(kind|tag|severity|status):(?:"([^"]*)"|(\S+))/gi,
  )) {
    if (match[1]) continue;
    const field = match[2].toLowerCase();
    const value = (match[3] ?? match[4]).replace(/^"|"$/g, "");
    selection[field] = [...new Set([...(selection[field] ?? []), value])];
  }
  return selection;
}

export function selectionToQuery(selection: FacetSelection): string {
  return Object.entries(selection)
    .flatMap(([field, values]) =>
      values.map((value) =>
        /\s/.test(value) ? `${field}:"${value}"` : `${field}:${value}`,
      ),
    )
    .join(" ");
}
