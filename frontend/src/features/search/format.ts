import type { FacetCount, SearchResponse } from "./types";

export function formatCount(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}m`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function formatElapsed(ms: number): string {
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatScore(score: number): string {
  if (score >= 100) return score.toFixed(0);
  if (score >= 10) return score.toFixed(1);
  return score.toFixed(2);
}

export function formatDate(value: string): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function truncate(value: string, width = 80): string {
  if (value.length <= width) return value;
  return `${value.slice(0, Math.max(0, width - 1))}…`;
}

export function formatFacet(facet: FacetCount): string {
  return `${facet.value} (${formatCount(facet.count)})`;
}

export function formatSearchSummary(response: SearchResponse): string {
  const { total, facets, elapsed_ms, generation } = response.result;
  return `${total} result${total === 1 ? "" : "s"} · ${facets.length} facets · generation ${generation} · ${formatElapsed(elapsed_ms)}`;
}

export function formatPageInfo(response: SearchResponse): string {
  const total = response.page.total ?? response.result.total;
  if (response.page.has_more) {
    return `${formatCount(response.result.items.length)} of ${formatCount(total)}+`;
  }
  return `${formatCount(response.result.items.length)} of ${formatCount(total)}`;
}

export function formatQueryLabel(text: string): string {
  return text.trim() ? truncate(text, 60) : "All notes";
}
