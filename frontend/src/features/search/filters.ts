import { formatFilter, parseFilterToken } from "./query";
import type { FacetCount, ParsedFilter, SearchResultHit } from "./types";

export interface FilterChip {
  id: string;
  label: string;
  filter: ParsedFilter;
}

export interface FacetSelection {
  field: string;
  selected: string[];
}

export function filtersFromQuery(text: string): ParsedFilter[] {
  return text
    .split(/\s+/)
    .map((token) => {
      try {
        return parseFilterToken(token);
      } catch {
        return null;
      }
    })
    .filter((filter): filter is ParsedFilter => filter !== null);
}

export function filterId(filter: ParsedFilter): string {
  return `${filter.negated ? "-" : ""}${filter.field}${filter.operator}${filter.value}`;
}

export function filterLabel(filter: ParsedFilter): string {
  const negation = filter.negated ? "not " : "";
  if (filter.operator === ":")
    return `${negation}${filter.field}: ${filter.value}`;
  return `${negation}${filter.field} ${filter.operator} ${filter.value}`;
}

export function chipsFromFilters(filters: ParsedFilter[]): FilterChip[] {
  return filters.map((filter) => ({
    id: filterId(filter),
    label: filterLabel(filter),
    filter,
  }));
}

export function toggleFilter(
  filters: ParsedFilter[],
  filter: ParsedFilter,
): ParsedFilter[] {
  const id = filterId(filter);
  if (filters.some((item) => filterId(item) === id)) {
    return filters.filter((item) => filterId(item) !== id);
  }
  return [...filters, filter];
}

export function toggleFacetFilter(
  filters: ParsedFilter[],
  field: string,
  value: string,
): ParsedFilter[] {
  return toggleFilter(filters, {
    field,
    operator: ":",
    value,
    negated: false,
  });
}

export function removeFilterField(
  filters: ParsedFilter[],
  field: string,
): ParsedFilter[] {
  return filters.filter((filter) => filter.field !== field);
}

export function filtersToQueryFragment(filters: ParsedFilter[]): string {
  return filters.map(formatFilter).join(" ");
}

export function withFacetFilters(
  text: string,
  filters: ParsedFilter[],
): string {
  const fragment = filtersToQueryFragment(filters);
  return fragment ? `${text.trim()} ${fragment}`.trim() : text.trim();
}

export function hasFilter(
  filters: ParsedFilter[],
  field: string,
  value: string,
): boolean {
  const target = value.toLowerCase();
  return filters.some(
    (filter) =>
      filter.field === field &&
      filter.value.toLowerCase() === target &&
      !filter.negated,
  );
}

export function facetsFromHits(
  hits: SearchResultHit[],
  field: string,
  limit = 12,
): FacetCount[] {
  const counts = new Map<string, number>();
  for (const hit of hits) {
    const raw = hit.metadata[field];
    const values = Array.isArray(raw) ? raw : [raw];
    for (const value of values) {
      const text = String(value ?? "").trim();
      if (!text) continue;
      counts.set(text, (counts.get(text) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([value, count]) => ({ value, count }));
}

function metadataValues(hit: SearchResultHit, field: string): string[] {
  if (field === "id" || field === "node_id") return [String(hit.node_id)];
  if (field === "title") return [hit.title];
  if (field === "path") return [hit.path];
  if (field === "tag" || field === "tags") {
    const raw = hit.metadata.tags ?? hit.metadata.tag ?? [];
    return Array.isArray(raw) ? raw.map(String) : [String(raw)];
  }
  const raw = hit.metadata[field];
  return Array.isArray(raw) ? raw.map(String) : [String(raw ?? "")];
}

function matchesOperator(actual: string, filter: ParsedFilter): boolean {
  const expected = filter.value.toLowerCase();
  const value = actual.toLowerCase();
  if (filter.operator === "~" || filter.operator === ":") {
    if (expected.includes("*")) {
      const pattern = `^${expected.replace(/\*/g, ".*")}$`;
      return new RegExp(pattern).test(value);
    }
    return value.includes(expected);
  }
  if (filter.operator === "=") return value === expected;
  if (filter.operator === "!=") return value !== expected;
  const left = Number(value);
  const right = Number(expected);
  const comparable = Number.isFinite(left) && Number.isFinite(right);
  const a = comparable ? left : value;
  const b = comparable ? right : expected;
  if (filter.operator === ">") return a > b;
  if (filter.operator === ">=") return a >= b;
  if (filter.operator === "<") return a < b;
  return a <= b;
}

export function applyClientFilters(
  hits: SearchResultHit[],
  filters: ParsedFilter[],
): SearchResultHit[] {
  return hits.filter((hit) =>
    filters.every((filter) => {
      const matched = metadataValues(hit, filter.field).some((value) =>
        matchesOperator(value, filter),
      );
      return filter.negated ? !matched : matched;
    }),
  );
}

export function filterSummary(filters: ParsedFilter[]): string {
  if (!filters.length) return "All notes";
  return filters.map(filterLabel).join(" · ");
}

export function selectionFromFilters(
  filters: ParsedFilter[],
): FacetSelection[] {
  const groups = new Map<string, string[]>();
  for (const filter of filters) {
    if (filter.negated || filter.operator !== ":") continue;
    const values = groups.get(filter.field) ?? [];
    if (!values.includes(filter.value)) values.push(filter.value);
    groups.set(filter.field, values);
  }
  return [...groups.entries()].map(([field, selected]) => ({
    field,
    selected,
  }));
}

export function mergeFacets(
  primary: FacetCount[],
  fallback: FacetCount[],
  selected: string[],
): FacetCount[] {
  const merged = new Map<string, number>();
  for (const facet of fallback) merged.set(facet.value, facet.count);
  for (const facet of primary) merged.set(facet.value, facet.count);
  for (const value of selected) {
    if (!merged.has(value)) merged.set(value, 0);
  }
  return [...merged.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, count }));
}
