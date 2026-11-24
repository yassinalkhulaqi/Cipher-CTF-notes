/** Client-side filter DSL helpers mirroring the Python activity DSL. */

import type { FacetCounts, FilterChipData, FilterOperator, FilterValidation } from "./types";

export const FILTER_KEYS = [
  "kind",
  "actor",
  "subject",
  "severity",
  "text",
  "since",
  "until",
  "correlation",
  "tag",
] as const;

export const FILTER_OPERATORS: FilterOperator[] = ["include", "exclude"];

export const SEVERITIES = ["trace", "info", "notice", "warning", "critical"] as const;

export function severityRank(value: string): number {
  const index = SEVERITIES.indexOf(value.toLowerCase() as (typeof SEVERITIES)[number]);
  return index < 0 ? -1 : index;
}

export function severityTone(value: string): string {
  const rank = severityRank(value);
  if (rank >= 4) return "critical";
  if (rank === 3) return "warning";
  if (rank === 2) return "notice";
  if (rank === 1) return "info";
  return "trace";
}

/** Split a query into tokens while honouring single and double quotes. */
export function tokenizeFilterQuery(query: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let quote = "";
  let escaped = false;
  for (const character of query) {
    if (escaped) {
      current += character;
      escaped = false;
      continue;
    }
    if (character === "\\") {
      escaped = true;
      continue;
    }
    if (quote) {
      if (character === quote) {
        quote = "";
      } else {
        current += character;
      }
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      continue;
    }
    if (/\s/.test(character)) {
      if (current) {
        tokens.push(current);
        current = "";
      }
      continue;
    }
    current += character;
  }
  if (current) tokens.push(current);
  return tokens;
}

export function makeChip(key: string, value: string, operator: FilterOperator = "include"): FilterChipData {
  const prefix = operator === "exclude" ? "-" : "";
  return { key, value, operator, label: value, token: `${prefix}${key}:${value}` };
}

export function chipFromToken(token: string): FilterChipData | null {
  if (!token) return null;
  let operator: FilterOperator = "include";
  let raw = token;
  if (raw.startsWith("-") || raw.startsWith("!")) {
    operator = "exclude";
    raw = raw.slice(1);
  }
  const colon = raw.indexOf(":");
  if (colon < 0) {
    return raw ? makeChip("text", raw, operator) : null;
  }
  const key = raw.slice(0, colon).toLowerCase();
  const value = raw.slice(colon + 1);
  if (!key || !value) return null;
  return makeChip(key, value, operator);
}

function isTimestamp(value: string): boolean {
  if (!value.trim()) return false;
  if (!Number.isNaN(Number(value))) return true;
  return Number.isNaN(Date.parse(value)) === false;
}

export function parseFilterQuery(query: string): {
  chips: FilterChipData[];
  errors: string[];
  normalized: string;
} {
  const chips: FilterChipData[] = [];
  const errors: string[] = [];
  for (const token of tokenizeFilterQuery(query)) {
    const chip = chipFromToken(token);
    if (!chip) continue;
    if (!(FILTER_KEYS as readonly string[]).includes(chip.key)) {
      errors.push(`Unsupported filter key: ${chip.key}`);
      continue;
    }
    if (chip.key === "severity" && severityRank(chip.value) < 0) {
      errors.push(`Unknown severity: ${chip.value}`);
      continue;
    }
    if ((chip.key === "since" || chip.key === "until") && !isTimestamp(chip.value)) {
      errors.push(`Invalid timestamp for ${chip.key}: ${chip.value}`);
      continue;
    }
    chips.push(chip);
  }
  return { chips, errors, normalized: chipsToQuery(chips) };
}

export function validateFilterQuery(query: string): FilterValidation {
  const parsed = parseFilterQuery(query);
  return {
    valid: parsed.errors.length === 0,
    errors: parsed.errors,
    tokens: parsed.chips,
    normalized: parsed.normalized,
  };
}

export function chipsToQuery(chips: FilterChipData[]): string {
  return chips.map((chip) => chip.token).join(" ");
}

export function hasChip(chips: FilterChipData[], candidate: FilterChipData): boolean {
  return chips.some((chip) => chip.token === candidate.token);
}

export function toggleChip(chips: FilterChipData[], candidate: FilterChipData): FilterChipData[] {
  if (hasChip(chips, candidate)) {
    return chips.filter((chip) => chip.token !== candidate.token);
  }
  return [...chips, candidate];
}

export function removeChip(chips: FilterChipData[], token: string): FilterChipData[] {
  return chips.filter((chip) => chip.token !== token);
}

const FACET_KEYS: Record<keyof FacetCounts, string> = {
  kinds: "kind",
  actors: "actor",
  severities: "severity",
  subjects: "subject",
};

export function facetChips(facets: FacetCounts, key: keyof FacetCounts, limit = 8): FilterChipData[] {
  const counts = facets[key] ?? {};
  return Object.keys(counts)
    .sort((left, right) => counts[right] - counts[left] || left.localeCompare(right))
    .slice(0, Math.max(0, limit))
    .map((value) => makeChip(FACET_KEYS[key], value));
}

export function chipsFromFilterBody(body: Record<string, unknown>): FilterChipData[] {
  const chips: FilterChipData[] = [];
  for (const key of ["kinds", "actors", "subjects", "tags"] as const) {
    const values = body[key];
    if (!Array.isArray(values)) continue;
    const chipKey = key === "kinds" ? "kind" : key === "actors" ? "actor" : key === "subjects" ? "subject" : "tag";
    for (const value of values) {
      if (typeof value === "string") chips.push(makeChip(chipKey, value));
    }
  }
  return chips;
}

export function chipSummary(chips: FilterChipData[]): string {
  if (!chips.length) return "All activity";
  return chips.map((chip) => chip.label).join(" + ");
}
