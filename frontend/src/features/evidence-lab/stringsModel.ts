/** Filtering and aggregation for the strings and entropy tabs. */

import type {
  EntropyBucketData,
  EntropyReportData,
  StringHitData,
  StringScanData,
} from "./types";
import { clamp } from "./format";

export interface StringTab {
  id: string;
  label: string;
  count: number;
}

export function stringTabs(scan: StringScanData | null): StringTab[] {
  const counts = scan?.counts ?? {};
  const tabs: StringTab[] = [
    { id: "all", label: "All", count: scan?.hits.length ?? 0 },
  ];
  for (const [kind, count] of Object.entries(counts)) {
    tabs.push({
      id: kind,
      label: kind.charAt(0).toUpperCase() + kind.slice(1),
      count,
    });
  }
  return tabs.sort((a, b) => b.count - a.count || a.id.localeCompare(b.id));
}

export function filterHits(
  hits: readonly StringHitData[],
  query: string,
  kind: string,
): StringHitData[] {
  const needle = query.trim().toLowerCase();
  return hits.filter((hit) => {
    if (kind !== "all" && hit.kind !== kind) return false;
    return !needle || hit.text.toLowerCase().includes(needle);
  });
}

export function groupByKind(
  hits: readonly StringHitData[],
): Record<string, StringHitData[]> {
  const groups: Record<string, StringHitData[]> = {};
  for (const hit of hits) {
    (groups[hit.kind] ??= []).push(hit);
  }
  return groups;
}

export function topStrings(
  hits: readonly StringHitData[],
  limit = 20,
): StringHitData[] {
  return [...hits]
    .sort((a, b) => b.length - a.length || a.offset - b.offset)
    .slice(0, limit);
}

export function hitAtOffset(
  hits: readonly StringHitData[],
  offset: number,
): StringHitData | null {
  return hits.find((hit) => hit.offset <= offset && offset < hit.end) ?? null;
}

export function stringCoverage(scan: StringScanData | null): number {
  if (!scan || scan.bytes_scanned <= 0) return 0;
  const bytes = scan.hits.reduce((total, hit) => total + hit.length, 0);
  return clamp(bytes / scan.bytes_scanned, 0, 1);
}

export interface EntropyBar {
  label: string;
  ratio: number;
  count: number;
}

export function entropyBars(
  buckets: readonly EntropyBucketData[],
): EntropyBar[] {
  const peak = Math.max(1, ...buckets.map((bucket) => bucket.count));
  return buckets.map((bucket) => ({
    label: bucket.label,
    ratio: bucket.count / peak,
    count: bucket.count,
  }));
}

export function entropyTone(report: EntropyReportData | null): string {
  if (!report) return "neutral";
  if (report.normalized < 0.25) return "low";
  if (report.normalized < 0.6) return "medium";
  if (report.normalized < 0.9) return "high";
  return "random";
}

export function entropySummary(report: EntropyReportData | null): string {
  if (!report) return "No entropy sample";
  return `${report.classification.replace("_", " ")} - ${report.normalized.toFixed(2)} normalized`;
}
