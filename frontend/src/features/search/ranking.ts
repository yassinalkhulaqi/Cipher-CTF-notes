import type { ResultGroup, SearchResultHit, SearchSort } from "./types";

export function sortHits(
  hits: SearchResultHit[],
  key: SearchSort,
): SearchResultHit[] {
  const copy = [...hits];
  if (key === "updated") {
    return copy.sort((a, b) =>
      String(b.metadata.updated_at ?? "").localeCompare(
        String(a.metadata.updated_at ?? ""),
      ),
    );
  }
  if (key === "title")
    return copy.sort((a, b) => a.title.localeCompare(b.title));
  if (key === "id") return copy.sort((a, b) => a.node_id - b.node_id);
  return copy.sort((a, b) => b.score - a.score || b.node_id - a.node_id);
}

export function dedupeHits(hits: SearchResultHit[]): SearchResultHit[] {
  const seen = new Set<number>();
  const result: SearchResultHit[] = [];
  for (const hit of hits) {
    if (seen.has(hit.node_id)) continue;
    seen.add(hit.node_id);
    result.push(hit);
  }
  return result;
}

export function mergeHits(...groups: SearchResultHit[][]): SearchResultHit[] {
  return dedupeHits(groups.flat());
}

export function groupLabel(key: string): string {
  if (!key) return "Results";
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function groupHits(
  hits: SearchResultHit[],
  groupBy: string,
  maxGroups = 12,
): ResultGroup[] {
  const buckets = new Map<string, SearchResultHit[]>();
  for (const hit of hits) {
    const key = hit.group || String(hit.metadata[groupBy] ?? "");
    const normalized = key.trim().toLowerCase() || "none";
    const bucket = buckets.get(normalized) ?? [];
    bucket.push(hit);
    buckets.set(normalized, bucket);
  }
  return [...buckets.entries()]
    .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
    .slice(0, maxGroups)
    .map(([key, values]) => ({
      key,
      label: groupLabel(key),
      hits: sortHits(values, "relevance"),
      total: values.length,
    }));
}

export function flattenGroups(groups: ResultGroup[]): SearchResultHit[] {
  return mergeHits(...groups.map((group) => group.hits));
}

export function scoreLabel(score: number): string {
  if (score >= 25) return "exact";
  if (score >= 10) return "strong";
  if (score >= 2) return "related";
  return "weak";
}

export function scoreParts(hit: SearchResultHit): Array<[string, number]> {
  return Object.entries(hit.score_details?.components ?? {}).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1]),
  );
}

export function explainScore(hit: SearchResultHit): string {
  const parts = scoreParts(hit)
    .slice(0, 3)
    .map(([name, value]) => `${name}=${value.toFixed(2)}`);
  return `${hit.score.toFixed(2)} · ${parts.join(", ") || "no signals"}`;
}

export function filterByMinScore(
  hits: SearchResultHit[],
  minimum: number,
): SearchResultHit[] {
  return hits.filter((hit) => hit.score >= minimum);
}

export function topHits(
  hits: SearchResultHit[],
  limit = 10,
): SearchResultHit[] {
  return sortHits(hits, "relevance").slice(0, limit);
}

export function rankByCoverage(hits: SearchResultHit[]): SearchResultHit[] {
  return [...hits].sort(
    (a, b) =>
      (b.score_details?.coverage ?? 0) - (a.score_details?.coverage ?? 0) ||
      b.score - a.score,
  );
}

export function hitMetadata(hit: SearchResultHit, key: string): string {
  const value = hit.metadata[key];
  if (Array.isArray(value)) return value.map(String).join(", ");
  return value === undefined || value === null ? "" : String(value);
}

export function hitsToCommands(hits: SearchResultHit[]): string[] {
  return hits.map((hit) => `/goto ${hit.node_id} ${JSON.stringify(hit.title)}`);
}

export function scoreBadgeClass(hit: SearchResultHit): string {
  return `search-v2-score search-v2-score--${scoreLabel(hit.score)}`;
}
